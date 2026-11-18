from __future__ import annotations

import json
import math
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


ROLE_SPECS: dict[str, dict[str, Any]] = {
    "head_of_agents": {
        "name": "Head of Agents",
        "description": "Chief of Staff for the virtual company. Coordinates goals, work allocation, meetings and escalation.",
        "skills": ["goal_planning", "delegation", "facilitation", "risk_escalation", "progress_reporting"],
        "system_prompt": "You are the Head of Agents, the Chief of Staff of a founder-led virtual company. Translate the company vision and goals into clear work. Coordinate specialists, make dependencies explicit, challenge unsupported assumptions, keep the founder informed, and request approval for consequential actions. You may plan and recommend; do not claim to have performed work that has not been executed.",
    },
    "strategy": {
        "name": "Strategy & Growth Agent",
        "description": "Market research, business strategy, customer discovery and growth planning.",
        "skills": ["market_research", "customer_discovery", "business_strategy", "growth"],
        "system_prompt": "You are the company's Strategy and Growth specialist. Produce evidence-aware market analysis, state assumptions, identify customer problems and recommend practical experiments. Never invent research or customer evidence.",
    },
    "product": {
        "name": "Product Agent",
        "description": "Product definition, customer journeys, prioritisation and acceptance criteria.",
        "skills": ["product_discovery", "roadmapping", "requirements", "acceptance_criteria"],
        "system_prompt": "You are the company's Product specialist. Turn customer and business needs into a focused product scope, user journeys, priorities and testable acceptance criteria. Distinguish assumptions from validated facts.",
    },
    "technology": {
        "name": "Technology Agent",
        "description": "Software architecture, engineering plans, implementation and technical quality.",
        "skills": ["architecture", "software_engineering", "testing", "delivery"],
        "system_prompt": "You are the company's Technology specialist. Produce implementable technical designs and engineering work, prefer maintained open-source components, explain trade-offs and include verification steps. Do not claim code was changed unless a connected tool actually changed it.",
    },
    "marketing": {
        "name": "Marketing Agent",
        "description": "Positioning, content, launch campaigns and customer acquisition.",
        "skills": ["positioning", "content", "campaigns", "customer_acquisition"],
        "system_prompt": "You are the company's Marketing specialist. Develop clear positioning, ethical campaigns and measurable customer acquisition experiments. Do not invent campaign results or customer testimonials.",
    },
    "operations": {
        "name": "Operations Agent",
        "description": "Operating procedures, service delivery, customer support and process improvement.",
        "skills": ["service_operations", "process_design", "customer_support", "quality"],
        "system_prompt": "You are the company's Operations specialist. Design repeatable, lightweight operating procedures, service delivery and support processes. Identify operational risks and owners.",
    },
    "finance": {
        "name": "Finance & Governance Agent",
        "description": "Budgeting, cost control, unit economics and financial governance.",
        "skills": ["budgeting", "unit_economics", "cost_control", "financial_planning"],
        "system_prompt": "You are the company's Finance and Governance specialist. Prepare transparent estimates, budgets and unit economics, state assumptions, highlight cash and compliance risks, and never initiate payments or financial commitments.",
    },
}


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
    """Create a reusable starter team. Repeated calls are safe and do not duplicate roles."""
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise LookupError("Company not found")
    company = next(node for node in _nodes(graph) if node["type"] == "company")
    settings = get_settings()
    agents = [node for node in _nodes(graph) if node["type"] == "agent"]
    role_to_agent: dict[str, dict[str, Any]] = {}
    for agent in agents:
        role = str((agent.get("data") or {}).get("role", "")).lower()
        if role in {"chief_of_staff", "chief-of-staff"}:
            role = "head_of_agents"
        if role in ROLE_SPECS and role not in role_to_agent:
            role_to_agent[role] = agent

    for role, spec in ROLE_SPECS.items():
        agent = role_to_agent.get(role)
        runtime_mode = "MOCK" if settings.mock_inference else "LOCAL_MODEL"
        agent_data = {
            "role": role,
            "skills": spec["skills"],
            "system_prompt": spec["system_prompt"],
            "runtime_status": "READY",
            "runtime_mode": runtime_mode,
            "model": settings.reasoning_model,
            "version": "1.0.0",
            "authority": "coordination_only" if role == "head_of_agents" else "assigned_work_only",
        }
        if agent is None:
            agent = create_node(
                company_id=company_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                node_type="agent",
                name=spec["name"],
                description=spec["description"],
                status="READY",
                data=agent_data,
            )
            role_to_agent[role] = agent
            graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
        else:
            existing_data = agent.get("data") or {}
            needs_update = (
                agent.get("status") != "READY"
                or any(existing_data.get(key) != value for key, value in agent_data.items())
            )
            if needs_update:
                merged = {**existing_data, **agent_data}
                agent = update_node(
                    company_id=company_id,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    node_id=agent["id"],
                    status="READY",
                    data_patch=merged,
                ) or agent
            role_to_agent[role] = agent
        if role == "head_of_agents":
            _ensure_edge(company_id, tenant_id, actor_id, graph, company_id, agent["id"], "owns")
        else:
            head = role_to_agent.get("head_of_agents")
            if head:
                graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
                _ensure_edge(company_id, tenant_id, actor_id, graph, agent["id"], head["id"], "reports_to")
        graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph

    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
    return {
        "company_id": company_id,
        "agents": [node for node in _nodes(graph) if node["type"] == "agent"],
        "count": len([node for node in _nodes(graph) if node["type"] == "agent"]),
        "runtime_mode": "MOCK" if settings.mock_inference else "LOCAL_MODEL",
    }


def _mock_plan() -> dict[str, Any]:
    return {
        "tasks": [
            {
                "key": "market_validation",
                "title": "Validate the customer problem and market",
                "role": "strategy",
                "description": "Identify target customers, the problem to solve, existing alternatives and the riskiest business assumptions.",
                "acceptance_criteria": ["Target customer segment is described", "Key assumptions and risks are listed", "At least three validation experiments are proposed"],
                "depends_on": [],
            },
            {
                "key": "product_scope",
                "title": "Define the first product release",
                "role": "product",
                "description": "Turn the company goal into a small first-release scope, user journey and testable acceptance criteria.",
                "acceptance_criteria": ["MVP scope is prioritised", "Primary user journey is documented", "Acceptance criteria are testable"],
                "depends_on": ["market_validation"],
            },
            {
                "key": "technical_plan",
                "title": "Prepare the technical delivery plan",
                "role": "technology",
                "description": "Propose an implementation architecture, milestones, quality checks and the smallest viable technical release.",
                "acceptance_criteria": ["Architecture and components are described", "Implementation milestones are listed", "Testing and security checks are identified"],
                "depends_on": ["product_scope"],
            },
            {
                "key": "go_to_market",
                "title": "Prepare customer discovery and launch",
                "role": "marketing",
                "description": "Define positioning, launch messaging, customer discovery channels and a measurable first campaign.",
                "acceptance_criteria": ["Positioning statement is drafted", "Initial channels are prioritised", "Campaign success measures are defined"],
                "depends_on": ["product_scope"],
            },
            {
                "key": "financial_model",
                "title": "Establish the budget and unit economics",
                "role": "finance",
                "description": "Estimate operating costs, pricing assumptions, cash requirements and a founder approval budget.",
                "acceptance_criteria": ["Cost assumptions are visible", "Pricing and unit economics are estimated", "Spending controls are recommended"],
                "depends_on": ["market_validation"],
            },
            {
                "key": "operating_model",
                "title": "Design the operating and customer support model",
                "role": "operations",
                "description": "Define how the product or service will be delivered, supported and measured after launch.",
                "acceptance_criteria": ["Core operating process is documented", "Support responsibilities are clear", "Operational risks and controls are listed"],
                "depends_on": ["product_scope"],
            },
        ]
    }


async def _chat_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 1600,
) -> str:
    settings = get_settings()
    if settings.mock_inference:
        raise RuntimeError("Local model inference is disabled while MOCK_INFERENCE=true")
    payload = {
        "model": settings.reasoning_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{settings.reasoning_api_url.rstrip('/')}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.vllm_api_key}"},
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


def _parse_plan(content: str) -> list[dict[str, Any]]:
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Head of Agents did not return a JSON task plan")
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("Head of Agents returned invalid JSON; no work was created") from exc
    tasks = parsed.get("tasks") if isinstance(parsed, dict) else None
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 10:
        raise ValueError("A plan must contain between 1 and 10 tasks")
    allowed_roles = set(ROLE_SPECS) - {"head_of_agents"}
    result: list[dict[str, Any]] = []
    keys: set[str] = set()
    for index, item in enumerate(tasks):
        if not isinstance(item, dict):
            raise ValueError("Every task in the plan must be an object")
        key = str(item.get("key") or f"task_{index + 1}").strip()[:80]
        role = str(item.get("role") or "").strip().lower()
        title = str(item.get("title") or "").strip()[:160]
        description = str(item.get("description") or "").strip()[:3000]
        criteria = item.get("acceptance_criteria", [])
        dependencies = item.get("depends_on", [])
        if not key or key in keys:
            raise ValueError("Task keys must be non-empty and unique")
        if role not in allowed_roles:
            raise ValueError(f"Unsupported specialist role in plan: {role}")
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
            "role": role,
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

    team = bootstrap_workforce(company_id=company_id, tenant_id=tenant_id, actor_id=actor_id)
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
    company = next(node for node in _nodes(graph) if node["type"] == "company")
    agents = {str((node.get("data") or {}).get("role")): node for node in _nodes(graph) if node["type"] == "agent"}
    head = agents.get("head_of_agents")
    if not head:
        raise RuntimeError("Head of Agents is not available")
    settings = get_settings()
    if settings.mock_inference:
        tasks = _mock_plan()["tasks"]
        planner_mode = "mock-template"
    else:
        system = str((head.get("data") or {}).get("system_prompt") or ROLE_SPECS["head_of_agents"]["system_prompt"])
        prompt = (
            "Create a practical execution plan for this company goal. Return JSON only in this schema: "
            '{"tasks":[{"key":"short_unique_key","title":"...","role":"strategy|product|technology|marketing|operations|finance",'
            '"description":"...","acceptance_criteria":["..."],"depends_on":["earlier_or_other_task_key"]}]}. '
            "Create 3 to 8 tasks, use only the listed roles, make work concrete and measurable, express dependencies, "
            "and do not include external financial actions.\n\n"
            f"Company: {company['name']}\nVision: {(company.get('data') or {}).get('vision', '')}\n"
            f"Mission: {(company.get('data') or {}).get('mission', '')}\n"
            f"Goal: {goal['name']}\nDescription: {goal.get('description', '')}\n"
            f"Available specialists: {', '.join(sorted(set(ROLE_SPECS) - {'head_of_agents'}))}"
        )
        if settings.mcp_enabled:
            from .mcp_client import complete_with_mcp

            plan_response = await complete_with_mcp(
                system_prompt=system,
                user_prompt=prompt,
                role="head_of_agents",
                company_id=company_id,
                tenant_id=tenant_id,
                agent_id=head["id"],
                max_tokens=2400,
            )
        else:
            plan_response = await _chat_completion(
                system_prompt=system,
                user_prompt=prompt,
                temperature=0.15,
                max_tokens=2400,
            )
        tasks = _parse_plan(plan_response)
        planner_mode = "local-model+mcp" if settings.mcp_enabled else "local-model"
    missing = sorted({task["role"] for task in tasks} - set(agents))
    if missing:
        raise RuntimeError(f"Workforce is missing specialist roles: {', '.join(missing)}")

    created: dict[str, dict[str, Any]] = {}
    result_tasks: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        agent = agents[task["role"]]
        work = create_node(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=head["id"],
            node_type="work",
            name=task["title"],
            description=task["description"],
            status="READY",
            data={
                "goal_id": goal_id,
                "task_key": task["key"],
                "sequence": index,
                "assigned_agent_id": agent["id"],
                "assigned_role": task["role"],
                "acceptance_criteria": task["acceptance_criteria"],
                "depends_on_keys": task["depends_on"],
                "planner_agent_id": head["id"],
                "planner_mode": planner_mode,
                "progress": 0,
                "attempt": 0,
            },
        )
        created[task["key"]] = work
        result_tasks.append(work)
        current = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
        _ensure_edge(company_id, tenant_id, head["id"], current, work["id"], agent["id"], "assigned_to")
        current = get_company_graph(company_id=company_id, tenant_id=tenant_id) or current
        _ensure_edge(company_id, tenant_id, head["id"], current, work["id"], goal_id, "contributes_to")
        current = get_company_graph(company_id=company_id, tenant_id=tenant_id) or current
        _ensure_edge(company_id, tenant_id, head["id"], current, agent["id"], goal_id, "contributes_to")
    for task in tasks:
        source = created[task["key"]]
        for dependency_key in task["depends_on"]:
            dependency = created.get(dependency_key)
            if dependency is None:
                raise ValueError(f"Unknown dependency: {dependency_key}")
            current = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
            _ensure_edge(company_id, tenant_id, head["id"], current, source["id"], dependency["id"], "depends_on")
    return {
        "goal_id": goal_id,
        "created": True,
        "planner_agent_id": head["id"],
        "planner_mode": planner_mode,
        "tasks": result_tasks,
        "count": len(result_tasks),
        "message": "The Head of Agents created persisted assignments. Work has not run yet.",
    }


async def _execute_prompt(
    agent: dict[str, Any], prompt: str, *, company_id: str, tenant_id: str
) -> str:
    settings = get_settings()
    data = agent.get("data") or {}
    if settings.mock_inference:
        role = str(data.get("role", "specialist")).replace("_", " ").title()
        return (
            f"# {role} — Development simulation\n\n"
            "This assignment ran in MOCK_INFERENCE mode. No LLM inference or external tool was used.\n\n"
            f"## Assignment context\n{prompt[:1800]}\n\n"
            "## Suggested work product\n"
            "The specialist has acknowledged the assignment and produced this traceable development placeholder. "
            "Configure a reachable local OpenAI-compatible model endpoint and set MOCK_INFERENCE=false for model-generated work.\n"
        )
    system = str(data.get("system_prompt") or "You are a specialist AI employee. Complete the assigned work, state assumptions and provide a practical deliverable.")
    if settings.mcp_enabled:
        from .mcp_client import complete_with_mcp

        return await complete_with_mcp(
            system_prompt=system,
            user_prompt=prompt,
            role=str(data.get("role") or "specialist"),
            company_id=company_id,
            tenant_id=tenant_id,
            agent_id=agent["id"],
            max_tokens=2400,
        )
    return await _chat_completion(system_prompt=system, user_prompt=prompt, temperature=0.25, max_tokens=2400)


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
    if agent is None:
        raise RuntimeError("Assigned agent is not available")
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

    team = bootstrap_workforce(company_id=company_id, tenant_id=tenant_id, actor_id=actor_id)
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id) or graph
    agents = [node for node in _nodes(graph) if node["type"] == "agent" and node["status"] != "DISABLED"]
    requested = meeting_data.get("participant_agent_ids") or []
    if requested:
        agents = [node for node in agents if node["id"] in requested]
    else:
        priority = ["head_of_agents", "strategy", "product", "operations", "finance"]
        by_role = {str((node.get("data") or {}).get("role")): node for node in agents}
        agents = [by_role[role] for role in priority if role in by_role]
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
            f"Your role: {(agent.get('data') or {}).get('role')}\n"
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
            "role": (agent.get("data") or {}).get("role"),
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

    head = next((agent for agent in agents if (agent.get("data") or {}).get("role") == "head_of_agents"), agents[0])
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
    object_id = str(uuid.uuid4())
    filename = f"meeting-{meeting_id}-minutes.md"
    stored = ObjectStore().persist_object(
        key=f"companies/{company_id}/meetings/{object_id}-{filename}",
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
    deliverable = create_node(
        company_id=company_id,
        tenant_id=tenant_id,
        actor_id=head["id"],
        node_type="deliverable",
        name=f"Minutes: {meeting['name']}",
        description="Persisted meeting minutes and turn-by-turn agent discussion.",
        status="STORED",
        data={
            "object_id": stored["object_id"],
            "filename": filename,
            "content_type": stored["content_type"],
            "size_bytes": stored["size_bytes"],
            "sha256": stored["sha256"],
            "download_endpoint": f"/v2/companies/{company_id}/artifacts/{stored['object_id']}",
            "meeting_id": meeting_id,
            "execution_mode": mode,
        },
    )
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
