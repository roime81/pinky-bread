from __future__ import annotations

from typing import Any, Literal
import asyncio
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from redis.asyncio import Redis
from pydantic import BaseModel, Field

from .settings import get_settings
from .object_store import ObjectStore
from .durable_runtime import (
    enqueue_job,
    get_job,
    list_jobs,
    cancel_job,
    configure_coordination,
    get_coordination,
)

from .workforce import (
    bootstrap_workforce,
    plan_goal,
    execute_goal,
    execute_task,
    convene_meeting,
    record_kpi_measurement,
)

from .company_graph import (
    NODE_TYPES,
    RELATIONSHIPS,
    create_company,
    create_edge,
    create_node,
    get_company_graph,
    list_companies,
    list_company_events,
    verify_event_chain,
)

router = APIRouter(prefix="/v2", tags=["company graph"])


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
        "version": "2.0.0-alpha.2",
        "node_types": sorted(NODE_TYPES | {"company"}),
        "relationships": sorted(RELATIONSHIPS),
        "persistence": "PostgreSQL/SQLAlchemy graph records and event history",
        "live_notifications": "Valkey Pub/Sub; PostgreSQL remains authoritative",
        "object_storage": "Local filesystem or S3-compatible SeaweedFS with PostgreSQL metadata",
        "workforce": ["idempotent team bootstrap", "goal decomposition", "assigned work execution", "meeting facilitation", "KPI measurement history"],
        "inference": "Local OpenAI-compatible model endpoint or explicitly labelled mock mode",
        "source_of_truth": "database",
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
