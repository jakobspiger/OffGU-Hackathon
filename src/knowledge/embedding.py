"""OpenAI-compatible /embeddings adapter for the T04 vector index.

This mirrors the httpx pattern of ``src/engine/provider.py`` (Bearer key,
timeout/retry, sanitized errors) but lives in its own file so the T06 provider
stays untouched. It is only used in the *vector* retrieval mode:

    * ``scripts/build_index.py`` embeds every ``Evidence.text`` once at build
      time and persists the vectors (``embeddings.jsonl``).
    * ``src/knowledge/retrieval.py`` embeds the *query* at query time.

Vector mode is opt-in: it runs only when ``Settings().afs_embedding_model`` is
set (non-empty). With no embedding model configured the project stays in the
deterministic lexical mode and this module is never called.

The embedding key/secret is never logged and never raised in an error message.
Failures surface as :class:`src.errors.RetrievalError` so callers can present a
stable message. The HTTP client accepts an injectable ``httpx`` transport, so
tests exercise the request/response handling with a mock transport and perform
no real network call.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.errors import RetrievalError

if TYPE_CHECKING:  # pragma: no cover - import guard for type checkers only
    import httpx

    from src.config import Settings


def _require_embedding_config(settings: "Settings") -> tuple[str, str, str]:
    """Return ``(base, model, key)`` or raise a sanitized RetrievalError.

    The embedding path needs an OpenAI-compatible endpoint: an embedding model
    name, an API key and (optionally) a base URL. No secret is ever included in
    the raised message.
    """

    model = settings.afs_embedding_model
    if not model:
        raise RetrievalError(
            "Vector mode requires AFS_EMBEDDING_MODEL to be set; the index is lexical."
        )
    if settings.openai_api_key is None:
        raise RetrievalError("Embedding requests require OPENAI_API_KEY to be configured.")
    base = str(settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    return base, model, settings.openai_api_key.get_secret_value()


def embed_texts(
    texts: list[str],
    settings: "Settings",
    *,
    transport: "httpx.BaseTransport | None" = None,
) -> list[list[float]]:
    """Embed ``texts`` via an OpenAI-compatible ``/embeddings`` endpoint.

    Returns one vector (``list[float]``) per input text, in input order. Raises
    :class:`src.errors.RetrievalError` on any configuration, network, HTTP or
    envelope error, never leaking the API key or raw response body.

    ``transport`` lets tests inject a mock ``httpx`` transport so no real
    network call happens; production passes ``None`` (real transport).
    """

    import httpx  # imported lazily so lexical mode never needs httpx installed

    if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
        raise RetrievalError("embed_texts expects a list of strings.")
    if not texts:
        return []

    base, model, key = _require_embedding_config(settings)
    payload = {"model": model, "input": texts}
    retries = max(0, int(settings.afs_max_retries))

    last_error = "Embedding request failed."
    for attempt in range(retries + 1):
        try:
            with httpx.Client(
                timeout=settings.afs_request_timeout_seconds,
                transport=transport,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    base + "/embeddings",
                    headers={"Authorization": "Bearer " + key},
                    json=payload,
                )
        except httpx.TimeoutException:
            last_error = "Embedding request timed out."
        except httpx.RequestError:
            last_error = "Embedding connection failed."
        else:
            if response.status_code == 200:
                return _parse_embeddings(response, expected=len(texts))
            retryable = response.status_code in (408, 429) or response.status_code >= 500
            last_error = f"Embedding request failed (HTTP {response.status_code})."
            if not retryable:
                raise RetrievalError(last_error)
        if attempt < retries:
            time.sleep(0.0)
    raise RetrievalError(last_error)


def _parse_embeddings(response: "httpx.Response", *, expected: int) -> list[list[float]]:
    """Extract vectors from an OpenAI-compatible embeddings envelope.

    The envelope is ``{"data": [{"index": i, "embedding": [...]}, ...]}``.
    Vectors are returned ordered by ``index`` so the result matches input
    order even if the server reorders them. Never leaks the raw body.
    """

    try:
        data = response.json()["data"]
        ordered = sorted(data, key=lambda item: int(item["index"]))
        vectors: list[list[float]] = []
        for item in ordered:
            vector = [float(x) for x in item["embedding"]]
            if not vector:
                raise ValueError
            vectors.append(vector)
    except (ValueError, KeyError, IndexError, TypeError):
        raise RetrievalError("Embedding endpoint returned an invalid response envelope.") from None
    if len(vectors) != expected:
        raise RetrievalError("Embedding endpoint returned a mismatched number of vectors.")
    return vectors


__all__ = ["embed_texts"]
