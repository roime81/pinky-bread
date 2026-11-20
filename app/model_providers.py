from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from .settings import Settings, get_settings


PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "ollama": {"label": "Ollama", "credential_env": "VLLM_API_KEY", "endpoint_setting": "reasoning_api_url"},
    "vllm": {"label": "vLLM", "credential_env": "VLLM_API_KEY", "endpoint_setting": "reasoning_api_url"},
    "openai-compatible": {"label": "OpenAI-compatible", "credential_env": "OPENAI_COMPATIBLE_API_KEY", "endpoint_setting": "reasoning_api_url"},
    "openai": {"label": "OpenAI", "credential_env": "OPENAI_API_KEY", "endpoint_setting": "openai_api_url"},
    "gemini": {"label": "Google Gemini", "credential_env": "GEMINI_API_KEY", "endpoint_setting": "gemini_api_url"},
}


def normalize_chat_completions_base_url(value: str) -> str:
    """Normalize a chat-completions URL without damaging Gemini's /v1beta/openai path."""
    endpoint = str(value or "").strip().rstrip("/")
    if endpoint.endswith("/chat/completions"):
        endpoint = endpoint[: -len("/chat/completions")]
    if not endpoint:
        raise ValueError("A model API endpoint is required.")
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("The selected model API endpoint must be an HTTP(S) URL.")
    path = parsed.path.rstrip("/")
    if path.endswith(("/v1", "/v1beta/openai")):
        return endpoint
    return f"{endpoint}/v1"


def resolve_agent_model_configuration(
    model_configuration: dict[str, Any] | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Resolve safe per-agent model settings against server-side provider credentials."""
    settings = settings or get_settings()
    config = model_configuration or {}
    provider = str(config.get("provider") or settings.model_provider or "ollama").strip().lower()
    if provider not in PROVIDER_DEFAULTS:
        raise ValueError(
            f"Unsupported model provider '{provider}'. Choose one of: {', '.join(PROVIDER_DEFAULTS)}."
        )

    definition = PROVIDER_DEFAULTS[provider]
    endpoint_setting = definition["endpoint_setting"]
    endpoint = str(config.get("endpoint") or getattr(settings, endpoint_setting)).strip()
    model_name = str(config.get("model_name") or "").strip()
    if not model_name:
        if provider in {"openai", "gemini"}:
            raise RuntimeError(f"Choose a model identifier for {definition['label']} in the agent settings.")
        model_name = settings.reasoning_model

    if provider == "openai":
        api_key = settings.openai_api_key.strip()
    elif provider == "gemini":
        api_key = settings.gemini_api_key.strip()
    elif provider == "openai-compatible":
        api_key = (settings.openai_compatible_api_key or settings.vllm_api_key).strip()
    else:
        api_key = settings.vllm_api_key.strip()

    if provider in {"openai", "gemini"} and not api_key:
        raise RuntimeError(
            f"{definition['credential_env']} is not configured. Add it to your .env file and restart "
            "the API and worker containers before assigning this provider to an agent."
        )

    normalize_chat_completions_base_url(endpoint)
    return {
        "provider": provider,
        "provider_label": definition["label"],
        "model_name": model_name,
        "api_url": endpoint,
        "api_key": api_key,
        "credential_env": definition["credential_env"],
    }


def model_provider_status(*, settings: Settings | None = None) -> dict[str, Any]:
    """Return provider readiness without exposing any API credentials."""
    settings = settings or get_settings()
    result: dict[str, Any] = {}
    for provider, definition in PROVIDER_DEFAULTS.items():
        endpoint = str(getattr(settings, definition["endpoint_setting"]))
        if provider == "openai":
            configured = bool(settings.openai_api_key.strip())
        elif provider == "gemini":
            configured = bool(settings.gemini_api_key.strip())
        elif provider == "openai-compatible":
            configured = bool(settings.openai_compatible_api_key.strip() or settings.vllm_api_key.strip())
        else:
            configured = True
        result[provider] = {
            "label": definition["label"],
            "configured": configured,
            "credential_env": definition["credential_env"],
            "endpoint": endpoint,
            "requires_api_key": provider in {"openai", "gemini"},
        }
    return result
