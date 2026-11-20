from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_product_workspace_is_mounted_from_one_react_root():
    html = source("web/index.html")
    entry = source("frontend/src/main.tsx")
    assert 'id="root"' in html
    assert "/static/app/workspace.js" in html
    assert "/static/app/workspace.css" in html
    assert "createRoot(container).render" in entry
    assert "WorkspaceApp" in entry
    assert entry.count("createRoot(") == 1
    assert "/static/app.js" not in html
    assert "/static/company-graph.js" not in html
    assert "/static/a2a/agent-workspace.js" not in html


def test_vite_and_docker_build_publish_the_same_react_bundle_path():
    vite = source("frontend/vite.config.ts")
    docker = source("Dockerfile")
    assert 'base: "/static/app/"' in vite
    assert '"workspace.js"' in vite
    assert 'resolve(process.cwd(), "../web/app")' in vite
    assert "web/app ./web/app" in docker
    assert "web/a2a" not in docker


def test_react_workspace_owns_navigation_company_graph_and_company_creation():
    app = source("frontend/src/WorkspaceApp.tsx")
    for view in [
        "company-graph", "company-events", "founder-view", "company-agents",
        "agent-messaging", "durable-workforce", "model-providers", "overview", "workflows", "agents", "audit",
    ]:
        assert f'"{view}"' in app
    assert "/v2/companies?tenant_id=" in app
    assert '"/v2/companies"' in app
    assert "/graph?tenant_id=" in app
    assert "setActiveView" in app
    assert "graph-company-picker" in app


def test_react_company_graph_supports_relationship_inspection_and_node_creation():
    app = source("frontend/src/WorkspaceApp.tsx")
    assert "graph.edges.map" in app
    assert "pb-graph-node" in app
    assert "setSelectedNodeId" in app
    assert '"/nodes"' in app
    assert "addGraphNode" in app
    assert "connectGraphNodes" in app
    assert "recordKpiMeasurement" in app
    assert "/edges" in app


def test_react_workforce_supports_agent_crud_model_governance_and_reporting_lines():
    app = source("frontend/src/WorkspaceApp.tsx")
    assert '"/agents"' in app
    assert 'method: agent ? "PATCH" : "POST"' in app
    for key in [
        "system_prompt", "seniority_level", "authority", "manager_id",
        "model_configuration", "provider", "model_name", "endpoint",
    ]:
        assert key in app
    assert '<option value="openai">OpenAI API</option>' in app


def test_company_event_log_uses_durable_event_records_and_hash_verification():
    app = source("frontend/src/WorkspaceApp.tsx")
    assert "/events?tenant_id=" in app
    assert "/events/verify?tenant_id=" in app
    assert "eventVerification.valid" in app
    assert "entry_hash" in app
    assert "Company Event Log" in app


def test_founder_composer_is_react_controlled_and_keeps_document_ingestion():
    composer = source("frontend/src/FounderComposer.tsx")
    app = source("frontend/src/WorkspaceApp.tsx")
    assert "companyId: string" in composer
    assert "onSend: (message: string, artifactIds: string[]) => Promise<void>" in composer
    assert "await onSend(message, uploaded.map((item) => item.object_id))" in composer
    assert "/document-links" in composer
    assert "/artifacts" in composer
    assert "artifactIds" in app
    assert "/chat" in app
    assert "FounderComposer" in app
    assert "company-composer-root" not in source("web/index.html")


def test_agent_conversations_are_part_of_the_same_react_application():
    app = source("frontend/src/WorkspaceApp.tsx")
    entry = source("frontend/src/main.tsx")
    assert 'import AgentConversations from "./App"' in app
    assert "<AgentConversations />" in app
    assert "pinky:workspace" in app
    assert entry.count("createRoot(") == 1


def test_left_and_right_panels_are_independently_collapsible_and_persistent():
    app = source("frontend/src/WorkspaceApp.tsx")
    styles = source("frontend/src/workspace.css")
    assert "pinky-sidebar-hidden" in app
    assert "pinky-chat-panel-hidden" in app
    assert "is-left-collapsed" in styles
    assert "is-chat-collapsed" in styles
    assert "@media(max-width:680px)" in styles
    assert "pb-mobile-backdrop" in app
    assert "position:fixed" in styles


def test_model_provider_status_does_not_expose_provider_secrets():
    app = source("frontend/src/WorkspaceApp.tsx")
    assert "/v2/model-providers" in app
    assert "OPENAI_API_KEY" in app
    assert "GEMINI_API_KEY" in app
    assert "credentials stay on the server" in app.lower()
    assert "API keys are never stored in an agent profile" in app


def test_workflow_and_audit_views_retain_the_existing_backend_contracts():
    app = source("frontend/src/WorkspaceApp.tsx")
    for endpoint in [
        "/v1/workflows/invoke", "/v1/workflows", "/v1/agents",
        "/v1/agents/reload", "/v1/audit/",
    ]:
        assert endpoint in app
    assert "/approve" in app
    assert "workflowPrompt" in app
    assert "audit_trail" in app


def test_login_page_remains_the_unauthenticated_entry_point():
    login = source("web/login.html")
    main = source("app/main.py")
    script = source("web/login.js")
    assert 'id="login-form"' in login
    assert 'id="login-google"' in login
    assert 'id="login-password"' in login
    assert 'id="app-shell"' not in login
    assert "/static/login.js" in login
    assert 'RedirectResponse(url="/login", status_code=303)' in main
    assert 'RedirectResponse(url="/", status_code=303)' in main
    assert 'window.location.replace("/")' in script


def test_legacy_workspace_dom_scripts_are_not_loaded_by_the_application_shell():
    html = source("web/index.html")
    for path in [
        "/static/styles.css", "/static/company-graph.css",
        "/static/app.js", "/static/company-graph.js", "/static/auth.js",
    ]:
        assert path not in html
    assert re.search(r'<div id="root">', html)


def test_react_durable_workforce_queues_jobs_and_configures_recurring_coordination():
    app = source("frontend/src/WorkspaceApp.tsx")
    assert "/jobs?tenant_id=" in app
    assert "/coordination?tenant_id=" in app
    assert 'method: "PUT"' in app
    assert "saveCoordination" in app
    assert "cancelJob" in app
    assert "enqueueForNode" in app
    assert "PLAN_ONLY" in app
    assert "AUTO_EXECUTE" in app
