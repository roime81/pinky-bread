from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from .company_graph import create_edge, create_node, get_company_graph, update_node
from .object_store import ObjectStore
from .settings import get_settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()



class WorkforceExecutionCancelled(RuntimeError):
    """Cooperative cancellation at safe agent/task boundaries."""


def _agent_role(agent: dict[str, Any]) -> str:
    data = agent.get("data") or {}
    return str(data.get("role") or data.get("title") or "Generalist")


def _agent_title(agent: dict[str, Any]) -> str:
    data = agent.get("data") or {}
    return str(data.get("title") or data.get("role") or "AI Employee")


def _is_coordinator(agent: dict[str, Any]) -> bool:
    data = agent.get("data") or {}
    authority = str(data.get("authority") or "").upper()
    legacy_role = str(data.get("role") or "").lower()
    return authority == "COORDINATOR" or legacy_role in {"head_of_agents", "chief_of_staff", "chief-of-staff"}


def _is_active_agent(agent: dict[str, Any]) -> bool:
    return agent.get("type") == "agent" and agent.get("status") not in {"ARCHIVED", "DISABLED", "PAUSED"}





def _edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return graph.get("edges", [])


def _nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return graph.get("nodes", [])


def _ensure_edge(
    company_id: str,
    tenant_id: str,
    actor_id: str,
    graph: dict[str, Any],
    source_id: str,
    target_id: str,
    relationship: str,
) -> None:
    exists = any(
        edge["source"] == source_id
        and edge["target"] == target_id
        and edge["relationship"] == relationship
        for edge in _edges(graph)
    )
    if not exists:
        create_edge(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            source_node_id=source_id,
            target_node_id=target_id,
            relationship=relationship,
            data={"managed_by": "pinky_bread_workforce"},
        )


def bootstrap_workforce(*, company_id: str, tenant_id: str, actor_id: str) -> dict[str, Any]:
    """Legacy-compatible discovery endpoint. It deliberately creates no predefined agents."""
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise LookupError("Company not found")
    agents = [node for node in _nodes(graph) if node["type"] == "agent"]
    return {
        "company_id": company_id,
        "agents": agents,
        "count": len(agents),
        "created": 0,
        "message": "No default roster is installed. Create and configure the agents your company needs.",
    }


def _mock_plan(agents: list[dict[str, Any]], goal: dict[str, Any]) -> dict[str, Any]:
    """Create transparent placeholder assignments from the agents a founder actually defined."""
    candidates = [agent for agent in agents if not _is_coordinator(agent)] or agents
    tasks = []
    previous_key: str | None = None
    for index, agent in enumerate(candidates[:8], start=1):
        title = _agent_title(agent)
        task_key = f"agent_contribution_{index}"
        tasks.append({
            "key": task_key,
            "title": f"{agent['name']}: {goal['name']}",
            "agent_id": agent["id"],
            "description": (
                f"Prepare a practical contribution to the company goal from the perspective of "
                f"{agent['name']} ({title}). Use the agent's configured responsibilities and capabilities, "
                "identify assumptions and risks, and propose concrete next steps."
            ),
            "acceptance_criteria": [
                "A self-contained contribution is recorded",
                "Assumptions and material risks are identified",
                "Concrete next steps are recommended",
            ],
            "depends_on": [previous_key] if previous_key else [],
        })
        previous_key = task_key
    return {"tasks": tasks}



def _openai_compatible_base_url(value: str) -> str:
    endpoint = value.strip().rstrip("/")
    if endpoint.endswith("/chat/completions"):
        endpoint = endpoint[: -len("/chat/completions")]
    if not endpoint.endswith("/v1"):
        endpoint = f"{endpoint}/v1"
    return endpoint


async def _chat_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 1600,
    model_name: str | None = None,
    api_url: str | None = None,
    api_key: str | None = None,
) -> str:
    settings = get_settings()
    if settings.mock_inference:
        raise RuntimeError("Local model inference is disabled while MOCK_INFERENCE=true")
    payload = {
        "model": model_name or settings.reasoning_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{_openai_compatible_base_url(api_url or settings.reasoning_api_url)}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key or settings.vllm_api_key}"},
        )
        response.raise_for_status()
        body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Local model returned an unsupported chat-completion response") from exc
    if isinstance(content, list):
        content = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Local model returned an empty response")
    return content.strip()



async def chat_with_agent(
    *,
    agent: dict[str, Any],
    company: dict[str, Any],
    agents: list[dict[str, Any]],
    message: str,
    history: list[dict[str, str]],
    company_id: str,
    tenant_id: str,
) -> str:
    settings = get_settings()
    if settings.mock_inference:
        raise RuntimeError("AI chat is disabled because MOCK_INFERENCE=true. Configure a model endpoint and set MOCK_INFERENCE=false.")
    data = agent.get("data") or {}
    model_config = data.get("model_configuration") or {}
    model_name = str(model_config.get("model_name") or settings.reasoning_model)
    endpoint = str(model_config.get("endpoint") or settings.reasoning_api_url)
    if not endpoint.startswith(("http://", "https://")):
        raise RuntimeError("The selected agent model endpoint must be an HTTP(S) URL.")
    role = _agent_role(agent)
    responsibilities = data.get("responsibilities") or []
    skills = data.get("skills") or []
    system = str(data.get("system_prompt") or (
        f"You are {agent['name']}, an AI employee of {company['name']}. Your role is {role}. "
        f"Responsibilities: {responsibilities}. Skills: {skills}. "
        "Answer the founder directly, be candid about uncertainty, and distinguish facts from assumptions. "
        "You may discuss plans and propose actions, but never claim you executed tools, changed records, "
        "sent messages, spent money or completed work unless the platform confirms that action."
    ))
    system += (
        f"\n\nCompany vision: {(company.get('data') or {}).get('vision', '')}"
        f"\nCompany mission: {(company.get('data') or {}).get('mission', '')}"
        f"\nOther active employees: {json.dumps([{'name': item['name'], 'role': _agent_role(item)} for item in agents if item['id'] != agent['id']], ensure_ascii=False)}"
    )
    messages = history[-12:] + [{"role": "user", "content": message}]
    settings_model = model_config.get("model_name") or settings.reasoning_model
    payload_history = "\n\n".join(f"{item['role'].upper()}: {item['content']}" for item in messages[:-1])
    prompt = (f"Conversation so far:\n{payload_history}\n\n" if payload_history else "") + message
    if settings.mcp_enabled:
        from .mcp_client import complete_with_mcp

        is_coordinator = _is_coordinator(agent)
        return await complete_with_mcp(
            system_prompt=system,
            user_prompt=prompt,
            role="head_of_agents" if is_coordinator else "specialist",
            company_id=company_id,
            tenant_id=tenant_id,
            agent_id=agent["id"],
            max_tokens=int(model_config.get("max_tokens", 1800)),
            model_name=str(settings_model),
            api_url=endpoint,
        )
    return await _chat_completion(
        system_prompt=system,
        user_prompt=prompt,
        temperature=float(model_config.get("temperature", 0.25)),
        max_tokens=int(model_config.get("max_tokens", 1800)),
        model_name=str(settings_model),
        api_url=endpoint,
    )



def _chat_agent_matches(agent: dict[str, Any], message: str) -> bool:
    """Return true when the founder explicitly calls an employee by name or role."""
    data = agent.get("data") or {}
    labels = [agent.get("name", ""), data.get("role", ""), data.get("title", "")]
    for label in labels:
        value = str(label or "").strip()
        if len(value) < 2:
            continue
        if re.search(rf"(?<![\\w])@?{re.escape(value)}(?![\\w])", message, re.IGNORECASE):
            return True
    return False


def _chat_relevance_score(agent: dict[str, Any], message: str) -> int:
    """Lightweight, explainable role/skill routing; all active employees receive the same transcript."""
    data = agent.get("data") or {}
    profile = " ".join([
        str(agent.get("name") or ""), str(agent.get("description") or ""),
        _agent_role(agent), _agent_title(agent),
        " ".join(map(str, data.get("skills") or [])),
        " ".join(map(str, data.get("responsibilities") or [])),
        str(data.get("system_prompt") or ""),
    ]).lower()
    stop = {"the", "and", "for", "with", "that", "this", "from", "your", "you", "are",
            "can", "could", "would", "should", "what", "when", "where", "how", "why",
            "please", "help", "about", "into", "have", "has", "our", "their", "they"}
    words = {word for word in re.findall(r"[a-z0-9]{3,}", message.lower()) if word not in stop}
    if not words:
        return 0
    score = 0
    for word in words:
        if re.search(rf"\\b{re.escape(word)}\\b", profile):
            score += 2
    # A specialist's configured responsibility/skill match is stronger than a generic prompt match.
    specialist_text = " ".join(map(str, data.get("skills") or [])) + " " + " ".join(map(str, data.get("responsibilities") or []))
    specialist_text = specialist_text.lower()
    score += sum(2 for word in words if re.search(rf"\\b{re.escape(word)}\\b", specialist_text))
    if _is_coordinator(agent):
        score += 1
    return score


async def chat_with_workforce(
    *,
    agents: list[dict[str, Any]],
    company: dict[str, Any],
    message: str,
    history: list[dict[str, str]],
    company_id: str,
    tenant_id: str,
) -> list[dict[str, str]]:
    """Let every active employee observe the conversation, then invite relevant people to answer.

    Explicit name/role mentions are mandatory responders. Otherwise the highest-scoring
    specialists are invited, with the coordinator as a fallback. Responses are sequential
    so later speakers can build on earlier contributions.
    """
    if not agents:
        return []
    mentioned = [agent for agent in agents if _chat_agent_matches(agent, message)]
    if mentioned:
        selected = mentioned
    else:
        ranked = sorted(
            ((_chat_relevance_score(agent, message), agent) for agent in agents),
            key=lambda item: (item[0], _is_coordinator(item[1])),
            reverse=True,
        )
        relevant = [agent for score, agent in ranked if score > 0][:3]
        if not relevant:
            coordinator = next((agent for agent in agents if _is_coordinator(agent)), None)
            relevant = [coordinator or ranked[0][1]]
        selected = relevant

    responses: list[dict[str, str]] = []
    shared_history = list(history)
    for agent in selected:
        reply = await chat_with_agent(
            agent=agent,
            company=company,
            agents=agents,
            message=message,
            history=shared_history,
            company_id=company_id,
            tenant_id=tenant_id,
        )
        responses.append({"agent_id": str(agent["id"]), "name": str(agent["name"]), "role": _agent_role(agent), "reply": reply})
        shared_history.append({"role": "assistant", "content": f"{agent['name']} ({_agent_role(agent)}): {reply}"[:4000]})
    return responses

def _parse_plan(content: str, allowed_agent_ids: set[str]) -> list[dict[str, Any]]:
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Coordinator did not return a JSON task plan")
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("Coordinator returned invalid JSON; no work was created") from exc
    tasks = parsed.get("tasks") if isinstance(parsed, dict) else None
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 10:
        raise ValueError("A plan must contain between 1 and 10 tasks")
    result: list[dict[str, Any]] = []
    keys: set[str] = set()
    for index, item in enumerate(tasks):
        if not isinstance(item, dict):
            raise ValueError("Every task in the plan must be an object")
        key = str(item.get("key") or f"task_{index + 1}").strip()[:80]
        agent_id = str(item.get("agent_id") or "").strip()
        title = str(item.get("title") or "").strip()[:160]
        description = str(item.get("description") or "").strip()[:3000]
        criteria = item.get("acceptance_criteria", [])
        dependencies = item.get("depends_on", [])
        if not key or key in keys:
            raise ValueError("Task keys must be non-empty and unique")
        if agent_id not in allowed_agent_ids:
            raise ValueError(f"Task {key} refers to an agent that is not available in this company")
        if not title or not description:
            raise ValueError("Every task needs a title and description")
        if not isinstance(criteria, list) or not all(isinstance(value, str) for value in criteria):
            raise ValueError(f"Acceptance criteria for {key} must be a list of strings")
        if not isinstance(dependencies, list) or not all(isinstance(value, str) for value in dependencies):
            raise ValueError(f"Dependencies for {key} must be a list of task keys")
        keys.add(key)
        result.append({
            "key": key,
            "title": title,
            "agent_id": agent_id,
            "description": description,
            "acceptance_criteria": [value[:500] for value in criteria[:8]],
            "depends_on": dependencies[:10],
        })
    for index, item in enumerate(result):
        if item["key"] in item["depends_on"] or any(dep not in keys for dep in item["depends_on"]):
            raise ValueError(f"Task {item['key']} contains an invalid dependency")
        earlier_keys = {candidate["key"] for candidate in result[:index]}
        if any(dep not in earlier_keys for dep in item["depends_on"]):
            raise ValueError(f"Dependencies for {item['key']} must refer to earlier tasks so execution order is deterministic")
    return result


async def plan_goal(*, company_id: str, tenant_id: str, goal_id: str, actor_id: str) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise LookupError("Company not found")
    goal = next((node for node in _nodes(graph) if node["id"] == goal_id and node["type"] == "goal"), None)
    if goal is None:
        raise LookupError("Goal not found in this company")
    existing = [
        node for node in _nodes(graph)
        if node["type"] == "work" and (node.get("data") or {}).get("goal_id") == goal_id
        and node.get("status") != "CANCELLED"
    ]
    if existing:
        return {"goal_id": goal_id, "created": False, "tasks": existing, "count": len(existing), "message": "An active plan already exists; no duplicate work was created."}

    active_agents = [node for node in _nodes(graph) if _is_active_agent(node)]
    coordinator = next((agent for agent in active_agents if _is_coordinator(agent)), None)
    if coordinator is None:
        raise RuntimeError("No coordinator is assigned. Create an agent and set its authority to COORDINATOR before planning.")
    if not active_agents:
        raise RuntimeError("This company has no active agents. Create the team members needed for this goal.")

    specialists = [agent for agent in active_agents if agent["id"] != coordinator["id"]] or [coordinator]
    company = next(node for node in _nodes(graph) if node["type"] == "company")
    settings = get_settings()
    if settings.mock_inference:
        tasks = _mock_plan(specialists, goal)["tasks"]
        planner_mode = "mock-template-from-company-agents"
    else:
        agent_catalog = [
            {
                "id": agent["id"],
                "name": agent["name"],
                "title": _agent_title(agent),
                "role": _agent_role(agent),
                "description": agent.get("description", ""),
                "skills": (agent.get("data") or {}).get("skills", []),
                "responsibilities": (agent.get("data") or {}).get("responsibilities", []),
            }
            for agent in specialists
        ]
        coordinator_data = coordinator.get("data") or {}
        system = str(coordinator_data.get("system_prompt") or (
            f"You are {coordinator['name']}, the company's coordinator. "
            "Turn company goals into clear, delegated work using only the available agents."
        ))
        prompt = (
            "Create a practical execution plan for this company goal. Return JSON only in this schema: "
            '{"tasks":[{"key":"short_unique_key","title":"...","agent_id":"exact-agent-id",'
            '"description":"...","acceptance_criteria":["..."],"depends_on":["earlier_task_key"]}]}. '
            "Create 1 to 10 tasks. Assign each task to an exact agent id from the available-agent catalogue. "
            "Do not invent agent ids, roles, staff or capabilities. Use the configured agent responsibilities and skills. "
            "Make work concrete and measurable, express dependencies, and do not include external financial actions.\n\n"
            f"Company: {company['name']}\nVision: {(company.get('data') or {}).get('vision', '')}\n"
            f"Mission: {(company.get('data') or {}).get('mission', '')}\n"
            f"Goal: {goal['name']}\nDescription: {goal.get('description', '')}\n"
            f"Available agents: {json.dumps(agent_catalog, ensure_ascii=False)}"
        )
        if settings.mcp_enabled:
            from .mcp_client import complete_with_mcp

            plan_response = await complete_with_mcp(
                system_prompt=system,
                user_prompt=prompt,
                role="head_of_agents",
                company_id=company_id,
                tenant_id=tenant_id,
                agent_id=coordinator["id"],
                max_tokens=3000,
                model_name=str((coordinator.get("data") or {}).get("model_configuration", {}).get("model_name") or settings.reasoning_model),
                api_url=str((coordinator.get("data") or {}).get("model_configuration", {}).get("endpoint") or settings.reasoning_api_url),
            )
        else:
            plan_response = await _chat_completion(
                system_prompt=system,
                user_prompt=prompt,
                temperature=0.15,
                max_tokens=3000,
            )
        tasks = _parse_plan(plan_response, {agent["id"] for agent in specialists})
        planner_mode = "local-model+mcp" if settings.mcp_enabled else "local-model"

    agents_by_id = {agent["id"]: agent for agent in active_agents}
    created: dict[str, dict[str, Any]] = {}
    result_tasks: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        agent = agents_by_id.get(task["agent_id"])
        if agent is None or not _is_active_agent(agent):
            raise ValueError(f"Task {task['key']} is assigned to an unavailable agent")
        role_label = _agent_role(agent)
        work = create_node(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=coordinator["id"],
            node_type="work",
            name=task["title"],
            description=task["description"],
            status="READY",
            data={
                "goal_id": goal_id,
                "task_key": task["key"],
                "sequence": index,
                "assigned_agent_id": agent["id"],
                "assigned_role": role_label,
                "acceptance_criteria": task["acceptance_criteria"],
                "depends_on_keys": task["depends_on"],
                "planner_agent_id": coordinator["id"],
                "planner_mode": planner_mode,
                "progress": 0,
                "attempt": 0,
            },
        )
        created[task["key"]] = work
        result_tasks.append(work)
        current = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
        _ensure_edge(company_id, tenant_id, coordinator["id"], current, work["id"], agent["id"], "assigned_to")
        current = get_company_graph(company_id=company_id, tenant_id=tenant_id) or current
        _ensure_edge(company_id, tenant_id, coordinator["id"], current, work["id"], goal_id, "contributes_to")
        current = get_company_graph(company_id=company_id, tenant_id=tenant_id) or current
        _ensure_edge(company_id, tenant_id, coordinator["id"], current, agent["id"], goal_id, "contributes_to")
    for task in tasks:
        source = created[task["key"]]
        for dependency_key in task["depends_on"]:
            dependency = created.get(dependency_key)
            if dependency is None:
                raise ValueError(f"Unknown dependency: {dependency_key}")
            current = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
            _ensure_edge(company_id, tenant_id, coordinator["id"], current, source["id"], dependency["id"], "depends_on")
    return {
        "goal_id": goal_id,
        "created": True,
        "planner_agent_id": coordinator["id"],
        "planner_mode": planner_mode,
        "tasks": result_tasks,
        "count": len(result_tasks),
        "message": f"{coordinator['name']} created assignments using your company's configured agents. Work has not run yet.",
    }




async def _execute_prompt(
    agent: dict[str, Any], prompt: str, *, company_id: str, tenant_id: str
) -> str:
    settings = get_settings()
    data = agent.get("data") or {}
    display_role = _agent_title(agent)
    if settings.mock_inference:
        return (
            f"# {agent['name']} — {display_role} · Development simulation\n\n"
            "This assignment ran in MOCK_INFERENCE mode. No LLM inference or external tool was used.\n\n"
            f"## Assignment context\n{prompt[:1800]}\n\n"
            "## Suggested work product\n"
            "This is a traceable development placeholder, not model-generated work. "
            "Configure a self-hosted OpenAI-compatible model endpoint and set MOCK_INFERENCE=false for real inference.\n"
        )
    responsibilities = data.get("responsibilities") or []
    skills = data.get("skills") or []
    system = str(data.get("system_prompt") or (
        f"You are {agent['name']}, working as {display_role}. Your function is {_agent_role(agent)}. "
        f"Responsibilities: {responsibilities}. Capabilities: {skills}. "
        "Complete the assignment, state assumptions, explain risks and provide a practical deliverable. "
        "Never claim external actions were performed unless an approved tool actually performed them."
    ))
    if settings.mcp_enabled:
        from .mcp_client import complete_with_mcp

        return await complete_with_mcp(
            system_prompt=system,
            user_prompt=prompt,
            role="head_of_agents" if _is_coordinator(agent) else "specialist",
            company_id=company_id,
            tenant_id=tenant_id,
            agent_id=agent["id"],
            max_tokens=2400,
            model_name=str((data.get("model_configuration") or {}).get("model_name") or settings.reasoning_model),
            api_url=str((data.get("model_configuration") or {}).get("endpoint") or settings.reasoning_api_url),
        )
    model_config = data.get("model_configuration") or {}
    endpoint = str(model_config.get("endpoint") or settings.reasoning_api_url)
    if not endpoint.startswith(("http://", "https://")):
        raise RuntimeError("The selected agent model endpoint must be an HTTP(S) URL.")
    return await _chat_completion(
        system_prompt=system,
        user_prompt=prompt,
        temperature=float(model_config.get("temperature", 0.25)),
        max_tokens=int(model_config.get("max_tokens", 2400)),
        model_name=str(model_config.get("model_name") or settings.reasoning_model),
        api_url=endpoint,
    )




def _goal_progress(company_id: str, tenant_id: str, goal_id: str, actor_id: str) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise LookupError("Company not found")
    tasks = [node for node in _nodes(graph) if node["type"] == "work" and (node.get("data") or {}).get("goal_id") == goal_id]
    completed = sum(1 for node in tasks if node["status"] == "COMPLETED")
    progress = round((completed / len(tasks)) * 100) if tasks else 0
    goal = next((node for node in _nodes(graph) if node["id"] == goal_id), None)
    if goal:
        update_node(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            node_id=goal_id,
            status="COMPLETED" if tasks and completed == len(tasks) else ("IN_PROGRESS" if completed else goal["status"]),
            data_patch={
                "progress": progress,
                "completed_work": completed,
                "total_work": len(tasks),
                "progress_updated_at": _now(),
            },
        )
    return {"progress": progress, "completed_work": completed, "total_work": len(tasks)}


async def execute_task(
    *, company_id: str, tenant_id: str, work_id: str, actor_id: str,
    retry: bool = False, cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise LookupError("Company not found")
    work = next((node for node in _nodes(graph) if node["id"] == work_id and node["type"] == "work"), None)
    if work is None:
        raise LookupError("Work item not found")
    if work["status"] == "COMPLETED":
        return {"task": work, "idempotent": True, "message": "This assignment is already complete."}
    if cancel_check and cancel_check():
        raise WorkforceExecutionCancelled("Workforce job cancelled before assignment start")
    data = work.get("data") or {}
    recovering = False
    if work["status"] == "RUNNING":
        started = data.get("started_at")
        try:
            started_at = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
        except (TypeError, ValueError):
            age_seconds = get_settings().worker_lease_seconds + 1
        if age_seconds <= get_settings().worker_lease_seconds:
            raise RuntimeError("This assignment is already running under a live worker lease")
        recovering = True
    if work["status"] == "FAILED" and not retry:
        raise RuntimeError("This assignment failed; set retry=true to run it again")
    for dependency_key in data.get("depends_on_keys", []):
        dependency = next((
            node for node in _nodes(graph)
            if node["type"] == "work" and (node.get("data") or {}).get("task_key") == dependency_key
            and (node.get("data") or {}).get("goal_id") == data.get("goal_id")
        ), None)
        if dependency and dependency["status"] != "COMPLETED":
            raise RuntimeError(f"Blocked by prerequisite: {dependency['name']}")

    assignment = next((
        edge for edge in _edges(graph)
        if edge["source"] == work_id and edge["relationship"] == "assigned_to"
    ), None)
    if assignment is None:
        raise RuntimeError("Work item has no assigned agent")
    agent = next((node for node in _nodes(graph) if node["id"] == assignment["target"] and node["type"] == "agent"), None)
    if agent is None or not _is_active_agent(agent):
        raise RuntimeError("Assigned agent is archived, disabled or unavailable. Reassign this work item before retrying.")
    goal = next((node for node in _nodes(graph) if node["id"] == data.get("goal_id")), None)
    company = next(node for node in _nodes(graph) if node["type"] == "company")
    attempt = int(data.get("attempt", 0)) if recovering else int(data.get("attempt", 0)) + 1
    update_node(
        company_id=company_id,
        tenant_id=tenant_id,
        actor_id=agent["id"],
        node_id=work_id,
        status="RUNNING",
        data_patch={
            "attempt": max(attempt, 1),
            "started_at": data.get("started_at") if recovering else _now(),
            "runtime_mode": "MOCK" if get_settings().mock_inference else "LOCAL_MODEL",
            "recovered_after_lease_expiry": recovering,
        },
    )
    dependencies = []
    for edge in _edges(graph):
        if edge["source"] == work_id and edge["relationship"] == "depends_on":
            previous = next((node for node in _nodes(graph) if node["id"] == edge["target"]), None)
            if previous:
                dependencies.append(f"- {previous['name']}: {(previous.get('data') or {}).get('result_summary', 'completed')}")
    prompt = (
        f"Company: {company['name']}\n"
        f"Vision: {(company.get('data') or {}).get('vision', '')}\n"
        f"Mission: {(company.get('data') or {}).get('mission', '')}\n"
        f"Goal: {goal['name'] if goal else data.get('goal_id')} — {goal.get('description', '') if goal else ''}\n"
        f"Assignment: {work['name']}\n"
        f"Description: {work.get('description', '')}\n"
        f"Acceptance criteria: {json.dumps(data.get('acceptance_criteria', []), ensure_ascii=False)}\n"
        f"Completed prerequisites:\n{chr(10).join(dependencies) or '- None'}\n\n"
        "Produce a useful, self-contained work product. Separate facts, assumptions and recommendations. "
        "Include a concise summary and explicit next steps. Do not claim that external actions were performed."
    )
    try:
        output = await _execute_prompt(agent, prompt, company_id=company_id, tenant_id=tenant_id)
        if cancel_check and cancel_check():
            raise WorkforceExecutionCancelled("Workforce job cancelled after model inference")
        filename = f"work-{work_id[:8]}-attempt-{max(attempt, 1)}.md"
        object_key = f"companies/{company_id}/deliverables/{work_id}/attempt-{max(attempt, 1)}.md"
        stored = ObjectStore().persist_object_idempotent(
            key=object_key,
            content=output.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
            tenant_id=tenant_id,
            company_id=company_id,
            owner_type="work",
            owner_id=work_id,
            filename=filename,
            created_by=agent["id"],
            metadata={"goal_id": data.get("goal_id"), "agent_id": agent["id"], "work_id": work_id},
        )
        latest_graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
        deliverable_data = {
            "object_id": stored["object_id"],
            "filename": filename,
            "content_type": stored["content_type"],
            "size_bytes": stored["size_bytes"],
            "sha256": stored["sha256"],
            "download_endpoint": f"/v2/companies/{company_id}/artifacts/{stored['object_id']}",
            "work_id": work_id,
            "goal_id": data.get("goal_id"),
            "agent_id": agent["id"],
            "attempt": max(attempt, 1),
            "execution_mode": "MOCK" if get_settings().mock_inference else "LOCAL_MODEL",
        }
        deliverable = next((
            node for node in latest_graph["nodes"]
            if node["type"] == "deliverable"
            and (node.get("data") or {}).get("work_id") == work_id
            and (node.get("data") or {}).get("attempt") == max(attempt, 1)
        ), None)
        if deliverable is None:
            deliverable = create_node(
                company_id=company_id,
                tenant_id=tenant_id,
                actor_id=agent["id"],
                node_type="deliverable",
                name=f"Deliverable: {work['name']}",
                description=f"Generated by {agent['name']} for assignment {work['name']}",
                status="STORED",
                data=deliverable_data,
            )
        else:
            deliverable = update_node(
                company_id=company_id,
                tenant_id=tenant_id,
                actor_id=agent["id"],
                node_id=deliverable["id"],
                status="STORED",
                data_patch=deliverable_data,
            ) or deliverable
        latest_graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or latest_graph
        has_produces_edge = any(
            edge["source"] == work_id and edge["target"] == deliverable["id"]
            and edge["relationship"] == "produces"
            for edge in latest_graph["edges"]
        )
        if not has_produces_edge:
            create_edge(
                company_id=company_id,
                tenant_id=tenant_id,
                actor_id=agent["id"],
                source_node_id=work_id,
                target_node_id=deliverable["id"],
                relationship="produces",
                data={"object_id": stored["object_id"]},
            )
        completed = update_node(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=agent["id"],
            node_id=work_id,
            status="COMPLETED",
            data_patch={
                "progress": 100,
                "completed_at": _now(),
                "deliverable_id": deliverable["id"],
                "object_id": stored["object_id"],
                "result_summary": output[:700],
                "result_sha256": stored["sha256"],
            },
        )
        progress = _goal_progress(company_id, tenant_id, str(data.get("goal_id")), agent["id"])
        return {"task": completed, "deliverable": deliverable, "progress": progress, "idempotent": False}
    except WorkforceExecutionCancelled as exc:
        update_node(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=agent["id"],
            node_id=work_id,
            status="CANCELLED",
            data_patch={"cancelled_at": _now(), "last_error": str(exc)[:1000]},
        )
        raise
    except Exception as exc:
        update_node(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=agent["id"],
            node_id=work_id,
            status="FAILED",
            data_patch={"failed_at": _now(), "last_error": str(exc)[:1000]},
        )
        raise


async def execute_goal(
    *, company_id: str, tenant_id: str, goal_id: str, actor_id: str,
    retry_failed: bool = False, raise_on_error: bool = False,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise LookupError("Company not found")
    goal = next((node for node in _nodes(graph) if node["id"] == goal_id and node["type"] == "goal"), None)
    if goal is None:
        raise LookupError("Goal not found in this company")
    tasks = [node for node in _nodes(graph) if node["type"] == "work" and (node.get("data") or {}).get("goal_id") == goal_id]
    if not tasks:
        planned = await plan_goal(company_id=company_id, tenant_id=tenant_id, goal_id=goal_id, actor_id=actor_id)
        tasks = planned["tasks"]
    tasks.sort(key=lambda node: int((node.get("data") or {}).get("sequence", 0)))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for task in tasks:
        if cancel_check and cancel_check():
            raise WorkforceExecutionCancelled("Goal execution cancelled between assignments")
        current = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
        current_task = next((node for node in _nodes(current) if node["id"] == task["id"]), task)
        if current_task["status"] == "COMPLETED":
            results.append({"work_id": task["id"], "status": "COMPLETED", "idempotent": True})
            continue
        try:
            result = await execute_task(
                company_id=company_id, tenant_id=tenant_id, work_id=task["id"], actor_id=actor_id,
                retry=retry_failed, cancel_check=cancel_check,
            )
            results.append({"work_id": task["id"], "status": result["task"]["status"], "deliverable_id": result["deliverable"]["id"]})
        except Exception as exc:
            errors.append({"work_id": task["id"], "error": str(exc)})
            if raise_on_error:
                raise
    progress = _goal_progress(company_id, tenant_id, goal_id, actor_id)
    return {
        "goal_id": goal_id,
        "progress": progress,
        "results": results,
        "errors": errors,
        "completed": sum(1 for item in results if item["status"] == "COMPLETED"),
        "message": "Goal execution finished. Each successful assignment has a persisted deliverable; failures remain visible on the graph.",
    }


async def convene_meeting(
    *, company_id: str, tenant_id: str, meeting_id: str, actor_id: str,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise LookupError("Company not found")
    meeting = next((node for node in _nodes(graph) if node["id"] == meeting_id and node["type"] == "meeting"), None)
    if meeting is None:
        raise LookupError("Meeting not found in this company")
    meeting_data = meeting.get("data") or {}
    if meeting_data.get("meeting_state") == "COMPLETED" and meeting_data.get("minutes_object_id"):
        return {"meeting": meeting, "idempotent": True, "message": "Meeting already has persisted minutes."}

    agents = [node for node in _nodes(graph) if _is_active_agent(node)]
    requested = meeting_data.get("participant_agent_ids") or []
    if requested:
        agents = [node for node in agents if node["id"] in requested]
    else:
        agents.sort(
            key=lambda item: (
                0 if _is_coordinator(item) else 1,
                -int((item.get("data") or {}).get("seniority_level", 3)),
                item["name"].lower(),
            )
        )
    agents = agents[:8]
    if not agents:
        raise RuntimeError("No available meeting participants")
    for agent in agents:
        graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
        _ensure_edge(company_id, tenant_id, actor_id, graph, agent["id"], meeting_id, "participates_in")

    agenda = str(meeting_data.get("agenda") or meeting.get("description") or meeting["name"])
    update_node(
        company_id=company_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        node_id=meeting_id,
        status="IN_PROGRESS",
        data_patch={"meeting_state": "IN_PROGRESS", "started_at": _now(), "participant_agent_ids": [agent["id"] for agent in agents]},
    )
    discussion: list[dict[str, Any]] = []
    for index, agent in enumerate(agents, start=1):
        if cancel_check and cancel_check():
            update_node(
                company_id=company_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                node_id=meeting_id,
                status="CANCELLED",
                data_patch={"meeting_state": "CANCELLED", "cancelled_at": _now()},
            )
            raise WorkforceExecutionCancelled("Meeting cancelled between agent turns")
        prior = "\n".join(f"{item['agent_name']}: {item['contribution']}" for item in discussion)
        prompt = (
            f"Company meeting: {meeting['name']}\nAgenda: {agenda}\n"
            f"Your position: {_agent_title(agent)}\nYour function: {_agent_role(agent)}\n"
            f"Company mission: {(next(node for node in _nodes(graph) if node['type'] == 'company').get('data') or {}).get('mission', '')}\n"
            f"Previous discussion:\n{prior or 'You are the first speaker.'}\n\n"
            "Contribute one concise, practical perspective. Identify one risk or disagreement when relevant and suggest a concrete next step. "
            "Do not claim actions have been executed."
        )
        contribution = await _execute_prompt(agent, prompt, company_id=company_id, tenant_id=tenant_id)
        if cancel_check and cancel_check():
            update_node(
                company_id=company_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                node_id=meeting_id,
                status="CANCELLED",
                data_patch={"meeting_state": "CANCELLED", "cancelled_at": _now()},
            )
            raise WorkforceExecutionCancelled("Meeting cancelled after agent response")
        discussion.append({
            "sequence": index,
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "role": _agent_role(agent),
            "title": _agent_title(agent),
            "contribution": contribution[:3000],
            "occurred_at": _now(),
        })
        update_node(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=agent["id"],
            node_id=meeting_id,
            data_patch={"discussion": discussion, "current_speaker_id": agent["id"]},
        )

    head = next((agent for agent in agents if _is_coordinator(agent)), agents[0])
    transcript = "\n\n".join(f"## {item['agent_name']} ({item['role']})\n{item['contribution']}" for item in discussion)
    if get_settings().mock_inference:
        summary = f"Development simulation of {len(discussion)} agent contributions for agenda: {agenda}.\n\n" + "\n\n".join(
            f"- {item['agent_name']}: {item['contribution'][:260].replace(chr(10), ' ')}" for item in discussion
        )
        mode = "MOCK"
    else:
        summary = await _execute_prompt(
            head,
            (
                "Summarise this virtual company meeting. Include key discussion points, disagreements, decisions proposed, "
                "risks and recommended action items with suggested owners. Distinguish proposals from approved decisions.\n\n"
                f"Meeting: {meeting['name']}\nAgenda: {agenda}\nTranscript:\n{transcript}"
            ),
            company_id=company_id,
            tenant_id=tenant_id,
        )
        mode = "LOCAL_MODEL"

    minutes = (
        f"# {meeting['name']}\n\n"
        f"- Meeting type: {meeting_data.get('meeting_type', 'alignment')}\n"
        f"- Agenda: {agenda}\n"
        f"- Participants: {', '.join(agent['name'] for agent in agents)}\n"
        f"- Runtime: {mode}\n\n"
        f"## Facilitator summary\n{summary}\n\n## Discussion transcript\n{transcript}\n"
    )
    filename = f"meeting-{meeting_id}-minutes.md"
    object_key = f"companies/{company_id}/meetings/{meeting_id}/minutes.md"
    stored = ObjectStore().persist_object_idempotent(
        key=object_key,
        content=minutes.encode("utf-8"),
        content_type="text/markdown; charset=utf-8",
        tenant_id=tenant_id,
        company_id=company_id,
        owner_type="meeting",
        owner_id=meeting_id,
        filename=filename,
        created_by=head["id"],
        metadata={"meeting_id": meeting_id, "participant_ids": [agent["id"] for agent in agents], "runtime_mode": mode},
    )
    latest_graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
    deliverable_data = {
        "object_id": stored["object_id"],
        "filename": filename,
        "content_type": stored["content_type"],
        "size_bytes": stored["size_bytes"],
        "sha256": stored["sha256"],
        "download_endpoint": f"/v2/companies/{company_id}/artifacts/{stored['object_id']}",
        "meeting_id": meeting_id,
        "execution_mode": mode,
    }
    deliverable = next((
        node for node in latest_graph["nodes"]
        if node["type"] == "deliverable"
        and (node.get("data") or {}).get("meeting_id") == meeting_id
    ), None)
    if deliverable is None:
        deliverable = create_node(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=head["id"],
            node_type="deliverable",
            name=f"Minutes: {meeting['name']}",
            description="Persisted meeting minutes and turn-by-turn agent discussion.",
            status="STORED",
            data=deliverable_data,
        )
    else:
        deliverable = update_node(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=head["id"],
            node_id=deliverable["id"],
            status="STORED",
            data_patch=deliverable_data,
        ) or deliverable
    latest_graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or latest_graph
    has_produces_edge = any(
        edge["source"] == meeting_id and edge["target"] == deliverable["id"]
        and edge["relationship"] == "produces"
        for edge in latest_graph["edges"]
    )
    if not has_produces_edge:
        create_edge(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=head["id"],
            source_node_id=meeting_id,
            target_node_id=deliverable["id"],
            relationship="produces",
            data={"object_id": stored["object_id"]},
        )
    completed = update_node(
        company_id=company_id,
        tenant_id=tenant_id,
        actor_id=head["id"],
        node_id=meeting_id,
        status="COMPLETED",
        data_patch={
            "meeting_state": "COMPLETED",
            "completed_at": _now(),
            "meeting_summary": summary,
            "minutes_object_id": stored["object_id"],
            "minutes_deliverable_id": deliverable["id"],
            "runtime_mode": mode,
            "current_speaker_id": None,
        },
    )
    return {"meeting": completed, "deliverable": deliverable, "participants": discussion, "idempotent": False}


def record_kpi_measurement(
    *, company_id: str, tenant_id: str, kpi_id: str, actor_id: str,
    actual_value: float, source: str, evidence: str = "",
) -> dict[str, Any]:
    if not math.isfinite(actual_value):
        raise ValueError("KPI value must be a finite number")
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise LookupError("Company not found")
    kpi = next((node for node in _nodes(graph) if node["id"] == kpi_id and node["type"] == "kpi"), None)
    if kpi is None:
        raise LookupError("KPI not found in this company")
    data = kpi.get("data") or {}
    snapshot = {
        "actual": actual_value,
        "source": source[:240],
        "evidence": evidence[:2000],
        "measured_at": _now(),
        "recorded_by": actor_id,
    }
    history = list(data.get("snapshots") or [])[-99:] + [snapshot]
    target = data.get("target")
    status = "TARGET_MET" if isinstance(target, (int, float)) and actual_value >= float(target) else "TRACKING"
    updated = update_node(
        company_id=company_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        node_id=kpi_id,
        status=status,
        data_patch={
            "actual": actual_value,
            "measurement_state": "measured",
            "source": source[:240],
            "measured_at": snapshot["measured_at"],
            "snapshots": history,
        },
    )
    return {"kpi": updated, "measurement": snapshot, "history_count": len(history)}
