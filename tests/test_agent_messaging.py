from fastapi.testclient import TestClient

from app import agent_messaging
from app.database import init_db
from app.main import app


def _company(client, tenant):
    response = client.post("/v2/companies", json={
        "tenant_id": tenant,
        "owner_id": "founder",
        "name": "A2A Test Company",
        "vision": "Build useful products",
        "mission": "Collaborate effectively",
        "values": ["clarity", "trust"],
    })
    assert response.status_code == 201, response.text
    return response.json()


def _agent(client, company_id, tenant, name, authority="SPECIALIST"):
    response = client.post(f"/v2/companies/{company_id}/agents", json={
        "tenant_id": tenant,
        "actor_id": "founder",
        "name": name,
        "role": "Business collaboration",
        "title": "Collaboration Specialist",
        "description": f"{name} supports company collaboration",
        "skills": ["planning", "communication"],
        "responsibilities": ["Discuss plans and recommend next steps"],
        "system_prompt": f"You are {name}. Speak from your own perspective.",
        "authority": authority,
        "seniority_level": 4,
        "model_configuration": {"provider": "ollama", "model_name": "qwen2.5:3b"},
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_resolve_agent_discussion_with_two_named_agents():
    agents = [
        {"id": "mira-id", "type": "agent", "name": "Mira", "status": "ACTIVE", "data": {"role": "Coordinator", "authority": "COORDINATOR"}},
        {"id": "jamal-id", "type": "agent", "name": "Jamal", "status": "ACTIVE", "data": {"role": "Marketing"}},
    ]
    result = agent_messaging.resolve_agent_discussion(
        agents, "Mira, please discuss the launch plan with Jamal."
    )
    assert result is not None
    assert result["initiator"]["id"] == "mira-id"
    assert [agent["id"] for agent in result["recipients"]] == ["jamal-id"]
    assert result["max_turns"] == 6


def test_resolve_single_named_colleague_uses_coordinator():
    agents = [
        {"id": "mira-id", "type": "agent", "name": "Mira", "status": "ACTIVE", "data": {"authority": "COORDINATOR"}},
        {"id": "jamal-id", "type": "agent", "name": "Jamal", "status": "ACTIVE", "data": {"role": "Marketing"}},
    ]
    result = agent_messaging.resolve_agent_discussion(agents, "Please discuss our campaign with Jamal.")
    assert result is not None
    assert result["initiator"]["id"] == "mira-id"
    assert result["recipients"][0]["id"] == "jamal-id"


def test_greeting_is_bounded_to_one_peer_reply():
    agents = [
        {"id": "mira-id", "type": "agent", "name": "Mira", "status": "ACTIVE", "data": {}},
        {"id": "jamal-id", "type": "agent", "name": "Jamal", "status": "ACTIVE", "data": {}},
    ]
    result = agent_messaging.resolve_agent_discussion(agents, "Mira, say hello to Jamal.")
    assert result is not None
    assert result["max_turns"] == 2


def test_agent_to_agent_conversation_is_streamed_and_persisted(monkeypatch):
    init_db()
    tenant = "a2a-integration-tenant"

    async def fake_chat_with_agent(**kwargs):
        agent_name = kwargs["agent"]["name"]
        prompt = kwargs["message"]
        if agent_name == "Mira" and "Start the discussion" in prompt:
            return "Hi Jamal, can we discuss the launch audience and positioning?"
        if agent_name == "Jamal" and "Your colleague Mira" in prompt:
            return "Hello Mira. I recommend starting with existing customers and testing two segments. <PB_DISCUSSION_COMPLETE>"
        if agent_name == "Mira" and "report the outcome" in prompt:
            return "Jamal and I agreed to validate the launch audience with existing customers first."
        raise AssertionError(f"Unexpected invocation for {agent_name}: {prompt}")

    monkeypatch.setattr(agent_messaging, "chat_with_agent", fake_chat_with_agent)

    with TestClient(app) as client:
        company = _company(client, tenant)
        mira = _agent(client, company["id"], tenant, "Mira", "COORDINATOR")
        jamal = _agent(client, company["id"], tenant, "Jamal", "SPECIALIST")

        response = client.post(
            f"/v2/companies/{company['id']}/conversations/stream",
            json={
                "tenant_id": tenant,
                "actor_id": "founder",
                "message": "Mira, please discuss the launch plan with Jamal.",
                "max_turns": 6,
            },
        )
        assert response.status_code == 200, response.text
        frames = [
            line[5:].strip()
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
        events = [__import__("json").loads(frame) for frame in frames]
        assert any(event["type"] == "conversation_started" for event in events)
        assert any(event["type"] == "complete" for event in events)
        messages = [event["message"] for event in events if event["type"] == "message"]
        assert any(item["message_kind"] == "ACKNOWLEDGEMENT" for item in messages)
        assert any(item["sender_agent_id"] == mira["id"] and item["recipient_agent_id"] == jamal["id"] for item in messages)
        assert any(item["sender_agent_id"] == jamal["id"] and item["recipient_agent_id"] == mira["id"] for item in messages)
        assert messages[-1]["message_kind"] == "FOUNDER_SUMMARY"

        conversation_id = next(
            event["conversation_id"] for event in events if event["type"] == "conversation_started"
        )
        saved = client.get(
            f"/v2/companies/{company['id']}/conversations/{conversation_id}?tenant_id={tenant}"
        )
        assert saved.status_code == 200, saved.text
        thread = saved.json()
        assert thread["status"] == "COMPLETED"
        assert len(thread["messages"]) == 5
        assert thread["messages"][0]["sender_type"] == "FOUNDER"
        assert "agreed to validate" in thread["summary"]
        listing = client.get(f"/v2/companies/{company['id']}/conversations?tenant_id={tenant}")
        assert listing.status_code == 200
        assert listing.json()["count"] == 1

