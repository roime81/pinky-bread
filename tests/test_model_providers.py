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
