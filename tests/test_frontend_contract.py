from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_company_workspace_defines_every_runtime_helper_it_calls():
    source = (ROOT / "web" / "company-graph.js").read_text(encoding="utf-8")
    required = [
        "activeAgents",
        "_isCoordinatorForUi",
        "renderAgentDirectory",
        "openAgentEditor",
        "saveAgent",
        "sendAiMessage",
    ]
    for name in required:
        assert re.search(rf"function\s+{re.escape(name)}\s*\(", source), name
    assert len(re.findall(r"function\s+addAgent\s*\(", source)) == 1


def test_company_graph_nodes_remain_pointer_hit_testable():
    source = (ROOT / "web" / "company-graph.css").read_text(encoding="utf-8")
    assert ".graph-node{cursor:pointer" in source
    assert ".graph-node .node-core,.graph-node .node-halo{pointer-events:visiblePainted}" in source
    assert ".graph-node *{pointer-events:none}" not in source


def test_founder_workspace_contains_all_agent_editor_and_chat_controls():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for element_id in [
        "graph-add-agent",
        "graph-add-agent-directory",
        "agent-editor-form",
        "agent-editor-provider",
        "agent-editor-model",
        "agent-editor-endpoint",
        "agent-editor-manager",
        "auth-logout",
        "company-composer-root",
        "ai-runtime-status",
    ]:
        assert f'id="{element_id}"' in html, element_id


def test_hidden_sections_cannot_override_the_hidden_attribute():
    source = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    assert "[hidden]{display:none!important}" in source
    assert re.search(r"\.view\.active\s*\{\s*display:\s*block\s*!important", source)


def test_saved_company_initialization_reveals_the_dashboard():
    source = (ROOT / "web" / "company-graph.js").read_text(encoding="utf-8")
    init_start = source.index("async function initialise()")
    init_end = source.index("function renderCompanyPicker()", init_start)
    initialise = source[init_start:init_end]
    assert "state.company = state.companies[0]" in initialise
    assert "setWorkspaceVisible(true)" in initialise
    assert initialise.index("setWorkspaceVisible(true)") < initialise.index("await loadGraph(true)")


def test_founder_chat_does_not_require_manual_agent_selection():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "web" / "company-graph.js").read_text(encoding="utf-8")
    assert 'id="company-chat-agent"' not in html
    assert "renderChatAgentPicker" not in source
    assert "Relevant agents may join" in html


def test_company_graph_toolbar_and_durable_workforce_panel_are_removed():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'class="company-toolbar"' not in html
    assert 'class="graph-tools"' not in html
    assert 'id="workforce-runtime-panel"' not in html
    assert 'id="graph-company-picker"' in html
    assert 'id="graph-add-agent"' in html
    assert 'graph-heading-actions' in html


def test_company_agent_directory_is_rendered_inside_the_left_sidebar():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    sidebar_start = html.index('<aside class="sidebar"')
    main_start = html.index('<main class="main-area">')
    directory_start = html.index('id="agent-management-panel"')
    directory_end = html.index('</section>', directory_start)
    assert sidebar_start < directory_start < directory_end < main_start
    assert 'id="company-agent-list"' in html
    assert 'id="graph-add-agent-directory"' in html



def test_company_event_log_and_founder_view_are_dedicated_pages():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'data-view="company-events"' in html
    assert 'data-view="founder-view"' in html
    assert 'id="view-company-events"' in html
    assert 'id="view-founder-view"' in html
    assert html.count('id="graph-activity-panel"') == 1
    assert html.count('id="graph-brief-panel"') == 1
    assert 'class="company-bottom-grid"' not in html


def test_left_and_right_workspace_panels_are_independently_collapsible():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "company-graph.css").read_text(encoding="utf-8")
    assert 'id="sidebar-toggle"' in html
    assert 'id="sidebar-panel-close"' in html
    assert 'id="chat-panel-toggle"' in html
    assert 'id="chat-panel-close"' in html
    assert "pinky-sidebar-hidden" in app
    assert "pinky-chat-panel-hidden" in app
    assert ".app-shell.sidebar-hidden" in styles
    assert ".app-shell.chat-hidden" in styles


def test_agent_graph_dots_can_be_dragged_and_remembered_per_company():
    source = (ROOT / "web" / "company-graph.js").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "company-graph.css").read_text(encoding="utf-8")
    assert "bindAgentNodeDragging" in source
    assert 'closest(".graph-node.agent")' in source
    assert 'addEventListener("pointerdown"' in source
    assert 'addEventListener("pointermove"' in source
    assert 'addEventListener("pointerup"' in source
    assert "pinky-graph-layout:" in source
    assert "state.nodePositions" in source
    assert ".graph-node.agent" in styles
    assert "cursor: grab" in styles


def test_dedicated_login_page_is_the_unauthenticated_entry_point():
    login = (ROOT / "web" / "login.html").read_text(encoding="utf-8")
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    script = (ROOT / "web" / "login.js").read_text(encoding="utf-8")
    assert 'id="login-form"' in login
    assert 'id="login-google"' in login
    assert 'id="login-password"' in login
    assert 'id="app-shell"' not in login
    assert "/static/login.js" in login
    assert 'RedirectResponse(url="/login", status_code=303)' in main
    assert 'RedirectResponse(url="/", status_code=303)' in main
    assert 'window.location.replace("/")' in script


def test_commercial_model_providers_are_available_in_the_agent_editor():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    company_graph = (ROOT / "web" / "company-graph.js").read_text(encoding="utf-8")
    assert '<option value="openai">OpenAI API</option>' in html
    assert '<option value="gemini">Google Gemini API</option>' in html
    assert 'id="view-model-providers"' in html
    assert "OPENAI_API_KEY" in html
    assert "GEMINI_API_KEY" in html
    assert "'model-providers':loadModelProviders" in app
    assert 'provider: "openai"' in company_graph or 'openai: { model:' in company_graph
    assert 'gemini: { model:' in company_graph

def test_react_founder_composer_supports_document_uploads_and_cloud_share_links():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    composer = (ROOT / "frontend" / "src" / "FounderComposer.tsx").read_text(encoding="utf-8")
    company_graph = (ROOT / "web" / "company-graph.js").read_text(encoding="utf-8")
    assert 'id="company-composer-root"' in html
    assert 'id="company-command-form"' not in html
    assert "FounderComposer" in main
    assert "onDrop={handleDrop}" in composer
    assert "document-links" in composer
    assert "artifact_ids: artifactIds" in company_graph
    assert "pinky:founder-message-complete" in company_graph
