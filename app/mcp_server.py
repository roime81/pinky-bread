from __future__ import annotations

import logging
from typing import Any

import uvicorn
from pydantic import AnyHttpUrl
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token

from .company_graph import get_company_graph
from .database import check_db_connection
from .durable_runtime import enqueue_job, get_coordination, get_job
from .settings import get_settings

logger = logging.getLogger("pinky_bread.mcp")
settings = get_settings()


class StaticBearerVerifier(TokenVerifier):
    """Development bearer verifier. Replace with Keycloak/OIDC JWT verification for shared use."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if settings.mcp_api_token and token == settings.mcp_api_token:
            scopes = ["company:read", "workforce:enqueue"]
            client_id = "pinky-bread-agent-runtime"
        elif settings.mcp_read_token and token == settings.mcp_read_token:
            scopes = ["company:read"]
            client_id = "pinky-bread-readonly-client"
        else:
            return None
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            resource=settings.mcp_resource_url,
        )


mcp = MCPServer(
    "Pinky Bread Workforce",
    instructions=(
        "Read company context and submit controlled workforce jobs. "
        "This server does not expose payment, external messaging, infrastructure or other consequential side-effect tools."
    ),
    token_verifier=StaticBearerVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(settings.mcp_issuer_url),
        resource_server_url=AnyHttpUrl(settings.mcp_resource_url),
        required_scopes=["company:read"],
        validate_token_resource=True,
    ),
)


def _require_scope(scope: str) -> None:
    token = get_access_token()
    if token is None or scope not in token.scopes:
        raise PermissionError(f"MCP caller is missing the required scope: {scope}")


def _company_graph(company_id: str, tenant_id: str) -> dict[str, Any]:
    _require_scope("company:read")
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise ValueError("Company not found in the supplied tenant context")
    return graph


@mcp.tool()
def company_graph_snapshot(company_id: str, tenant_id: str) -> dict[str, Any]:
    """Read the persisted company graph. Returns company, goal, agent, work, meeting, KPI and deliverable nodes."""
    graph = _company_graph(company_id, tenant_id)
    return {
        "company_id": company_id,
        "version": graph["version"],
        "latest_event_no": graph["latest_event_no"],
        "nodes": graph["nodes"][:500],
        "edges": graph["edges"][:1500],
        "truncated": len(graph["nodes"]) > 500 or len(graph["edges"]) > 1500,
    }


@mcp.tool()
def list_company_goals(company_id: str, tenant_id: str) -> list[dict[str, Any]]:
    """List current company goals, including state and progress."""
    graph = _company_graph(company_id, tenant_id)
    return [
        {
            "id": node["id"],
            "name": node["name"],
            "description": node["description"],
            "status": node["status"],
            "progress": (node.get("data") or {}).get("progress", 0),
        }
        for node in graph["nodes"]
        if node["type"] == "goal"
    ]


@mcp.tool()
def list_goal_work(company_id: str, tenant_id: str, goal_id: str) -> list[dict[str, Any]]:
    """List work assignments for one company goal, including status, owner and dependencies."""
    graph = _company_graph(company_id, tenant_id)
    if goal_id not in {node["id"] for node in graph["nodes"] if node["type"] == "goal"}:
        raise ValueError("Goal not found in the supplied company")
    assignments = {edge["source"]: edge["target"] for edge in graph["edges"] if edge["relationship"] == "assigned_to"}
    return [
        {
            "id": node["id"],
            "name": node["name"],
            "description": node["description"],
            "status": node["status"],
            "assigned_agent_id": assignments.get(node["id"]),
            "data": node.get("data") or {},
        }
        for node in graph["nodes"]
        if node["type"] == "work" and (node.get("data") or {}).get("goal_id") == goal_id
    ]


@mcp.tool()
def get_workforce_job(company_id: str, tenant_id: str, job_id: str) -> dict[str, Any]:
    """Read the durable status, retries, result and error for a company workforce job."""
    job = get_job(job_id=job_id, company_id=company_id, tenant_id=tenant_id)
    if job is None:
        raise ValueError("Workforce job not found")
    return job


@mcp.tool()
def queue_goal_plan(company_id: str, tenant_id: str, goal_id: str, actor_id: str) -> dict[str, Any]:
    """Queue a Head-of-Agents goal planning job. The operation is idempotent while a matching job is active."""
    _require_scope("workforce:enqueue")
    graph = _company_graph(company_id, tenant_id)
    if goal_id not in {node["id"] for node in graph["nodes"] if node["type"] == "goal"}:
        raise ValueError("Goal not found in the supplied company")
    return enqueue_job(
        company_id=company_id,
        tenant_id=tenant_id,
        kind="goal_plan",
        target_id=goal_id,
        actor_id=actor_id,
        payload={"source": "mcp", "requested_by_agent": actor_id},
    )


@mcp.tool()
def queue_goal_execution(company_id: str, tenant_id: str, goal_id: str, actor_id: str) -> dict[str, Any]:
    """Queue goal execution only when the founder has enabled AUTO_EXECUTE coordination for this company."""
    _require_scope("workforce:enqueue")
    graph = _company_graph(company_id, tenant_id)
    if goal_id not in {node["id"] for node in graph["nodes"] if node["type"] == "goal"}:
        raise ValueError("Goal not found in the supplied company")
    policy = get_coordination(company_id=company_id, tenant_id=tenant_id)
    if not policy or not policy["enabled"] or policy["mode"] != "AUTO_EXECUTE":
        raise PermissionError("Founder approval required: enable AUTO_EXECUTE coordination before agents can queue goal execution")
    return enqueue_job(
        company_id=company_id,
        tenant_id=tenant_id,
        kind="goal_execution",
        target_id=goal_id,
        actor_id=actor_id,
        payload={"source": "mcp", "requested_by_agent": actor_id, "policy_mode": policy["mode"]},
    )


def main() -> None:
    check_db_connection()
    if not settings.mcp_api_token:
        raise RuntimeError("MCP_API_TOKEN is required before the MCP server can start")
    transport_security = TransportSecuritySettings(
        allowed_hosts=[
            f"mcp:{settings.mcp_port}",
            f"localhost:{settings.mcp_port}",
            f"127.0.0.1:{settings.mcp_port}",
        ],
        allowed_origins=[],
    )
    uvicorn.run(
        mcp.streamable_http_app(transport_security=transport_security),
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
