"""Small OpenAI-compatible Chat Completions adapter; retries live in extraction."""

import httpx

from src.config import Settings
from src.errors import ProviderError


class ChatJSONProvider:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None):
        settings.require_llm()
        self.settings = settings
        self.transport = transport

    def complete(self, system: str, query: str) -> str:
        settings = self.settings
        base = str(settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        assert settings.openai_api_key is not None
        try:
            with httpx.Client(
                timeout=settings.afs_request_timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    base + "/chat/completions",
                    headers={
                        "Authorization": "Bearer " + settings.openai_api_key.get_secret_value()
                    },
                    json={
                        "model": settings.openai_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": query},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )
        except httpx.TimeoutException:
            raise ProviderError("Model request timed out.", retryable=True) from None
        except httpx.RequestError:
            raise ProviderError("Model connection failed.", retryable=True) from None
        if response.status_code != 200:
            raise ProviderError(
                f"Model request failed (HTTP {response.status_code}).",
                retryable=response.status_code in (408, 429) or response.status_code >= 500,
            )
        try:
            choice = response.json()["choices"][0]
            message = choice["message"]
            if message.get("refusal") or choice.get("finish_reason") != "stop":
                raise ProviderError("Model refused or did not complete the extraction.")
            content = message["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            return content
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("Model returned an invalid response envelope.") from None
