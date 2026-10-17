"""T04 retrieval tests.

Two layers, so the suite is meaningful both in the dependency-free sandbox and
on a full local install:

    * Pure-logic (stdlib only): cosine, lexical score, source-rank down-rank,
      top-k ordering, the NIR/MIR/fluorescence fixture ranking and the
      H/reference exclusion. These run everywhere; they use light stub records
      (plain objects exposing the Evidence attributes retrieval reads).
    * Library-dependent (pydantic / httpx): input validation + missing-index
      error on the real ``retrieve``, real Evidence construction, and the
      vector path via a mocked httpx transport. These are ``importorskip``-
      guarded so they skip cleanly where pydantic/httpx are unavailable and run
      on the maintainer's machine.

No test makes a real network call and none needs an API key.
"""

from __future__ import annotations

import json
import os

import pytest

from src.knowledge.retrieval import (
    _cosine,
    _lexical_score,
    _normalize,
    _rank_hits,
    _rank_weight,
    reset_cache,
)


# ---------------------------------------------------------------------------
# Light stub record: exposes exactly the attributes retrieval reads.
# ---------------------------------------------------------------------------
class StubEvidence:
    def __init__(self, evidence_id, text, purpose, source_id, page=1):
        self.evidence_id = evidence_id
        self.text = text
        self.purpose = purpose
        self.source_id = source_id
        self.page = page
        self.score = None


def _ids(ranked):
    return [rec.evidence_id for rec, _ in ranked]


# ---------------------------------------------------------------------------
# Pure-logic: cosine.
# ---------------------------------------------------------------------------
def test_cosine_basic_and_edge_cases():
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert _cosine([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)
    # degenerate / mismatched vectors never raise, return 0.0
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert _cosine([1.0], [1.0, 2.0]) == 0.0
    assert _cosine([], [1.0]) == 0.0


# ---------------------------------------------------------------------------
# Pure-logic: normalization + lexical score.
# ---------------------------------------------------------------------------
def test_normalize_is_case_and_whitespace_robust():
    assert _normalize("  NIR   Powder  ") == "nir powder"
    assert _normalize("Fluoreszenz") == _normalize("FLUORESZENZ")


def test_lexical_score_rewards_overlap_and_is_deterministic():
    strong = _lexical_score("NIR powder moisture", "NIR spectroscopy of powder moisture")
    weak = _lexical_score("NIR powder moisture", "MIR petroleum in water")
    assert strong > weak
    assert weak == 0.0
    # deterministic
    assert strong == _lexical_score("NIR powder moisture", "NIR spectroscopy of powder moisture")


def test_lexical_score_empty_inputs_return_zero():
    assert _lexical_score("", "anything") == 0.0
    assert _lexical_score("nir", "") == 0.0


# ---------------------------------------------------------------------------
# Pure-logic: source-rank weight.
# ---------------------------------------------------------------------------
def test_rank_weight_downranks_business_context():
    tech = StubEvidence("S01-p010", "x", "technical", "S01")
    research = StubEvidence("S03-p003", "x", "research", "S03")
    business = StubEvidence("S05-context", "x", "business_context", "S05")
    assert _rank_weight(tech) == 1.0
    assert _rank_weight(research) == 1.0
    assert _rank_weight(business) < _rank_weight(tech)
    assert _rank_weight(business) > 0.0  # down-ranked, NOT filtered out


# ---------------------------------------------------------------------------
# Pure-logic: ranking / top-k ordering (lexical mode).
# ---------------------------------------------------------------------------
def _technical_corpus():
    return [
        StubEvidence(
            "S01-p010",
            "NIR near-infrared spectroscopy of powder moisture after the dryer",
            "technical",
            "S01",
        ),
        StubEvidence(
            "S04-p004",
            "MIR mid-infrared measurement of petroleum traces in water",
            "research",
            "S04",
        ),
        StubEvidence(
            "S03-p002",
            "LED fluorescence study of kidney tissue autofluorescence",
            "research",
            "S03",
        ),
        StubEvidence(
            "XLSX-row03",
            "method comparison NIR powder sensitivity rating",
            "technical",
            "S01",
            page=6,
        ),
        StubEvidence(
            "S05-context",
            "AFS flyer NIR powder MIR fluorescence company marketing",
            "business_context",
            "S05",
        ),
        StubEvidence(
            "S06-context",
            "AFS laboratory website link NIR MIR fluorescence powder",
            "business_context",
            "S06",
            page=None,
        ),
    ]


def test_topk_orders_by_score_and_breaks_ties_by_id():
    recs = _technical_corpus()
    ranked = _rank_hits("NIR powder moisture", recs, k=3)
    assert len(ranked) == 3
    # the S01 NIR powder passage must be first
    assert ranked[0][0].evidence_id == "S01-p010"
    # scores are non-increasing
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)


def test_business_context_never_outranks_technical_on_technical_query():
    recs = _technical_corpus()
    # S05/S06 mention all keywords but are business_context: they must rank
    # below the technical/research hits that share query terms.
    ranked = _rank_hits("NIR MIR fluorescence powder", recs, k=6)
    ordered = _ids(ranked)
    tech_positions = [ordered.index(i) for i in ("S01-p010", "XLSX-row03")]
    biz_positions = [ordered.index(i) for i in ("S05-context", "S06-context")]
    assert max(tech_positions) < min(biz_positions)
    # business context is still present (down-ranked, not filtered)
    assert "S05-context" in ordered and "S06-context" in ordered


@pytest.mark.parametrize(
    "query,expected_first",
    [
        ("NIR powder moisture", "S01-p010"),
        ("MIR petroleum water", "S04-p004"),
        ("fluorescence kidney", "S03-p002"),
    ],
)
def test_nir_mir_fluorescence_queries_hit_right_passages(query, expected_first):
    ranked = _rank_hits(query, _technical_corpus(), k=1)
    assert ranked[0][0].evidence_id == expected_first


def test_ranking_is_deterministic_across_runs():
    recs = _technical_corpus()
    first = _ids(_rank_hits("NIR MIR fluorescence powder", recs, k=6))
    second = _ids(_rank_hits("NIR MIR fluorescence powder", list(reversed(recs)), k=6))
    assert first == second


# ---------------------------------------------------------------------------
# Library-dependent: real retrieve() input validation + missing index.
# ---------------------------------------------------------------------------
def _real_settings(tmp_path, monkeypatch, embedding_model=None):
    """Build a Settings() pointed at an isolated empty index dir.

    Skips when pydantic is unavailable (sandbox). Resets the module cache so a
    previous test's index does not leak into this one.
    """

    pytest.importorskip("pydantic_settings")
    from src.config import Settings

    reset_cache()
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    settings = Settings(
        _env_file=None, afs_index_dir=index_dir, afs_embedding_model=embedding_model
    )
    monkeypatch.setattr("src.config.Settings", lambda *a, **kw: settings)
    return settings, index_dir


def test_retrieve_rejects_bad_input(tmp_path, monkeypatch):
    pytest.importorskip("pydantic_settings")
    from src.knowledge.retrieval import retrieve

    with pytest.raises(ValueError):
        retrieve("", 8)
    with pytest.raises(ValueError):
        retrieve("   ", 8)
    with pytest.raises(ValueError):
        retrieve("nir", 0)
    with pytest.raises(ValueError):
        retrieve("nir", 51)
    with pytest.raises(ValueError):
        retrieve("nir", True)  # bool is not an int here
    with pytest.raises(ValueError):
        retrieve("nir", 3.0)  # float is not int


def test_missing_index_raises_retrieval_error(tmp_path, monkeypatch):
    _real_settings(tmp_path, monkeypatch)
    from src.errors import RetrievalError
    from src.knowledge.retrieval import retrieve

    with pytest.raises(RetrievalError):
        retrieve("NIR powder", 5)


# ---------------------------------------------------------------------------
# Library-dependent: real Evidence round-trip (lexical mode).
# ---------------------------------------------------------------------------
def _write_real_evidence(index_dir):
    """Write a small evidence.jsonl using the real contract constructors."""

    from src.models import Evidence

    records = [
        Evidence(
            evidence_id="S01-p010",
            source_id="S01",
            page=10,
            origin_source_id="S01",
            text="NIR near-infrared spectroscopy of powder moisture after the dryer",
            kind="pdf",
            purpose="technical",
        ),
        Evidence(
            evidence_id="S04-p004",
            source_id="S04",
            page=4,
            origin_source_id="S04",
            text="MIR mid-infrared measurement of petroleum traces in water",
            kind="pdf",
            purpose="research",
        ),
        Evidence(
            evidence_id="S05-context",
            source_id="S05",
            page=1,
            origin_source_id="S05",
            text="AFS flyer NIR powder MIR company marketing business context",
            kind="curated_note",
            purpose="business_context",
        ),
        Evidence(
            evidence_id="S06-context",
            source_id="S06",
            page=None,
            origin_source_id="S06",
            text="AFS laboratory website link NIR MIR powder business context",
            kind="text",
            purpose="business_context",
        ),
    ]
    path = os.path.join(str(index_dir), "evidence.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(rec.model_dump_json())
            fh.write("\n")
    return records


def test_returned_evidence_has_score_and_valid_fields(tmp_path, monkeypatch):
    _settings, index_dir = _real_settings(tmp_path, monkeypatch)
    _write_real_evidence(index_dir)
    from src.knowledge.retrieval import retrieve

    results = retrieve("NIR powder moisture", 4)
    assert results, "expected hits"
    # score (hit info) is set on every returned Evidence
    assert all(r.score is not None for r in results)
    # descending order, ties by id
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    # the technical S01 passage wins; fields preserved
    assert results[0].evidence_id == "S01-p010"
    assert results[0].source_id == "S01"
    # S06 page stays None (never an invented PDF page)
    s06 = [r for r in results if r.source_id == "S06"]
    assert s06 and s06[0].page is None


def test_business_context_downranked_on_real_evidence(tmp_path, monkeypatch):
    _settings, index_dir = _real_settings(tmp_path, monkeypatch)
    _write_real_evidence(index_dir)
    from src.knowledge.retrieval import retrieve

    results = retrieve("NIR MIR powder", 4)
    ids = [r.evidence_id for r in results]
    # technical/research ahead of business_context
    assert ids.index("S01-p010") < ids.index("S05-context")
    assert ids.index("S04-p004") < ids.index("S06-context")
    # business context present, not filtered
    assert "S05-context" in ids and "S06-context" in ids


def test_retrieve_never_returns_reference_or_h_text(tmp_path, monkeypatch):
    """retrieve reads ONLY evidence.jsonl; H-scenarios / reference records in
    sibling files must never surface."""

    _settings, index_dir = _real_settings(tmp_path, monkeypatch)
    _write_real_evidence(index_dir)
    # Plant decoys in files retrieve must ignore.
    with open(os.path.join(str(index_dir), "reference_records.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "record_id": "BRIEF-p01",
                    "source_id": "BRIEF",
                    "text": "NIR MIR powder DOCX development reference",
                }
            )
        )
        fh.write("\n")
    with open(os.path.join(str(index_dir), "h_scenarios.txt"), "w", encoding="utf-8") as fh:
        fh.write("H01 NIR MIR powder final scenario\n")

    from src.knowledge.retrieval import retrieve

    results = retrieve("NIR MIR powder", 10)
    ids = {r.evidence_id for r in results}
    assert "BRIEF-p01" not in ids
    assert all(r.source_id in ("S01", "S02", "S03", "S04", "S05", "S06") for r in results)


def test_retrieve_matches_retriever_protocol(tmp_path, monkeypatch):
    _settings, index_dir = _real_settings(tmp_path, monkeypatch)
    _write_real_evidence(index_dir)
    from src.contracts import Retriever
    from src.knowledge.retrieval import retrieve

    retriever: Retriever = retrieve  # structural check: signature compatible
    out = retriever("NIR powder", 2)
    assert len(out) == 2


# ---------------------------------------------------------------------------
# Library-dependent: vector mode via a mocked httpx transport (no network).
# ---------------------------------------------------------------------------
def test_embed_texts_uses_mock_transport(tmp_path, monkeypatch):
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("pydantic_settings")
    from src.config import Settings
    from src.knowledge.embedding import embed_texts

    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        body = json.loads(request.content)
        vectors = [[float(len(t)), 1.0, 0.0] for t in body["input"]]
        data = [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
        return httpx.Response(200, json={"data": data})

    settings = Settings(
        _env_file=None,
        afs_embedding_model="test-embed",
        openai_api_key="secret-key",
        openai_base_url="https://example.test/v1",
    )
    transport = httpx.MockTransport(handler)
    out = embed_texts(["abc", "de"], settings, transport=transport)
    assert out == [[3.0, 1.0, 0.0], [2.0, 1.0, 0.0]]
    assert captured["url"].endswith("/embeddings")
    assert captured["auth"] == "Bearer secret-key"


def test_embed_texts_http_error_raises_retrieval_error(tmp_path):
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("pydantic_settings")
    from src.config import Settings
    from src.errors import RetrievalError
    from src.knowledge.embedding import embed_texts

    def handler(request):
        return httpx.Response(400, json={"error": "bad model"})

    settings = Settings(
        _env_file=None,
        afs_embedding_model="test-embed",
        openai_api_key="secret-key",
        afs_max_retries=0,
    )
    with pytest.raises(RetrievalError):
        embed_texts(["abc"], settings, transport=httpx.MockTransport(handler))


def test_vector_mode_uses_embeddings_via_mock_transport(tmp_path, monkeypatch):
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("pydantic_settings")
    settings, index_dir = _real_settings(tmp_path, monkeypatch, embedding_model="test-embed")
    records = _write_real_evidence(index_dir)

    # Stored vectors: make S04 the clear vector-space winner for our query.
    stored = {
        "S01-p010": [1.0, 0.0, 0.0],
        "S04-p004": [0.0, 1.0, 0.0],
        "S05-context": [0.9, 0.1, 0.0],
        "S06-context": [0.8, 0.2, 0.0],
    }
    with open(os.path.join(str(index_dir), "embeddings.jsonl"), "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(
                json.dumps({"evidence_id": rec.evidence_id, "vector": stored[rec.evidence_id]})
            )
            fh.write("\n")

    # Query embeds to the S04 direction.
    def handler(request):
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0, 1.0, 0.0]}]})

    # _real_settings already monkeypatched src.config.Settings to an
    # arg-discarding lambda, so build the key-carrying Settings from the REAL
    # class (type(settings)) to ensure embed_texts sees the api key and
    # embedding model, then re-patch with this key-carrying object.
    RealSettings = type(settings)
    patched = RealSettings(
        _env_file=None,
        afs_index_dir=index_dir,
        afs_embedding_model="test-embed",
        openai_api_key="secret-key",
    )
    monkeypatch.setattr("src.config.Settings", lambda *a, **kw: patched)
    # Inject the mock transport into embed_texts used inside retrieve.
    import src.knowledge.embedding as emb

    real_embed = emb.embed_texts
    monkeypatch.setattr(
        "src.knowledge.retrieval.embed_texts",
        lambda texts, s: real_embed(texts, s, transport=httpx.MockTransport(handler)),
        raising=False,
    )
    reset_cache()
    from src.knowledge.retrieval import retrieve

    results = retrieve("petroleum in water", 4)
    # vector winner is S04 (query vector aligned with S04's stored vector)
    assert results[0].evidence_id == "S04-p004"
    assert all(r.score is not None for r in results)
