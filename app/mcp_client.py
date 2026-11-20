from __future__ import annotations

import json
from typing import Any

import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from .settings import get_settings
from .model_providers import normalize_chat_completions_base_url


ROLE_TOOL_ALLOWLIST: dict[str, set[str]] = {
    "head_of_agents": {
        "company_graph_snapshot",
        "list_company_goals",
        "list_goal_work",
        "get_workforce_job",
        "queue_goal_plan",
        "queue_goal_execution",
    },
    "strategy": {"company_graph_snapshot", "list_company_goals", "list_goal_work"},
    "product": {"company_graph_snapshot", "list_company_goals", "list_goal_work"},
    "technology": {"company_graph_snapshot", "list_company_goals", "list_goal_work"},
    "marketing": {"company_graph_snapshot", "list_company_goals", "list_goal_work"},
    "operations": {"company_graph_snapshot", "list_company_goals", "list_goal_work"},
    "finance": {"company_graph_snapshot", "list_company_goals", "list_goal_work"},
    "specialist": {"company_graph_snapshot", "list_company_goals", "list_goal_work"},
}


def _tool_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
    if not isinstance(schema, dict):
        schema = {}
    schema = json.loads(json.dumps(schema))
    properties = schema.setdefault("properties", {})
    for trusted_field in ("company_id", "tenant_id", "actor_id"):
        properties.pop(trusted_field, None)
    schema["required"] = [
        field for field in schema.get("required", [])
        if field not in {"company_id", "tenant_id", "actor_id"}
    ]
    schema.setdefault("type", "object")
    return schema


def _tool_result_text(result: Any) -> str:
    if getattr(result, "is_error", False) or getattr(result, "isError", False):
        raise RuntimeError("MCP tool returned an error")
    parts = []
    for item in getattr(result, "content", []) or []:
        value = getattr(item, "text", None)
        if value:
            parts.append(value)
    if parts:
        return "\n".join(parts)
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if structured is not None:
        return json.dumps(structured, ensure_ascii=False, default=str)
    return str(result)


async def complete_with_mcp(
    *,
    system_prompt: str,
    user_prompt: str,
    role: str,
    company_id: str,
    tenant_id: str,
    agent_id: str,
    max_tokens: int = 2400,
    model_name: str | None = None,
    api_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """Call a configured OpenAI-compatible provider and expose only role-allow-listed MCP tools."""
    settings = get_settings()
    if not settings.mcp_enabled:
        raise RuntimeError("MCP is disabled")
    if not settings.mcp_api_token:
        raise RuntimeError("MCP_API_TOKEN is required when MCP_ENABLED=true")
    allowed = ROLE_TOOL_ALLOWLIST.get(role, set())
    if not allowed:
        raise PermissionError(f"No MCP tools are granted to agent role: {role}")

    # Least privilege: only the Head of Agents receives enqueue scope.
    bearer = settings.mcp_api_token if role == "head_of_agents" else settings.mcp_read_token
    if not bearer:
        raise RuntimeError("The matching MCP bearer token is not configured for this agent role")
    headers = {"Authorization": f"Bearer {bearer}"}
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    endpoint = f"{normalize_chat_completions_base_url(api_url or settings.reasoning_api_url)}/chat/completions"
    model_tools: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(30.0, read=300.0),
    ) as http_client:
        transport = streamable_http_client(
            url=settings.mcp_server_url,
            http_client=http_client,
        )
        async with Client(transport) as session:
            discovered = await session.list_tools()
            available = {
                tool.name: tool
                for tool in discovered.tools
                if tool.name in allowed
            }
            model_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": _tool_schema(tool),
                    },
                }
                for tool in available.values()
            ]
            async with httpx.AsyncClient(timeout=180) as client:
                for _ in range(max(1, min(settings.mcp_max_tool_rounds, 8))):
                    payload: dict[str, Any] = {
                        "model": model_name or settings.reasoning_model,
                        "messages": messages,
                        "temperature": 0.25,
                        "max_tokens": max_tokens,
                    }
                    if model_tools:
                        payload["tools"] = model_tools
                    response = await client.post(
                        endpoint,
                        json=payload,
                        headers={"Authorization": f"Bearer {api_key or settings.vllm_api_key}"},
                    )
                    response.raise_for_status()
                    body = response.json()
                    try:
                        message = body["choices"][0]["message"]
                    except (KeyError, IndexError, TypeError) as exc:
                        raise RuntimeError("The selected model provider returned an unsupported chat-completion response") from exc
                    tool_calls = message.get("tool_calls") or []
                    content = message.get("content") or ""
                    if not tool_calls:
                        if isinstance(content, list):
                            content = "\n".join(
                                str(part.get("text", ""))
                                for part in content if isinstance(part, dict)
                            )
                        if not isinstance(content, str) or not content.strip():
                            raise RuntimeError("Local model returned an empty final response")
                        return content.strip()

                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    })
                    for call in tool_calls:
                        function = call.get("function") or {}
                        name = function.get("name")
                        if name not in available or name not in allowed:
                            raise PermissionError(f"Model requested an ungranted MCP tool: {name}")
                        try:
                            arguments = json.loads(function.get("arguments") or "{}")
                        except json.JSONDecodeError as exc:
                            raise ValueError(f"Model returned invalid arguments for MCP tool {name}") from exc
                        if not isinstance(arguments, dict):
                            raise ValueError(f"MCP tool arguments must be an object: {name}")
                        # Identity and tenancy are injected by the runtime, never trusted from model output.
                        safe_arguments = {
                            **{k: v for k, v in arguments.items() if k not in {"company_id", "tenant_id", "actor_id"}},
                            "company_id": company_id,
                            "tenant_id": tenant_id,
                            "actor_id": agent_id,
                        }
                        result = await session.call_tool(name, safe_arguments)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call.get("id", ""),
                            "content": _tool_result_text(result),
                        })
                raise RuntimeError("Local model exceeded the configured MCP tool-call limit")
