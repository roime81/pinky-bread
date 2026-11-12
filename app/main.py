from __future__ import annotations
import base64
import json
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from .database import init_db
from .engine import WorkflowEngine, WorkflowNotFound, WorkflowConflict
from .registry import AgentRegistry
from .schemas import WorkflowInvokeRequest, ApprovalRequest, ArtifactInput
from .settings import get_settings

settings = get_settings()
registry = AgentRegistry(settings.agent_config_dir)
engine = WorkflowEngine(registry)
@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", description="Air-gapped multimodal multi-agent platform MVP", lifespan=lifespan)


web_dir = Path(__file__).resolve().parent.parent / "web"
app.mount("/static", StaticFiles(directory=web_dir), name="static")


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return (web_dir / "index.html").read_text(encoding="utf-8")


@app.get("/api/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok", "app": settings.app_name, "environment": settings.app_env, "mock_inference": settings.mock_inference, "airgap_mode": "network-restricted-by-deployment"}


@app.get("/v1/agents")
def list_agents() -> dict[str, Any]:
    return {"agents": [agent.model_dump() for agent in registry.all()]}


@app.post("/v1/agents/reload")
def reload_agents() -> dict[str, Any]:
    return registry.reload()


@app.post("/v1/artifacts")
async def upload_artifact(file: UploadFile = File(...)) -> dict[str, Any]:
    allowed = {"image/png", "image/jpeg", "application/pdf"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Only PNG, JPEG and PDF artifacts are supported")
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"Maximum artifact size is {settings.max_upload_mb} MB")
    return {"filename": Path(file.filename or "upload").name, "mime_type": file.content_type, "base64_data": base64.b64encode(data).decode("ascii"), "size_bytes": len(data)}


@app.post("/v1/workflows/invoke")
async def invoke_workflow(request: WorkflowInvokeRequest) -> dict[str, Any]:
    try:
        return await engine.invoke(request)
    except WorkflowConflict as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Workflow failed: {exc}")


@app.post("/v1/workflows/stream")
async def stream_workflow(request: WorkflowInvokeRequest):
    async def event_stream():
        try:
            result = await engine.invoke(request)
            for entry in result.get("audit_trail", []):
                yield f"event: {entry['action_type'].lower()}\ndata: {json.dumps(entry)}\n\n"
            yield f"event: complete\ndata: {json.dumps(result)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/v1/workflows/{thread_id}/approve")
def approve_workflow(thread_id: str, request: ApprovalRequest) -> dict[str, Any]:
    try:
        return engine.approve(thread_id, approver_id=request.approver_id, decision=request.decision, notes=request.notes)
    except WorkflowNotFound:
        raise HTTPException(404, "Workflow not found")
    except WorkflowConflict as exc:
        raise HTTPException(409, str(exc))


@app.get("/v1/workflows/{thread_id}")
def get_workflow(thread_id: str) -> dict[str, Any]:
    try:
        return engine.get_workflow(thread_id)
    except WorkflowNotFound:
        raise HTTPException(404, "Workflow not found")


@app.get("/v1/workflows")
def list_workflows() -> dict[str, Any]:
    return {"workflows": engine.list_workflows()}


@app.get("/v1/audit/{thread_id}")
def get_audit(thread_id: str) -> dict[str, Any]:
    try:
        return engine.audit(thread_id)
    except WorkflowNotFound:
        raise HTTPException(404, "Workflow not found")
