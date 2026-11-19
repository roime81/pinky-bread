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


def test_company_chat_uses_selected_company_agent_and_history(monkeypatch):
    init_db()
    settings = get_settings()
    monkeypatch.setattr(settings, "mock_inference", False)
    captured = {}

    async def fake_chat_with_agent(**kwargs):
        captured.update(kwargs)
        return "Here is the product strategy."

    monkeypatch.setattr("app.company_api.chat_with_agent", fake_chat_with_agent)
    with TestClient(app) as client:
        tenant = "company-chat-live-test"
        company = _company(client, tenant)
        agent = _agent(client, company["id"], tenant)
        response = client.post(f"/v2/companies/{company['id']}/chat", json={
            "tenant_id": tenant,
            "actor_id": "founder",
            "agent_id": agent["id"],
            "message": "Help me prioritise our first release.",
            "history": [{"role": "user", "content": "We are a small startup."}],
        })
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["reply"] == "Here is the product strategy."
        assert payload["mode"] == "LIVE_MODEL"
        assert payload["agent"]["name"] == "Mira"
        assert captured["agent"]["id"] == agent["id"]
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
