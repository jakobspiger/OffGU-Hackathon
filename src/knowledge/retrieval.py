"""Public retrieval entry point (T04): hybrid vector + lexical over the T02 index.

``retrieve(query, k)`` is the shared :class:`src.contracts.Retriever` adapter.
It reads ONLY ``data/index/evidence.jsonl`` (resolved from
``Settings().afs_index_dir``), so the challenge scenarios H01-H06 and the
development references (BRIEF/DOCX ReferenceRecords) are structurally excluded:
they are never written to ``evidence.jsonl`` by T02's build.

Mode (auto-switch, no silent fallback to an invented model)
-----------------------------------------------------------
    * **vector** when ``afs_embedding_model`` is set (non-empty) AND an
      embeddings index (``embeddings.jsonl``) exists next to ``evidence.jsonl``.
      The query is embedded once per call and scored by cosine similarity
      against the stored evidence vectors.
    * **lexical** otherwise (the real default: no embedding model is enabled on
      the configured endpoint). A deterministic, unicode-/case-robust token
      score over the evidence text is used. No network, no key.

In both modes ``business_context`` evidence (S05/S06) is DOWN-RANKED, never
filtered out: it stays citable as context but can never outrank technical or
research evidence as a performance claim.

Returned evidence is sorted by descending final score (ties broken by
``evidence_id`` for reproducibility) and carries the ``score`` field set to the
final hit score. All other fields (``evidence_id``, ``page`` incl. S06's
``None``, ...) are left unchanged.

Sandbox note
------------
The scoring helpers (``_cosine``, ``_lexical_score``, ``_rank_weight``,
``_normalize``, ``_rank_hits``) are pure stdlib and testable without pydantic or
httpx. Only loading real :class:`Evidence` objects and the vector/query
embedding path need the production libraries; those are import-guarded in the
tests.
"""

from __future__ import annotations

import json
import math
import os
import threading
import unicodedata
from typing import TYPE_CHECKING, Any

from src.errors import RetrievalError
from src.knowledge.embedding import embed_texts

if TYPE_CHECKING:  # pragma: no cover - type-checker import only
    from src.models import Evidence

# Down-rank weight for business_context (S05/S06): small but non-zero so the
# text stays citable as context yet never outranks technical/research evidence
# as a performance claim. Rank weights multiply the base relevance score.
_RANK_WEIGHTS: dict[str, float] = {
    "technical": 1.0,
    "research": 1.0,
    "business_context": 0.15,
}


# ---------------------------------------------------------------------------
# Pure-logic scoring helpers (stdlib only; no pydantic / numpy / httpx).
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    """NFC + casefold + whitespace-collapse, consistent with the V-2 style.

    Deterministic and case/unicode robust so lexical scoring is stable across
    presentation differences without stemming or synonyms.
    """

    normalized = unicodedata.normalize("NFC", text)
    return " ".join(normalized.split()).casefold()


def _tokenize(text: str) -> list[str]:
    """Split normalized text into alphanumeric tokens (non-alnum is a boundary)."""

    tokens: list[str] = []
    current: list[str] = []
    for char in _normalize(text):
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _lexical_score(query: str, text: str) -> float:
    """Deterministic lexical relevance of ``text`` for ``query``.

    Token-overlap with term-frequency weighting, length-normalized so long
    passages do not win on size alone. Returns 0.0 when there is no overlap.
    """

    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    text_tokens = _tokenize(text)
    if not text_tokens:
        return 0.0

    counts: dict[str, int] = {}
    for token in text_tokens:
        counts[token] = counts.get(token, 0) + 1

    unique_query = set(query_tokens)
    matched_terms = 0
    total_hits = 0
    for term in unique_query:
        hits = counts.get(term, 0)
        if hits:
            matched_terms += 1
            total_hits += hits

    if matched_terms == 0:
        return 0.0

    # Coverage of the query (how many distinct query terms appear) dominates;
    # frequency adds a small, saturating bonus; length-normalized by the text
    # token count so verbose passages are not favoured.
    coverage = matched_terms / len(unique_query)
    frequency_bonus = total_hits / (total_hits + len(text_tokens))
    return coverage + 0.25 * frequency_bonus


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors, pure Python.

    Returns 0.0 for a zero-magnitude or length-mismatched vector rather than
    raising, so a single degenerate stored vector cannot abort a query.
    """

    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def _rank_weight(evidence: Any) -> float:
    """Source-rank multiplier from ``purpose``.

    technical and research rank ahead of business_context (S05/S06), which is
    down-ranked but not zeroed. Works on any object/dict exposing ``purpose``.
    """

    purpose = _get(evidence, "purpose")
    return _RANK_WEIGHTS.get(purpose, 1.0)


def _get(evidence: Any, field: str) -> Any:
    """Read ``field`` from an Evidence model or a plain dict (test stub)."""

    if isinstance(evidence, dict):
        return evidence.get(field)
    return getattr(evidence, field, None)


def _rank_hits(
    query: str,
    records: list[Any],
    k: int,
    *,
    query_vector: list[float] | None = None,
    vectors_by_id: dict[str, list[float]] | None = None,
) -> list[tuple[Any, float]]:
    """Score, down-rank and order records; return the top ``k`` with scores.

    Vector mode (``query_vector`` + ``vectors_by_id`` given): base score is the
    cosine similarity of the query vector against each record's stored vector.
    Lexical mode: base score is :func:`_lexical_score` over the record text.
    The business_context down-rank (:func:`_rank_weight`) is applied in BOTH
    modes. Ordering is by descending final score, ties broken by ``evidence_id``
    ascending, for reproducible output.
    """

    scored: list[tuple[Any, float]] = []
    for record in records:
        if query_vector is not None and vectors_by_id is not None:
            evidence_id = _get(record, "evidence_id")
            stored = vectors_by_id.get(evidence_id)
            base = _cosine(query_vector, stored) if stored is not None else 0.0
        else:
            base = _lexical_score(query, _get(record, "text") or "")
        final = base * _rank_weight(record)
        scored.append((record, final))

    scored.sort(key=lambda item: (-item[1], str(_get(item[0], "evidence_id"))))
    return scored[:k]


# ---------------------------------------------------------------------------
# Index loading + per-process cache.
# ---------------------------------------------------------------------------
class _IndexCache:
    """Loaded index snapshot cached per process (UI/batch do not reload)."""

    def __init__(
        self,
        records: list[Any],
        vectors_by_id: dict[str, list[float]] | None,
        mode: str,
    ) -> None:
        self.records = records
        self.vectors_by_id = vectors_by_id
        self.mode = mode


_cache: _IndexCache | None = None
_cache_lock = threading.Lock()


def reset_cache() -> None:
    """Drop the cached index (tests call this between index fixtures)."""

    global _cache
    with _cache_lock:
        _cache = None


def _read_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RetrievalError(f"Index file {path!r} is corrupt at line {lineno}.") from exc
    return rows


def _load_index(settings: Any) -> _IndexCache:
    """Load evidence (and vectors if present) into the cache.

    Raises :class:`RetrievalError` (NOT ComponentNotReadyError) when the index
    directory or ``evidence.jsonl`` is missing.
    """

    from src.models import Evidence

    index_dir = str(settings.afs_index_dir)
    evidence_path = os.path.join(index_dir, "evidence.jsonl")
    if not os.path.isfile(evidence_path):
        raise RetrievalError(
            f"Knowledge index is unavailable: {evidence_path!r} not found. "
            "Build it with `python scripts/build_index.py`."
        )

    records: list[Any] = []
    with open(evidence_path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                records.append(Evidence.model_validate_json(line))
            except Exception as exc:  # noqa: BLE001 - surface as retrieval error
                raise RetrievalError(
                    f"Index evidence line {lineno} is not valid Evidence: {exc}"
                ) from exc

    # Vector mode is only active when an embedding model is configured AND the
    # embeddings index exists next to evidence.jsonl. No silent fallback to an
    # invented model: a missing model name or missing vectors => lexical.
    embeddings_path = os.path.join(index_dir, "embeddings.jsonl")
    vectors_by_id: dict[str, list[float]] | None = None
    mode = "lexical"
    if getattr(settings, "afs_embedding_model", None) and os.path.isfile(embeddings_path):
        vectors_by_id = {}
        for row in _read_jsonl(embeddings_path):
            evidence_id = row.get("evidence_id")
            vector = row.get("vector")
            if isinstance(evidence_id, str) and isinstance(vector, list):
                vectors_by_id[evidence_id] = [float(x) for x in vector]
        mode = "vector"

    return _IndexCache(records=records, vectors_by_id=vectors_by_id, mode=mode)


def _get_index(settings: Any) -> _IndexCache:
    global _cache
    with _cache_lock:
        if _cache is None:
            _cache = _load_index(settings)
        return _cache


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------
def retrieve(query: str, k: int = 8) -> list[Evidence]:
    """Return the top-``k`` Evidence for ``query``, ranked by descending score.

    Input validation (unchanged from the T01 stub): ``query`` must be a
    non-empty string and ``k`` must be an ``int`` in ``1..50``; otherwise
    ``ValueError``. A missing index raises :class:`RetrievalError`.
    """

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")
    if type(k) is not int or not 1 <= k <= 50:
        raise ValueError("k must be an integer between 1 and 50.")

    from src.config import Settings

    settings = Settings()
    index = _get_index(settings)

    query_vector: list[float] | None = None
    if index.mode == "vector" and index.vectors_by_id:
        query_vector = embed_texts([query], settings)[0]

    top = _rank_hits(
        query,
        index.records,
        k,
        query_vector=query_vector,
        vectors_by_id=index.vectors_by_id if index.mode == "vector" else None,
    )

    results: list[Evidence] = []
    for record, score in top:
        results.append(record.model_copy(update={"score": score}))
    return results


__all__ = ["retrieve", "reset_cache"]
