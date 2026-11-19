import asyncio

from app import workforce


def _agent(agent_id, name, role, skills=None, authority="SPECIALIST"):
    return {
        "id": agent_id,
        "type": "agent",
        "name": name,
        "status": "ACTIVE",
        "data": {
            "role": role,
            "title": role.title(),
            "skills": skills or [],
            "responsibilities": skills or [],
            "authority": authority,
        },
    }


def test_explicit_agent_mention_is_detected():
    maya = _agent("maya", "Maya Chen", "Marketing Lead")
    assert workforce._chat_agent_matches(maya, "Please @Maya Chen, review the launch plan.")
    assert workforce._chat_agent_matches(maya, "Marketing Lead, can you join?")
    assert not workforce._chat_agent_matches(maya, "Can someone review the launch plan?")


def test_relevance_scores_match_configured_skills():
    marketing = _agent("marketing", "Maya", "Marketing", ["campaign", "social media", "launch"])
    finance = _agent("finance", "Amir", "Finance", ["budget", "forecast", "cash flow"])
    assert workforce._chat_relevance_score(marketing, "Prepare a social media launch campaign") > 0
    assert workforce._chat_relevance_score(marketing, "Prepare a social media launch campaign") > workforce._chat_relevance_score(finance, "Prepare a social media launch campaign")


def test_explicitly_called_agents_all_get_a_turn(monkeypatch):
    agents = [
        _agent("maya", "Maya Chen", "Marketing Lead", ["campaign"]),
        _agent("amir", "Amir", "Finance Lead", ["budget"]),
        _agent("lee", "Lee", "Engineer", ["software"]),
    ]
    called = []
    observed_histories = []

    async def fake_chat_with_agent(**kwargs):
        called.append(kwargs["agent"]["id"])
        observed_histories.append(list(kwargs["history"]))
        return f"Reply from {kwargs['agent']['name']}"

    monkeypatch.setattr(workforce, "chat_with_agent", fake_chat_with_agent)
    result = asyncio.run(workforce.chat_with_workforce(
        agents=agents,
        company={"name": "Test Co", "data": {}},
        message="@Maya Chen and @Amir, please review the launch budget.",
        history=[],
        company_id="company-1",
        tenant_id="tenant-1",
    ))
    assert called == ["maya", "amir"]
    assert [item["agent_id"] for item in result] == called
    assert len(result) == 2
    assert observed_histories[1][-1]["content"] == "Maya Chen (Marketing Lead): Reply from Maya Chen"
