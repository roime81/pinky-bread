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
        "auth-gate",
        "auth-logout",
        "company-command-form",
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
