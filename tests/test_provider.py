import json

import httpx
import pytest

from src.config import Settings
from src.engine.provider import ChatJSONProvider
from src.errors import ProviderError


def settings():
    return Settings(
        _env_file=None,
        openai_api_key="synthetic-secret",
        openai_model="test-model",
        openai_base_url="https://example.test/v1",
    )


def test_http_request_contract_and_response():
    def handler(request):
        assert str(request.url) == "https://example.test/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer synthetic-secret"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert body["messages"][1] == {"role": "user", "content": "Synthetic"}
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
            },
        )

    provider = ChatJSONProvider(settings(), transport=httpx.MockTransport(handler))
    assert provider.complete("JSON instructions", "Synthetic") == "{}"


@pytest.mark.parametrize("status,retryable", [(401, False), (400, False), (429, True), (503, True)])
def test_http_errors_are_sanitized(status, retryable):
    provider = ChatJSONProvider(
        settings(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, text="synthetic-secret and private request")
        ),
    )
    with pytest.raises(ProviderError) as error:
        provider.complete("JSON", "private request")
    assert error.value.retryable is retryable
    assert "synthetic-secret" not in str(error.value)
    assert "private request" not in str(error.value)


def test_timeout_is_retryable():
    def handler(request):
        raise httpx.ReadTimeout("private request", request=request)

    provider = ChatJSONProvider(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="timed out") as error:
        provider.complete("JSON", "private request")
    assert error.value.retryable


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": []},
        {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"refusal": "No"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
    ],
)
def test_invalid_refused_or_truncated_responses_fail(payload):
    provider = ChatJSONProvider(
        settings(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    with pytest.raises(ProviderError):
        provider.complete("JSON", "Synthetic")
