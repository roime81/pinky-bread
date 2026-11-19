from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app
from app.settings import get_settings


def _company(client: TestClient, tenant: str) -> dict:
    response = client.post("/v2/companies", json={
        "tenant_id": tenant,
        "owner_id": "founder",
        "name": "AI Chat Test Company",
        "vision": "Build useful products",
        "mission": "Serve customers",
        "values": [],
    })
    assert response.status_code == 201, response.text
    return response.json()


def _agent(client: TestClient, company_id: str, tenant: str) -> dict:
    response = client.post(f"/v2/companies/{company_id}/agents", json={
        "tenant_id": tenant,
        "actor_id": "founder",
        "name": "Mira",
        "role": "Product strategy",
        "title": "Head of Product",
        "description": "Owns product strategy",
        "skills": ["research", "strategy"],
        "responsibilities": ["Research customers"],
        "system_prompt": "You are Mira, a product strategist.",
        "authority": "COORDINATOR",
        "seniority_level": 8,
        "model_configuration": {
            "provider": "ollama",
            "model_name": "qwen2.5:7b",
            "endpoint": "http://ollama:11434/v1",
        },
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_company_chat_routes_to_workforce_and_shares_history(monkeypatch):
    init_db()
    settings = get_settings()
    monkeypatch.setattr(settings, "mock_inference", False)
    captured = {}

    async def fake_chat_with_workforce(**kwargs):
        captured.update(kwargs)
        return [{
            "agent_id": kwargs["agents"][0]["id"],
            "name": "Mira",
            "role": "Product strategy",
            "reply": "Here is the product strategy.",
        }]

    monkeypatch.setattr("app.company_api.chat_with_workforce", fake_chat_with_workforce)
    with TestClient(app) as client:
        tenant = "company-chat-live-test"
        company = _company(client, tenant)
        agent = _agent(client, company["id"], tenant)
        response = client.post(f"/v2/companies/{company['id']}/chat", json={
            "tenant_id": tenant,
            "actor_id": "founder",
            "message": "Help me prioritise our first release.",
            "history": [{"role": "user", "content": "We are a small startup."}],
        })
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["responses"][0]["reply"] == "Here is the product strategy."
        assert "Mira" in payload["reply"]
        assert payload["mode"] == "LIVE_MODEL"
        assert payload["agent"]["name"] == "Mira"
        assert captured["agents"][0]["id"] == agent["id"]
        assert captured["history"][0]["content"] == "We are a small startup."


def test_company_chat_reports_mock_mode_instead_of_faking_an_ai_reply(monkeypatch):
    init_db()
    settings = get_settings()
    monkeypatch.setattr(settings, "mock_inference", True)
    with TestClient(app) as client:
        tenant = "company-chat-mock-test"
        company = _company(client, tenant)
        agent = _agent(client, company["id"], tenant)
        response = client.post(f"/v2/companies/{company['id']}/chat", json={
            "tenant_id": tenant,
            "agent_id": agent["id"],
            "message": "What should we do next?",
        })
        assert response.status_code == 503
        assert "MOCK_INFERENCE=true" in response.json()["detail"]


def test_founder_chat_uses_agent_specific_model_endpoint(monkeypatch):
    import asyncio

    from app.workforce import chat_with_agent

    settings = get_settings()
    monkeypatch.setattr(settings, "mock_inference", False)
    captured = {}

    async def fake_completion(**kwargs):
        captured.update(kwargs)
        return "Model-specific answer"

    monkeypatch.setattr("app.workforce._chat_completion", fake_completion)
    agent = {
        "id": "agent-1",
        "name": "Mira",
        "description": "Product strategy",
        "data": {
            "role": "Product strategist",
            "model_configuration": {
                "provider": "ollama",
                "model_name": "qwen2.5:7b",
                "endpoint": "http://ollama:11434/v1",
            },
        },
    }
    company = {"name": "Test Co", "data": {"vision": "Build", "mission": "Serve"}}
    result = asyncio.run(chat_with_agent(
        agent=agent,
        company=company,
        agents=[agent],
        message="What is our next move?",
        history=[],
        company_id="company-1",
        tenant_id="tenant-1",
    ))
    assert result == "Model-specific answer"
    assert captured["model_name"] == "qwen2.5:7b"
    assert captured["api_url"] == "http://ollama:11434/v1"


def test_mcp_client_exposes_safe_read_only_tools_to_specialists():
    from app.mcp_client import ROLE_TOOL_ALLOWLIST

    assert ROLE_TOOL_ALLOWLIST["specialist"] == {
        "company_graph_snapshot",
        "list_company_goals",
        "list_goal_work",
    }


def test_coordinator_chat_uses_mcp_and_its_employee_model(monkeypatch):
    import asyncio

    from app.workforce import chat_with_agent

    settings = get_settings()
    monkeypatch.setattr(settings, "mock_inference", False)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    captured = {}

    async def fake_complete_with_mcp(**kwargs):
        captured.update(kwargs)
        return "I reviewed the company context and prepared the next steps."

    monkeypatch.setattr("app.mcp_client.complete_with_mcp", fake_complete_with_mcp)
    agent = {
        "id": "coordinator-1",
        "name": "Nora",
        "description": "Company coordination",
        "data": {
            "role": "Company coordination",
            "authority": "COORDINATOR",
            "model_configuration": {
                "provider": "ollama",
                "model_name": "qwen2.5:3b",
                "endpoint": "http://ollama:11434/v1",
            },
        },
    }
    company = {"name": "Test Co", "data": {"vision": "Build", "mission": "Serve"}}
    answer = asyncio.run(chat_with_agent(
        agent=agent,
        company=company,
        agents=[agent],
        message="Review progress and suggest next actions.",
        history=[{"role": "user", "content": "We have two goals."}],
        company_id="company-2",
        tenant_id="tenant-2",
    ))
    assert answer.startswith("I reviewed")
    assert captured["role"] == "head_of_agents"
    assert captured["agent_id"] == "coordinator-1"
    assert captured["model_name"] == "qwen2.5:3b"
    assert captured["api_url"] == "http://ollama:11434/v1"
    assert "We have two goals." in captured["user_prompt"]


def test_runtime_status_explains_mock_mode(monkeypatch):
    init_db()
    settings = get_settings()
    monkeypatch.setattr(settings, "mock_inference", True)
    with TestClient(app) as client:
        response = client.get("/v2/runtime")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mock_inference"] is True
        assert payload["model_reachable"] is False
        assert "MOCK_INFERENCE=true" in payload["model_error"]
