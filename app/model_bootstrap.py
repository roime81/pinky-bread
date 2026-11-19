from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .settings import get_settings


def ollama_service_root(api_url: str) -> str:
    """Convert an OpenAI-compatible Ollama URL to the native Ollama API root."""
    root = api_url.strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root


def _installed_model_names(payload: dict[str, Any]) -> set[str]:
    return {
        str(item.get("name") or item.get("model") or "")
        for item in payload.get("models", [])
        if isinstance(item, dict)
    }


async def ensure_default_model() -> None:
    settings = get_settings()
    if settings.mock_inference:
        print("MOCK_INFERENCE=true; skipping automatic Ollama model bootstrap.")
        return
    if settings.model_provider != "ollama":
        print(f"MODEL_PROVIDER={settings.model_provider}; skipping Ollama model bootstrap.")
        return

    root = ollama_service_root(settings.reasoning_api_url)
    model = settings.reasoning_model
    timeout = httpx.Timeout(2400.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        tags_response = await client.get(f"{root}/api/tags")
        tags_response.raise_for_status()
        installed = _installed_model_names(tags_response.json())
        if any(name == model or name.split(":")[0] == model.split(":")[0] for name in installed):
            print(f"Ollama model already installed: {model}")
            return

        print(f"Pulling Ollama model {model}. The first startup may take a while.")
        response = await client.post(
            f"{root}/api/pull",
            json={"name": model, "stream": False},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise RuntimeError(f"Ollama failed to pull {model}: {payload['error']}")
        print(f"Ollama model is ready: {model}")


def main() -> None:
    asyncio.run(ensure_default_model())


if __name__ == "__main__":
    main()
