from types import SimpleNamespace

import pytest

from app.model_providers import (
    model_provider_status,
    normalize_chat_completions_base_url,
    resolve_agent_model_configuration,
)


def _settings(**overrides):
    values = {
        "model_provider": "ollama",
        "reasoning_model": "qwen2.5:3b",
        "reasoning_api_url": "http://ollama:11434/v1",
        "openai_api_key": "",
        "openai_api_url": "https://api.openai.com/v1",
        "gemini_api_key": "",
        "gemini_api_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "openai_compatible_api_key": "",
        "vllm_api_key": "local-dev-key",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_openai_agent_uses_openai_api_key_and_default_endpoint():
    resolved = resolve_agent_model_configuration(
        {"provider": "openai", "model_name": "gpt-4.1-mini"},
        settings=_settings(openai_api_key="sk-test-secret"),
    )
    assert resolved["provider"] == "openai"
    assert resolved["model_name"] == "gpt-4.1-mini"
    assert resolved["api_url"] == "https://api.openai.com/v1"
    assert resolved["api_key"] == "sk-test-secret"
    assert resolved["credential_env"] == "OPENAI_API_KEY"


def test_gemini_agent_uses_gemini_api_key_and_openai_compatibility_endpoint():
    resolved = resolve_agent_model_configuration(
        {"provider": "gemini", "model_name": "gemini-2.5-flash"},
        settings=_settings(gemini_api_key="gemini-test-secret"),
    )
    assert resolved["provider"] == "gemini"
    assert resolved["model_name"] == "gemini-2.5-flash"
    assert resolved["api_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert resolved["api_key"] == "gemini-test-secret"


def test_missing_commercial_credentials_fail_with_actionable_environment_setting():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        resolve_agent_model_configuration(
            {"provider": "openai", "model_name": "gpt-4.1-mini"},
            settings=_settings(),
        )
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        resolve_agent_model_configuration(
            {"provider": "gemini", "model_name": "gemini-2.5-flash"},
            settings=_settings(),
        )


def test_commercial_provider_requires_an_explicit_model_identifier():
    with pytest.raises(RuntimeError, match="Choose a model identifier"):
        resolve_agent_model_configuration(
            {"provider": "openai"},
            settings=_settings(openai_api_key="sk-test-secret"),
        )


def test_custom_openai_compatible_endpoint_can_use_its_own_server_side_key():
    resolved = resolve_agent_model_configuration(
        {
            "provider": "openai-compatible",
            "model_name": "my-deployment",
            "endpoint": "https://llm.example.test/v1",
        },
        settings=_settings(openai_compatible_api_key="gateway-test-secret"),
    )
    assert resolved["api_url"] == "https://llm.example.test/v1"
    assert resolved["api_key"] == "gateway-test-secret"


def test_gemini_base_url_is_not_rewritten_to_a_wrong_v1_path():
    assert normalize_chat_completions_base_url(
        "https://generativelanguage.googleapis.com/v1beta/openai"
    ) == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert normalize_chat_completions_base_url(
        "https://api.openai.com/v1/chat/completions"
    ) == "https://api.openai.com/v1"


def test_provider_status_never_returns_secret_values():
    status = model_provider_status(settings=_settings(
        openai_api_key="sk-do-not-return",
        gemini_api_key="gemini-do-not-return",
    ))
    assert status["openai"]["configured"] is True
    assert status["gemini"]["configured"] is True
    serialized = repr(status)
    assert "sk-do-not-return" not in serialized
    assert "gemini-do-not-return" not in serialized


def test_agent_chat_uses_its_openai_credentials_and_model(monkeypatch):
    import asyncio

    from app.settings import get_settings
    from app.workforce import chat_with_agent

    settings = get_settings()
    monkeypatch.setattr(settings, "mock_inference", False)
    monkeypatch.setattr(settings, "mcp_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", "sk-openai-agent-test")

    captured = {}

    async def fake_completion(**kwargs):
        captured.update(kwargs)
        return "OpenAI agent response"

    monkeypatch.setattr("app.workforce._chat_completion", fake_completion)
    agent = {
        "id": "openai-agent",
        "name": "Mira",
        "data": {
            "role": "Research analyst",
            "model_configuration": {"provider": "openai", "model_name": "gpt-4.1-mini"},
        },
    }
    result = asyncio.run(chat_with_agent(
        agent=agent,
        company={"name": "Test Co", "data": {}},
        agents=[agent],
        message="Summarise the market.",
        history=[],
        company_id="company-openai",
        tenant_id="tenant-openai",
    ))
    assert result == "OpenAI agent response"
    assert captured["model_name"] == "gpt-4.1-mini"
    assert captured["api_url"] == "https://api.openai.com/v1"
    assert captured["api_key"] == "sk-openai-agent-test"


def test_agent_chat_passes_gemini_credentials_through_mcp_tool_runtime(monkeypatch):
    import asyncio

    from app.settings import get_settings
    from app.workforce import chat_with_agent

    settings = get_settings()
    monkeypatch.setattr(settings, "mock_inference", False)
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "gemini_api_key", "gemini-agent-test")
    captured = {}

    async def fake_complete_with_mcp(**kwargs):
        captured.update(kwargs)
        return "Gemini agent response"

    monkeypatch.setattr("app.mcp_client.complete_with_mcp", fake_complete_with_mcp)
    agent = {
        "id": "gemini-agent",
        "name": "Nora",
        "data": {
            "role": "Company coordinator",
            "authority": "COORDINATOR",
            "model_configuration": {"provider": "gemini", "model_name": "gemini-4-hydrogen"},
        },
    }
    result = asyncio.run(chat_with_agent(
        agent=agent,
        company={"name": "Test Co", "data": {}},
        agents=[agent],
        message="Plan this week's priorities.",
        history=[],
        company_id="company-gemini",
        tenant_id="tenant-gemini",
    ))
    assert result == "Gemini agent response"
    assert captured["model_name"] == "gemini-4-hydrogen"
    assert captured["api_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert captured["api_key"] == "gemini-agent-test"


def test_provider_status_does_not_expose_api_keys(monkeypatch):
    from app import company_api
    from app.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-never-expose-this")
    monkeypatch.setattr(settings, "gemini_api_key", "AIza-never-expose-this")
    result = company_api.model_providers_endpoint()
    assert result["providers"]["openai"]["configured"] is True
    assert result["providers"]["gemini"]["configured"] is True
    assert "sk-never-expose-this" not in repr(result)
    assert "AIza-never-expose-this" not in repr(result)


def test_agent_model_configuration_rejects_api_keys_in_agent_payload():
    from fastapi import HTTPException
    from app.company_api import _validated_model_configuration

    with pytest.raises(HTTPException) as raised:
        _validated_model_configuration({
            "provider": "openai",
            "model_name": "gpt-4.1-mini",
            "api_key": "sk-this-should-not-be-stored",
        })
    assert raised.value.status_code == 422
    assert "server in .env" in raised.value.detail
