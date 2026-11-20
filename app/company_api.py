from __future__ import annotations

from typing import Any, Literal
import asyncio
import json
import re
import uuid
import httpx
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from redis.asyncio import Redis
from pydantic import BaseModel, Field

from .settings import get_settings
from .model_providers import PROVIDER_DEFAULTS, model_provider_status
from .object_store import ObjectStore
from .durable_runtime import (
    enqueue_job,
    get_job,
    list_jobs,
    cancel_job,
    configure_coordination,
    get_coordination,
)

from .agent_messaging import (
    get_agent_conversation,
    list_agent_conversations,
    resolve_agent_discussion,
    stream_agent_discussion,
)

from .workforce import (
    bootstrap_workforce,
    plan_goal,
    execute_goal,
    execute_task,
    convene_meeting,
    record_kpi_measurement,
    chat_with_workforce,
)

from .company_graph import (
    NODE_TYPES,
    RELATIONSHIPS,
    create_company,
    create_edge,
    create_node,
    create_agent_node,
    update_agent_node,
    archive_agent_node,
    update_node,
    get_company_graph,
    list_companies,
    list_company_events,
    verify_event_chain,
)

router = APIRouter(prefix="/v2", tags=["company graph"])

def _validated_model_configuration(value: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(value or {})
    secret_fields = {"api_key", "apikey", "secret", "token", "access_token", "authorization"}
    if secret_fields.intersection(key.lower() for key in config):
        raise HTTPException(
            422,
            "Provider API keys must be configured on the server in .env; they cannot be stored in agent profiles.",
        )
    allowed = {"provider", "model_name", "endpoint", "temperature", "max_tokens"}
    unknown = set(config) - allowed
    if unknown:
        raise HTTPException(422, f"Unsupported model configuration fields: {', '.join(sorted(unknown))}")
    provider = str(config.get("provider") or get_settings().model_provider).strip().lower()
    if provider not in PROVIDER_DEFAULTS:
        raise HTTPException(422, f"Unsupported model provider '{provider}'.")
    config["provider"] = provider
    model_name = config.get("model_name")
    if model_name is not None:
        if not isinstance(model_name, str) or len(model_name.strip()) > 160:
            raise HTTPException(422, "Model identifier must be a string of at most 160 characters.")
        config["model_name"] = model_name.strip()
    endpoint = config.get("endpoint")
    if endpoint:
        if not isinstance(endpoint, str) or len(endpoint) > 500 or not endpoint.startswith(("http://", "https://")):
            raise HTTPException(422, "Model API endpoint must be a valid HTTP(S) URL of at most 500 characters.")
        config["endpoint"] = endpoint.strip()
    if "max_tokens" in config:
        try:
            config["max_tokens"] = max(1, min(32000, int(config["max_tokens"])))
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "max_tokens must be an integer.") from exc
    if "temperature" in config:
        try:
            config["temperature"] = max(0.0, min(2.0, float(config["temperature"])))
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "temperature must be a number between 0 and 2.") from exc
    return config



class CompanyCreate(BaseModel):
    tenant_id: str = Field(default="demo-tenant", min_length=2, max_length=120)
    owner_id: str = Field(default="demo-user", min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=240)
    vision: str = Field(default="", max_length=4000)
    mission: str = Field(default="", max_length=4000)
    values: list[str] = Field(default_factory=list, max_length=30)


class GraphNodeCreate(BaseModel):
    tenant_id: str = Field(default="demo-tenant", min_length=2, max_length=120)
    actor_id: str = Field(default="demo-user", min_length=2, max_length=120)
    node_type: str
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=8000)
    status: str = Field(default="PLANNED", min_length=2, max_length=40)
    data: dict[str, Any] = Field(default_factory=dict)


class GraphNodeUpdate(BaseModel):
    tenant_id: str = Field(default="demo-tenant", min_length=2, max_length=120)
    actor_id: str = Field(default="demo-user", min_length=2, max_length=120)
    name: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=8000)
    status: str | None = Field(default=None, min_length=2, max_length=40)
    data_patch: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeCreate(BaseModel):
    tenant_id: str = Field(default="demo-tenant", min_length=2, max_length=120)
    actor_id: str = Field(default="demo-user", min_length=2, max_length=120)
    source_node_id: str = Field(min_length=36, max_length=36)
    target_node_id: str = Field(min_length=36, max_length=36)
    relationship: str
    data: dict[str, Any] = Field(default_factory=dict)


class WorkforceAction(BaseModel):
    tenant_id: str = Field(default="demo-tenant", min_length=2, max_length=120)
    actor_id: str = Field(default="demo-user", min_length=2, max_length=120)


class AgentCreateRequest(WorkforceAction):
    name: str = Field(min_length=2, max_length=120)
    role: str = Field(min_length=2, max_length=160)
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)
    skills: list[str] = Field(default_factory=list, max_length=30)
    responsibilities: list[str] = Field(default_factory=list, max_length=20)
    system_prompt: str = Field(default="", max_length=8000)
    seniority_level: int = Field(default=3, ge=1, le=10)
    authority: Literal["SPECIALIST", "COORDINATOR"] = "SPECIALIST"
    model_configuration: dict[str, Any] = Field(default_factory=dict)
    manager_id: str | None = Field(default=None, min_length=36, max_length=36)


class AgentUpdateRequest(WorkforceAction):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    role: str | None = Field(default=None, min_length=2, max_length=160)
    title: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    skills: list[str] | None = Field(default=None, max_length=30)
    responsibilities: list[str] | None = Field(default=None, max_length=20)
    system_prompt: str | None = Field(default=None, max_length=8000)
    seniority_level: int | None = Field(default=None, ge=1, le=10)
    authority: Literal["SPECIALIST", "COORDINATOR"] | None = None
    model_configuration: dict[str, Any] | None = None
    manager_id: str | None = Field(default=None, min_length=36, max_length=36)
    status: Literal["ACTIVE", "PAUSED"] | None = None



class CompanyChatRequest(WorkforceAction):
    message: str = Field(min_length=1, max_length=12000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)


class AgentConversationStreamRequest(WorkforceAction):
    message: str = Field(min_length=1, max_length=12000)
    max_turns: int = Field(default=6, ge=2, le=12)

class WorkExecutionRequest(WorkforceAction):
    retry: bool = False


class KpiMeasurementRequest(WorkforceAction):
    actual_value: float
    source: str = Field(min_length=2, max_length=240)
    evidence: str = Field(default="", max_length=2000)


class GoalJobRequest(WorkforceAction):
    kind: Literal["goal_plan", "goal_execution"]
    idempotency_key: str | None = Field(default=None, max_length=180)


class CoordinationRequest(WorkforceAction):
    enabled: bool = True
    mode: Literal["PLAN_ONLY", "AUTO_EXECUTE"] = "PLAN_ONLY"
    interval_seconds: int = Field(default=300, ge=60, le=86400)


class TargetJobRequest(WorkforceAction):
    idempotency_key: str | None = Field(default=None, max_length=180)


@router.get("/capabilities")
def company_graph_capabilities() -> dict[str, Any]:
    return {
        "version": "2.0.0-alpha.4",
        "node_types": sorted(NODE_TYPES | {"company"}),
        "relationships": sorted(RELATIONSHIPS),
        "persistence": "PostgreSQL/SQLAlchemy graph records and event history",
        "live_notifications": "Valkey Pub/Sub; PostgreSQL remains authoritative",
        "object_storage": "Local filesystem or S3-compatible SeaweedFS with PostgreSQL metadata",
        "agent_management": ["founder-defined agent creation", "profile and prompt editing", "per-agent commercial and local LLM provider settings", "seniority promotion/demotion", "coordinator authority", "manager reporting lines", "archive with history preservation"],
        "workforce": ["dynamic agent delegation", "goal decomposition", "assigned work execution", "meeting facilitation", "KPI measurement history"],
        "inference": "Per-agent Ollama, vLLM, OpenAI-compatible, OpenAI API or Gemini API provider selection",
        "orchestration": "LangGraph StateGraph with PostgreSQL AsyncPostgresSaver checkpoints",
        "durable_jobs": "PostgreSQL job records, worker leases, retries, cancellation and recovery",
        "coordination": "Founder-controlled recurring PLAN_ONLY or AUTO_EXECUTE schedules",
        "mcp": "Official MCP Python SDK v2 Streamable HTTP; bearer scopes for development/internal use",
        "source_of_truth": "PostgreSQL; Valkey is only a best-effort coordination signal",
    }



@router.get("/model-providers")
def model_providers_endpoint() -> dict[str, Any]:
    settings = get_settings()
    return {
        "providers": model_provider_status(settings=settings),
        "default_provider": settings.model_provider,
        "credentials_storage": "server_environment_only",
        "credential_help": "Set OPENAI_API_KEY or GEMINI_API_KEY in .env, then recreate the API and worker containers.",
    }


@router.post("/companies", status_code=201)
def create_company_endpoint(request: CompanyCreate) -> dict[str, Any]:
    return create_company(
        tenant_id=request.tenant_id,
        owner_id=request.owner_id,
        name=request.name,
        vision=request.vision,
        mission=request.mission,
        values=request.values,
    )


@router.get("/companies")
def list_companies_endpoint(
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    return {"companies": list_companies(tenant_id=tenant_id)}


@router.get("/companies/{company_id}/graph")
def get_graph_endpoint(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")
    return graph


@router.post("/companies/{company_id}/nodes", status_code=201)
def create_node_endpoint(company_id: str, request: GraphNodeCreate) -> dict[str, Any]:
    if request.node_type not in NODE_TYPES:
        raise HTTPException(422, f"Unsupported node type. Allowed: {', '.join(sorted(NODE_TYPES))}")
    try:
        node = create_node(
            company_id=company_id,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            node_type=request.node_type,
            name=request.name,
            description=request.description,
            status=request.status,
            data=request.data,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if node is None:
        raise HTTPException(404, "Company not found")
    return node


@router.patch("/companies/{company_id}/nodes/{node_id}")
def update_node_endpoint(company_id: str, node_id: str, request: GraphNodeUpdate) -> dict[str, Any]:
    node = update_node(
        company_id=company_id,
        tenant_id=request.tenant_id,
        actor_id=request.actor_id,
        node_id=node_id,
        name=request.name,
        description=request.description,
        status=request.status,
        data_patch=request.data_patch,
    )
    if node is None:
        raise HTTPException(404, "Company graph node not found")
    return node


@router.post("/companies/{company_id}/edges", status_code=201)
def create_edge_endpoint(company_id: str, request: GraphEdgeCreate) -> dict[str, Any]:
    if request.relationship not in RELATIONSHIPS:
        raise HTTPException(422, f"Unsupported relationship. Allowed: {', '.join(sorted(RELATIONSHIPS))}")
    try:
        edge = create_edge(
            company_id=company_id,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            source_node_id=request.source_node_id,
            target_node_id=request.target_node_id,
            relationship=request.relationship,
            data=request.data,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if edge is None:
        raise HTTPException(404, "Company not found")
    return edge


@router.get("/companies/{company_id}/events")
def list_events_endpoint(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
    after_event_no: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    events = list_company_events(
        company_id=company_id,
        tenant_id=tenant_id,
        after_event_no=after_event_no,
        limit=limit,
    )
    if events is None:
        raise HTTPException(404, "Company not found")
    return {"events": events, "count": len(events)}


@router.get("/companies/{company_id}/events/verify")
def verify_events_endpoint(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    result = verify_event_chain(company_id=company_id, tenant_id=tenant_id)
    if result is None:
        raise HTTPException(404, "Company not found")
    return result


@router.get("/companies/{company_id}/events/stream")
async def stream_company_events(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
):
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")

    async def event_stream():
        client = Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=2,
        )
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(f"pinky-bread:company:{company_id}")
            yield "event: connected\ndata: {}\n\n"
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    payload = message.get("data", "{}")
                    yield f"event: graph_event\ndata: {payload}\n\n"
                else:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        except Exception:
            # PostgreSQL event history remains available through the REST endpoint.
            yield "event: broker_unavailable\ndata: notification service unavailable\n\n"
        finally:
            try:
                await pubsub.aclose()
                await client.aclose()
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/companies/{company_id}/artifacts", status_code=201)
async def upload_company_artifact(
    company_id: str,
    file: UploadFile = File(...),
    tenant_id: str = Form(default="demo-tenant", min_length=2, max_length=120),
    actor_id: str = Form(default="demo-user", min_length=2, max_length=120),
    kind: str = Form(default="document"),
    title: str = Form(default="", max_length=240),
    related_node_id: str | None = Form(default=None),
):
    if kind not in {"document", "deliverable"}:
        raise HTTPException(422, "Artifact kind must be document or deliverable")

    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")
    if related_node_id and related_node_id not in {node["id"] for node in graph["nodes"]}:
        raise HTTPException(404, "Related graph node not found in this company")

    settings = get_settings()
    raw = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if not raw:
        raise HTTPException(400, "Uploaded file is empty")
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, f"File exceeds the {settings.max_upload_mb} MB upload limit")

    filename = Path(file.filename or "upload.bin").name
    safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename).strip("._")[:255] or "upload.bin"
    content_type = (file.content_type or "application/octet-stream")[:200]
    object_key = f"companies/{company_id}/{uuid.uuid4()}/{safe_filename}"

    try:
        stored = ObjectStore().persist_object(
            key=object_key,
            content=raw,
            content_type=content_type,
            tenant_id=tenant_id,
            company_id=company_id,
            owner_type="company",
            owner_id=company_id,
            filename=safe_filename,
            created_by=actor_id,
            metadata={"kind": kind},
        )
        node = create_node(
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            node_type=kind,
            name=title.strip() or safe_filename,
            description=f"Stored {kind} · {len(raw)} bytes",
            status="STORED",
            data={
                "object_id": stored["object_id"],
                "filename": safe_filename,
                "content_type": content_type,
                "size_bytes": len(raw),
                "sha256": stored["sha256"],
                "download_endpoint": f"/v2/companies/{company_id}/artifacts/{stored['object_id']}",
            },
        )
        if node is None:
            raise HTTPException(404, "Company not found")
        if kind == "deliverable" and related_node_id:
            create_edge(
                company_id=company_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                source_node_id=related_node_id,
                target_node_id=node["id"],
                relationship="produces",
                data={"object_id": stored["object_id"]},
            )
        elif kind == "document" and related_node_id:
            create_edge(
                company_id=company_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                source_node_id=node["id"],
                target_node_id=related_node_id,
                relationship="informs",
                data={"object_id": stored["object_id"]},
            )
        else:
            create_edge(
                company_id=company_id,
                tenant_id=tenant_id,
                actor_id=actor_id,
                source_node_id=company_id,
                target_node_id=node["id"],
                relationship="owns",
                data={"object_id": stored["object_id"]},
            )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, "Unable to persist company artifact") from exc

    return {
        "artifact": {
            "object_id": stored["object_id"],
            "node_id": node["id"],
            "kind": kind,
            "filename": safe_filename,
            "content_type": content_type,
            "size_bytes": stored["size_bytes"],
            "sha256": stored["sha256"],
            "storage_backend": stored["storage_backend"],
            "created_at": stored["created_at"],
        }
    }


@router.get("/companies/{company_id}/artifacts")
def list_company_artifacts(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")
    records = ObjectStore().list_records(tenant_id=tenant_id, company_id=company_id, limit=limit)
    return {
        "artifacts": [
            {
                "object_id": record["object_id"],
                "filename": record["filename"],
                "content_type": record["content_type"],
                "size_bytes": record["size_bytes"],
                "sha256": record["sha256"],
                "storage_backend": record["storage_backend"],
                "created_by": record["created_by"],
                "created_at": record["created_at"],
            }
            for record in records
        ]
    }


@router.get("/companies/{company_id}/artifacts/{object_id}")
def download_company_artifact(
    company_id: str,
    object_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
):
    record = ObjectStore().get_record(
        object_id=object_id,
        tenant_id=tenant_id,
        company_id=company_id,
    )
    if record is None:
        raise HTTPException(404, "Artifact not found")
    try:
        content = ObjectStore().get_bytes(record["object_key"], backend=record["storage_backend"])
    except FileNotFoundError as exc:
        raise HTTPException(404, "Artifact bytes are unavailable") from exc
    return Response(
        content=content,
        media_type=record["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{record["filename"]}"'},
    )




@router.get("/runtime")
async def company_runtime_status() -> dict[str, Any]:
    settings = get_settings()
    status: dict[str, Any] = {
        "mock_inference": settings.mock_inference,
        "provider": settings.model_provider,
        "model": settings.reasoning_model,
        "model_reachable": False,
        "model_available": False,
        "model_error": None,
        "mcp_enabled": settings.mcp_enabled,
        "mcp_configured": bool(settings.mcp_server_url and settings.mcp_api_token and settings.mcp_read_token),
    }
    if settings.mock_inference:
        status["model_error"] = "MOCK_INFERENCE=true; live inference is disabled."
        return status
    endpoint = settings.reasoning_api_url.rstrip("/")
    service_root = endpoint[:-3] if endpoint.endswith("/v1") else endpoint
    is_ollama = settings.model_provider == "ollama" or "ollama" in endpoint.lower()
    probe_url = f"{service_root}/api/tags" if is_ollama else f"{endpoint}/models"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=2.0)) as client:
            response = await client.get(probe_url, headers={"Authorization": f"Bearer {settings.vllm_api_key}"})
            response.raise_for_status()
            payload = response.json()
        status["model_reachable"] = True
        if is_ollama:
            names = {
                str(item.get("name") or item.get("model") or "")
                for item in payload.get("models", [])
                if isinstance(item, dict)
            }
            model_base = settings.reasoning_model.split(":")[0]
            status["model_available"] = any(
                name == settings.reasoning_model or name.split(":")[0] == model_base
                for name in names
            )
        else:
            entries = payload.get("data", []) if isinstance(payload, dict) else []
            names = {str(item.get("id", "")) for item in entries if isinstance(item, dict)}
            status["model_available"] = not names or settings.reasoning_model in names
        if not status["model_available"]:
            status["model_error"] = f"Model '{settings.reasoning_model}' is not present in the provider model list."
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        status["model_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return status


@router.post("/companies/{company_id}/chat")
async def company_chat_endpoint(company_id: str, request: CompanyChatRequest) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=request.tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")
    agents = [
        node for node in graph["nodes"]
        if node["type"] == "agent" and node.get("status") not in {"ARCHIVED", "DISABLED", "PAUSED"}
    ]
    if not agents:
        raise HTTPException(409, "Create an AI employee before starting a company conversation")
    discussion = resolve_agent_discussion(agents, request.message)
    if discussion is not None:
        events = [
            event async for event in stream_agent_discussion(
                company_id=company_id,
                tenant_id=request.tenant_id,
                actor_id=request.actor_id,
                company=next(node for node in graph["nodes"] if node["type"] == "company"),
                agents=agents,
                initiator=discussion["initiator"],
                recipients=discussion["recipients"],
                founder_message=request.message,
                max_turns=discussion["max_turns"],
            )
        ]
        complete = next((event.get("conversation") for event in reversed(events) if event.get("type") == "complete"), None)
        messages = [event["message"] for event in events if event.get("type") == "message"]
        summary = next((item for item in reversed(messages) if item.get("message_kind") == "FOUNDER_SUMMARY"), None)
        return {
            "reply": summary["content"] if summary else "The discussion completed.",
            "responses": [
                {
                    "agent_id": item["sender_agent_id"],
                    "name": item["sender_name"],
                    "role": next((_agent.get("data", {}).get("role", "AI employee") for _agent in agents if _agent["id"] == item["sender_agent_id"]), "AI employee"),
                    "reply": item["content"],
                    "recipient_name": item.get("recipient_name"),
                    "message_kind": item.get("message_kind"),
                }
                for item in messages
            ],
            "conversation_id": complete.get("conversation_id") if complete else None,
            "conversation": complete,
            "mode": "LIVE_AGENT_TO_AGENT",
            "agent": {"id": discussion["initiator"]["id"], "name": discussion["initiator"]["name"], "role": discussion["initiator"].get("data", {}).get("role", "AI employee")},
        }

    history = []
    for item in request.history[-12:]:
        role = item.get("role")
        content = item.get("content", "")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            history.append({"role": role, "content": content[:4000]})
    company = next(node for node in graph["nodes"] if node["type"] == "company")
    try:
        responses = await chat_with_workforce(
            agents=agents,
            company=company,
            message=request.message,
            history=history,
            company_id=company_id,
            tenant_id=request.tenant_id,
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Model or MCP request failed: {type(exc).__name__}: {str(exc)[:300]}") from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(502, f"AI runtime error: {str(exc)[:300]}") from exc
    except Exception as exc:
        raise HTTPException(502, f"AI runtime integration failed: {type(exc).__name__}: {str(exc)[:300]}") from exc
    if not responses:
        raise HTTPException(503, "No active AI employee was available to respond")
    reply = "\n\n".join(f"**{item['name']} · {item['role']}**\n{item['reply']}" for item in responses)
    first = next((item for item in agents if item["id"] == responses[0]["agent_id"]), agents[0])
    return {
        "reply": reply,
        "responses": responses,
        "mode": "LIVE_MODEL_WITH_MCP" if get_settings().mcp_enabled else "LIVE_MODEL",
        "agent": {
            "id": first["id"],
            "name": first["name"],
            "role": (first.get("data") or {}).get("role", "AI employee"),
            "model": (first.get("data") or {}).get("model_configuration", {}).get("model_name"),
        },
    }




@router.get("/companies/{company_id}/conversations")
def list_agent_conversations_endpoint(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")
    conversations = list_agent_conversations(company_id=company_id, tenant_id=tenant_id)
    return {"conversations": conversations, "count": len(conversations)}


@router.get("/companies/{company_id}/conversations/{conversation_id}")
def get_agent_conversation_endpoint(
    company_id: str,
    conversation_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    conversation = get_agent_conversation(
        company_id=company_id, tenant_id=tenant_id, conversation_id=conversation_id
    )
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    return conversation


@router.post("/companies/{company_id}/conversations/stream")
async def stream_agent_conversation_endpoint(
    company_id: str, request: AgentConversationStreamRequest
):
    graph = get_company_graph(company_id=company_id, tenant_id=request.tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")
    agents = [
        node for node in graph["nodes"]
        if node["type"] == "agent" and node.get("status") not in {"ARCHIVED", "DISABLED", "PAUSED"}
    ]
    resolution = resolve_agent_discussion(agents, request.message)
    if resolution is None:
        raise HTTPException(
            422,
            "To start an agent discussion, mention the initiating agent and at least one colleague "
            "(or mention one colleague when a coordinator is configured), and include an instruction "
            "such as discuss, talk, ask, message or say hello.",
        )
    company = next(node for node in graph["nodes"] if node["type"] == "company")

    async def event_stream():
        iterator = stream_agent_discussion(
            company_id=company_id,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            company=company,
            agents=agents,
            initiator=resolution["initiator"],
            recipients=resolution["recipients"],
            founder_message=request.message,
            max_turns=min(request.max_turns, resolution["max_turns"])
            if resolution["max_turns"] == 2 else request.max_turns,
        ).__aiter__()
        pending = None
        conversation_id = None
        try:
            pending = asyncio.create_task(anext(iterator))
            while True:
                done, _ = await asyncio.wait({pending}, timeout=15.0)
                if not done:
                    heartbeat = {"type": "heartbeat", "conversation_id": conversation_id}
                    yield f"data: {json.dumps(heartbeat)}\n\n"
                    continue
                try:
                    event = pending.result()
                except StopAsyncIteration:
                    break
                conversation_id = (
                    event.get("conversation_id")
                    or (event.get("conversation") or {}).get("conversation_id")
                    or conversation_id
                )
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
                pending = asyncio.create_task(anext(iterator))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            payload = {"type": "error", "error": f"{type(exc).__name__}: {str(exc)[:1000]}"}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            try:
                await iterator.aclose()
            except RuntimeError:
                # The iterator may already have completed or been closed.
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/companies/{company_id}/agents")
def list_company_agents_endpoint(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")
    agents = [node for node in graph["nodes"] if node["type"] == "agent"]
    return {"agents": agents, "count": len(agents)}


@router.post("/companies/{company_id}/agents", status_code=201)
def create_company_agent_endpoint(company_id: str, request: AgentCreateRequest) -> dict[str, Any]:
    data = {
        "role": request.role.strip(),
        "title": request.title.strip(),
        "skills": [item.strip() for item in request.skills if item.strip()],
        "responsibilities": [item.strip() for item in request.responsibilities if item.strip()],
        "system_prompt": request.system_prompt.strip(),
        "seniority_level": request.seniority_level,
        "authority": request.authority,
        "runtime_status": "READY",
        "created_via": "company_agent_management",
        "model_configuration": _validated_model_configuration(request.model_configuration),
    }
    try:
        node = create_agent_node(
            company_id=company_id,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            name=request.name.strip(),
            description=request.description.strip(),
            data=data,
            manager_id=request.manager_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if node is None:
        raise HTTPException(404, "Company not found")
    return node


@router.patch("/companies/{company_id}/agents/{agent_id}")
def update_company_agent_endpoint(
    company_id: str, agent_id: str, request: AgentUpdateRequest
) -> dict[str, Any]:
    fields = request.model_fields_set
    patch: dict[str, Any] = {}
    for key in ("role", "title", "skills", "responsibilities", "system_prompt", "seniority_level", "authority", "model_configuration"):
        if key in fields:
            value = getattr(request, key)
            patch[key] = _validated_model_configuration(value) if key == "model_configuration" and value is not None else ([item.strip() for item in value if item.strip()] if key in {"skills", "responsibilities"} and value is not None else (value.strip() if key in {"role", "title", "system_prompt"} and value is not None else value))
    try:
        node = update_agent_node(
            company_id=company_id,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            node_id=agent_id,
            name=request.name.strip() if request.name is not None else None,
            description=request.description.strip() if request.description is not None else None,
            data_patch=patch,
            status=request.status,
            manager_id=request.manager_id,
            update_manager="manager_id" in fields,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if node is None:
        raise HTTPException(404, "Agent not found")
    return node


@router.post("/companies/{company_id}/agents/{agent_id}/promote")
def promote_company_agent_endpoint(company_id: str, agent_id: str, request: WorkforceAction) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=request.tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")
    agent = next((node for node in graph["nodes"] if node["id"] == agent_id and node["type"] == "agent"), None)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    level = int((agent.get("data") or {}).get("seniority_level", 3))
    if level >= 10:
        raise HTTPException(409, "Agent is already at the highest seniority level")
    return update_agent_node(
        company_id=company_id,
        tenant_id=request.tenant_id,
        actor_id=request.actor_id,
        node_id=agent_id,
        data_patch={"seniority_level": level + 1},
    )


@router.post("/companies/{company_id}/agents/{agent_id}/demote")
def demote_company_agent_endpoint(company_id: str, agent_id: str, request: WorkforceAction) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=request.tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")
    agent = next((node for node in graph["nodes"] if node["id"] == agent_id and node["type"] == "agent"), None)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    level = int((agent.get("data") or {}).get("seniority_level", 3))
    if level <= 1:
        raise HTTPException(409, "Agent is already at the lowest seniority level")
    return update_agent_node(
        company_id=company_id,
        tenant_id=request.tenant_id,
        actor_id=request.actor_id,
        node_id=agent_id,
        data_patch={"seniority_level": level - 1},
    )


@router.delete("/companies/{company_id}/agents/{agent_id}")
def remove_company_agent_endpoint(
    company_id: str, agent_id: str, request: WorkforceAction
) -> dict[str, Any]:
    try:
        node = archive_agent_node(
            company_id=company_id,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            node_id=agent_id,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if node is None:
        raise HTTPException(404, "Agent not found")
    return {"removed": True, "preserved_history": True, "agent": node}


@router.post("/companies/{company_id}/workforce/bootstrap")
def bootstrap_workforce_endpoint(company_id: str, request: WorkforceAction) -> dict[str, Any]:
    try:
        return bootstrap_workforce(
            company_id=company_id,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/companies/{company_id}/goals/{goal_id}/plan")
async def plan_company_goal_endpoint(
    company_id: str, goal_id: str, request: WorkforceAction
) -> dict[str, Any]:
    try:
        return await plan_goal(
            company_id=company_id,
            tenant_id=request.tenant_id,
            goal_id=goal_id,
            actor_id=request.actor_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/companies/{company_id}/goals/{goal_id}/execute")
async def execute_company_goal_endpoint(
    company_id: str, goal_id: str, request: WorkforceAction
) -> dict[str, Any]:
    try:
        return await execute_goal(
            company_id=company_id,
            tenant_id=request.tenant_id,
            goal_id=goal_id,
            actor_id=request.actor_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/companies/{company_id}/work/{work_id}/execute")
async def execute_company_work_endpoint(
    company_id: str, work_id: str, request: WorkExecutionRequest
) -> dict[str, Any]:
    try:
        return await execute_task(
            company_id=company_id,
            tenant_id=request.tenant_id,
            work_id=work_id,
            actor_id=request.actor_id,
            retry=request.retry,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/companies/{company_id}/meetings/{meeting_id}/convene")
async def convene_company_meeting_endpoint(
    company_id: str, meeting_id: str, request: WorkforceAction
) -> dict[str, Any]:
    try:
        return await convene_meeting(
            company_id=company_id,
            tenant_id=request.tenant_id,
            meeting_id=meeting_id,
            actor_id=request.actor_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/companies/{company_id}/kpis/{kpi_id}/measure")
def record_company_kpi_endpoint(
    company_id: str, kpi_id: str, request: KpiMeasurementRequest
) -> dict[str, Any]:
    try:
        return record_kpi_measurement(
            company_id=company_id,
            tenant_id=request.tenant_id,
            kpi_id=kpi_id,
            actor_id=request.actor_id,
            actual_value=request.actual_value,
            source=request.source,
            evidence=request.evidence,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc



@router.post("/companies/{company_id}/goals/{goal_id}/jobs", status_code=202)
def enqueue_goal_job_endpoint(
    company_id: str, goal_id: str, request: GoalJobRequest
) -> dict[str, Any]:
    try:
        return enqueue_job(
            company_id=company_id,
            tenant_id=request.tenant_id,
            kind=request.kind,
            target_id=goal_id,
            actor_id=request.actor_id,
            idempotency_key=request.idempotency_key,
            payload={"source": "company_api"},
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/companies/{company_id}/work/{work_id}/jobs", status_code=202)
def enqueue_work_job_endpoint(
    company_id: str, work_id: str, request: TargetJobRequest
) -> dict[str, Any]:
    try:
        return enqueue_job(
            company_id=company_id,
            tenant_id=request.tenant_id,
            kind="work_execution",
            target_id=work_id,
            actor_id=request.actor_id,
            idempotency_key=request.idempotency_key,
            payload={"source": "company_api"},
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/companies/{company_id}/meetings/{meeting_id}/jobs", status_code=202)
def enqueue_meeting_job_endpoint(
    company_id: str, meeting_id: str, request: TargetJobRequest
) -> dict[str, Any]:
    try:
        return enqueue_job(
            company_id=company_id,
            tenant_id=request.tenant_id,
            kind="meeting",
            target_id=meeting_id,
            actor_id=request.actor_id,
            idempotency_key=request.idempotency_key,
            payload={"source": "company_api"},
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/companies/{company_id}/jobs")
def list_company_jobs_endpoint(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
    limit: int = Query(default=100, ge=1, le=250),
) -> dict[str, Any]:
    if get_company_graph(company_id=company_id, tenant_id=tenant_id) is None:
        raise HTTPException(404, "Company not found")
    jobs = list_jobs(company_id=company_id, tenant_id=tenant_id, limit=limit)
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/companies/{company_id}/jobs/{job_id}")
def get_company_job_endpoint(
    company_id: str,
    job_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    job = get_job(job_id=job_id, company_id=company_id, tenant_id=tenant_id)
    if job is None:
        raise HTTPException(404, "Workforce job not found")
    return job


@router.post("/companies/{company_id}/jobs/{job_id}/cancel")
def cancel_company_job_endpoint(
    company_id: str,
    job_id: str,
    request: WorkforceAction,
) -> dict[str, Any]:
    job = cancel_job(job_id=job_id, company_id=company_id, tenant_id=request.tenant_id)
    if job is None:
        raise HTTPException(404, "Workforce job not found")
    return job


@router.get("/companies/{company_id}/coordination")
def get_company_coordination_endpoint(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    if get_company_graph(company_id=company_id, tenant_id=tenant_id) is None:
        raise HTTPException(404, "Company not found")
    return {"coordination": get_coordination(company_id=company_id, tenant_id=tenant_id)}


@router.put("/companies/{company_id}/coordination")
def configure_company_coordination_endpoint(
    company_id: str, request: CoordinationRequest
) -> dict[str, Any]:
    try:
        policy = configure_coordination(
            company_id=company_id,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            enabled=request.enabled,
            mode=request.mode,
            interval_seconds=request.interval_seconds,
        )
        return {"coordination": policy}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
