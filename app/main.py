from __future__ import annotations
import base64
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from .database import check_db_connection, init_db
from .engine import WorkflowEngine, WorkflowNotFound, WorkflowConflict
from .registry import AgentRegistry
from .schemas import WorkflowInvokeRequest, ApprovalRequest, ArtifactInput
from .settings import get_settings
from .company_api import router as company_graph_router
from .auth import router as auth_router, AuthMiddleware, session_user

settings = get_settings()
registry = AgentRegistry(settings.agent_config_dir)
engine = WorkflowEngine(registry)
@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_schema:
        # Convenient for local SQLite development. Compose uses a one-shot
        # migration service and disables schema creation in app containers.
        init_db()
    else:
        check_db_connection()
    yield


app = FastAPI(title=settings.app_name, version="2.0.0-alpha.4", description="Local-first AI company and multi-agent operating system", lifespan=lifespan)


web_dir = Path(__file__).resolve().parent.parent / "web"
app.mount("/static", StaticFiles(directory=web_dir), name="static")
app.include_router(company_graph_router)
app.include_router(auth_router)
app.add_middleware(AuthMiddleware)


def _workspace_response() -> HTMLResponse:
    return HTMLResponse(
        (web_dir / "index.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    current_settings = get_settings()
    if current_settings.auth_enabled and not session_user(request):
        return RedirectResponse(url="/login", status_code=303)
    return _workspace_response()


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    current_settings = get_settings()
    if not current_settings.auth_enabled or session_user(request):
        return RedirectResponse(url="/", status_code=303)
    return HTMLResponse((web_dir / "login.html").read_text(encoding="utf-8"))


@app.get("/dashboard", include_in_schema=False)
@app.get("/workspace", include_in_schema=False)
def canonical_dashboard_alias(request: Request):
    """Keep old dashboard bookmarks from landing on an unrecognised page."""
    current_settings = get_settings()
    if current_settings.auth_enabled and not session_user(request):
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/", status_code=303)


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

@app.get("/{path:path}", response_class=HTMLResponse)
def frontend_route_fallback(path: str, request: Request):
    """Serve the React workspace on browser deep links without swallowing API 404s."""
    first_segment = path.split("/", 1)[0].lower()
    reserved_prefixes = {"static", "auth", "api", "v1", "v2", "docs", "redoc", "openapi.json"}
    if first_segment in reserved_prefixes:
        raise HTTPException(status_code=404, detail="Not found")

    requested_path = "/" + path
    if request.url.query:
        requested_path += "?" + request.url.query

    current_settings = get_settings()
    if current_settings.auth_enabled and not session_user(request):
        return RedirectResponse(
            url="/login?" + urlencode({"next": requested_path}),
            status_code=303,
        )
    return _workspace_response()

