from __future__ import annotations
import base64
import httpx
from pathlib import Path
from .settings import get_settings
from .schemas import AgentManifest


class LocalInference:
    """OpenAI-compatible local inference adapter. Mock mode keeps the MVP GPU-free."""
    def __init__(self):
        self.settings = get_settings()

    async def complete(self, manifest: AgentManifest, prompt: str, images: list[tuple[str, bytes]] | None = None) -> str:
        if self.settings.mock_inference:
            return self._mock_completion(manifest, prompt, images or [])
        if images:
            endpoint = self.settings.multimodal_api_url
            model = self.settings.multimodal_model
        else:
            endpoint = manifest.model_configuration.endpoint or self.settings.reasoning_api_url
            model = manifest.model_configuration.model_name or self.settings.reasoning_model
        content: list[dict] = [{"type": "text", "text": prompt}]
        for mime, data in images or []:
            encoded = base64.b64encode(data).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": manifest.persona_and_guardrails.system_prompt},
                {"role": "user", "content": content if images else prompt},
            ],
            "temperature": manifest.model_configuration.temperature,
            "max_tokens": manifest.model_configuration.max_tokens,
        }
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{endpoint.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.settings.vllm_api_key}"},
            )
            response.raise_for_status()
            body = response.json()
            return body["choices"][0]["message"]["content"]

    @staticmethod
    def _mock_completion(manifest: AgentManifest, prompt: str, images: list[tuple[str, bytes]]) -> str:
        name = manifest.agent_metadata.display_name
        attachment_note = f" I received {len(images)} image attachment(s); mock mode does not visually inspect pixels." if images else ""
        return f"[{name} — MOCK MODE] I analysed the supplied request using the configured workflow rules.{attachment_note}\n\nRequest context: {prompt[:700]}\n\nThis is a development simulation, not a production decision."
