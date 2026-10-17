"""Small OpenAI-compatible Chat Completions adapter; retries live in extraction."""

import httpx

from src.config import Settings
from src.errors import ProviderError


class ChatJSONProvider:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None):
        settings.require_llm()
        self.settings = settings
        self.transport = transport

    def _post(self, base: str, messages: list[dict], *, json_mode: bool) -> httpx.Response:
        settings = self.settings
        assert settings.openai_api_key is not None
        payload: dict = {"model": settings.openai_model, "messages": messages}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            with httpx.Client(
                timeout=settings.afs_request_timeout_seconds,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                return client.post(
                    base + "/chat/completions",
                    headers={
                        "Authorization": "Bearer " + settings.openai_api_key.get_secret_value()
                    },
                    json=payload,
                )
        except httpx.TimeoutException:
            raise ProviderError("Model request timed out.", retryable=True) from None
        except httpx.RequestError:
            raise ProviderError("Model connection failed.", retryable=True) from None

    @staticmethod
    def _rejects_json_mode(response: httpx.Response) -> bool:
        """Conservatively detect a response_format rejection without leaking the body."""
        try:
            text = response.text.lower()
        except Exception:
            return False
        return "response_format" in text or "json_object" in text or "json mode" in text

    def complete(self, system: str, query: str) -> str:
        settings = self.settings
        base = str(settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        assert settings.openai_api_key is not None
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ]
        # Prefer native JSON mode; fall back to a plain request for OpenAI-compatible
        # endpoints that reject response_format. The system prompt already demands
        # JSON-only output, so correctness does not depend on the server-side flag.
        response = self._post(base, messages, json_mode=True)
        if response.status_code in (400, 422) and self._rejects_json_mode(response):
            response = self._post(base, messages, json_mode=False)
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
