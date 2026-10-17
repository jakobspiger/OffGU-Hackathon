"""Tests for the ingestion logic (AP3/AP4/AP5) against the shared T01 contract.

The ingestion modules import the shared Pydantic contract from ``src.models``,
so the whole module is skipped when pydantic is not installed (the authoring
sandbox has PyPI/uv blocked). On the maintainer's machine ``uv sync --locked``
provides pydantic and the full suite runs. The library-dependent code paths
(PyMuPDF / python-docx / openpyxl) are additionally guarded with
``pytest.importorskip``.
"""

from __future__ import annotations

import json
import os

import pytest

pytest.importorskip("pydantic", reason="pydantic is provided by `uv sync --locked`")

from tests.conftest import H_SCENARIOS_PATH, MATERIALS_DIR, S02_NOTES_PATH  # noqa: E402

from src.knowledge import ingest  # noqa: E402
from src.knowledge.types import Evidence, ReferenceRecord, to_dict  # noqa: E402


# ---------------------------------------------------------------------------
# evidence-id determinism
# ---------------------------------------------------------------------------
def test_evidence_ids_are_deterministic_and_formatted():
    assert ingest.pdf_evidence_id("S01", 10) == "S01-p010"
    assert ingest.pdf_evidence_id("S01", 1) == "S01-p001"
    assert ingest.table_evidence_id(3) == "XLSX-row03"
    assert ingest.s02_note_evidence_id(13) == "S02-note-p13"
    assert ingest.business_evidence_id("S06") == "S06-context"
    assert ingest.business_evidence_id("S05") == "S05-context"


# ---------------------------------------------------------------------------
# curated S02 notes (YAML, no PyYAML needed via fallback parser)
# ---------------------------------------------------------------------------
def test_s02_notes_load_and_are_pending_visual_check():
    assert os.path.isfile(S02_NOTES_PATH), "s02_notes.yaml fixture must exist"
    recs = ingest.ingest_curated_s02_notes(S02_NOTES_PATH)
    assert recs, "expected curated S02 notes"
    pages = {r.page for r in recs}
    # Key image-heavy slides from the ticket: 6 and 13-16.
    for required in (6, 13, 14, 15, 16):
        assert required in pages, f"missing S02 note for p.{required}"
    for r in recs:
        assert r.source_id == "S02"
        assert r.origin_source_id == "S02"
        assert r.kind == "curated_note"
        assert r.purpose == "technical"
        assert r.evidence_id == ingest.s02_note_evidence_id(r.page)
        # Review is proven by the status field + review_note, never a text hack.
        assert r.review_status == "pending_visual_check"
        assert r.review_note
        assert "provenance" not in r.text.lower()


def test_s02_notes_graceful_on_missing_file(tmp_path):
    missing = tmp_path / "nope.yaml"
    assert ingest.ingest_curated_s02_notes(missing) == []


# ---------------------------------------------------------------------------
# business context: S05 + S06
# ---------------------------------------------------------------------------
def test_s06_is_text_business_context_with_no_page():
    recs = ingest.ingest_business_context(MATERIALS_DIR)
    s06 = [r for r in recs if r.source_id == "S06"]
    assert len(s06) == 1
    assert s06[0].page is None
    assert s06[0].kind == "text"
    assert s06[0].purpose == "business_context"
    assert "mirphotonics.com/laboratory" in s06[0].text


def test_s05_is_curated_note_business_context_when_present():
    recs = ingest.ingest_business_context(MATERIALS_DIR)
    s05 = [r for r in recs if r.source_id == "S05"]
    if s05:  # only when the flyer file is present
        assert s05[0].kind == "curated_note"
        assert s05[0].page == 1
        assert s05[0].purpose == "business_context"


def test_s05_never_gets_technical_purpose():
    """[V-4] safeguard: S05 must never be labelled technical evidence."""

    # Directly via the helper.
    s05 = ingest.make_business_evidence("S05", "flyer description [business context only]")
    assert s05.purpose == "business_context"
    assert s05.purpose != "technical"
    # And via the real ingestion path, if the flyer is present.
    for rec in ingest.ingest_business_context(MATERIALS_DIR):
        if rec.source_id == "S05":
            assert rec.purpose != "technical"


# ---------------------------------------------------------------------------
# BRIEF / DOCX are ReferenceRecord, never Evidence
# ---------------------------------------------------------------------------
def test_brief_and_docx_produce_reference_records_not_evidence():
    brief = ingest.make_reference_record("BRIEF", 1, "challenge brief text", page=1)
    docx = ingest.make_reference_record("DOCX", 1, "development reference text")
    assert isinstance(brief, ReferenceRecord)
    assert isinstance(docx, ReferenceRecord)
    assert not isinstance(brief, Evidence)
    assert not isinstance(docx, Evidence)
    assert brief.source_id == "BRIEF"
    assert docx.source_id == "DOCX"
    assert brief.record_id == "BRIEF-p01"
    assert docx.record_id == "DOCX-p0001"
    # BRIEF/DOCX are not indexable evidence sources.
    assert "BRIEF" not in ingest.INDEXABLE_SOURCES
    assert "DOCX" not in ingest.INDEXABLE_SOURCES


# ---------------------------------------------------------------------------
# schema shape: every evidence record has evidence_id + source_id; pages 1-based
# ---------------------------------------------------------------------------
def _build_lib_free_evidence() -> list[Evidence]:
    """Collect the evidence we can build WITHOUT the optional parser libraries."""

    records: list[Evidence] = []
    records.extend(ingest.ingest_curated_s02_notes(S02_NOTES_PATH))
    records.extend(ingest.ingest_business_context(MATERIALS_DIR))
    return records


def test_pages_are_1_based_and_have_ids():
    for rec in _build_lib_free_evidence():
        assert rec.source_id, "every evidence record needs a source_id"
        assert rec.evidence_id, "every evidence record needs a stable evidence_id"
        assert rec.origin_source_id, "every evidence record needs an origin_source_id"
        if rec.page is not None:
            assert rec.page >= 1, "PDF/slide pages must be 1-based"


def test_table_ratings_marked_qualitative_and_cite_s01_p6():
    # Build a tiny in-memory XLSX via openpyxl if available; otherwise skip.
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "method_comparison"
    ws.append(
        [
            "method_no",
            "method",
            "measurement_technique",
            "physical_phenomenon",
            "sample_type",
            "optical_path_or_depth",
            "sensitivity",
            "selectivity",
            "cost",
        ]
    )
    ws.append([1, "NIR", "diffuse reflection", "overtone", "powder", "mm", "average", "low", "low"])
    notes = wb.create_sheet("notes")
    notes.append(["Transcribed from S01 Table 1, p.6."])

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.xlsx")
        wb.save(path)
        recs = ingest.ingest_table_xlsx(path)

    assert recs
    for r in recs:
        # The contract REQUIRES exactly (S01, 6, XLSX) for table_transcription.
        assert r.source_id == "S01"
        assert r.page == 6
        assert r.origin_source_id == "XLSX"
        assert r.kind == "table_transcription"
        assert r.purpose == "technical"
        assert "qualitative" in r.text.lower()
    assert any(r.evidence_id == ingest.table_evidence_id(1) for r in recs)


# ---------------------------------------------------------------------------
# kinds are separated; references never in evidence.jsonl
# ---------------------------------------------------------------------------
def test_references_stay_out_of_evidence_in_build(tmp_path):
    """Run the build script against a stub materials dir and inspect artifacts.

    No optional parser libs are present, so only the lib-free sources (S02
    notes, S06 context) land in evidence.jsonl. The key invariants still hold:
      * evidence.jsonl contains only contract evidence kinds
      * reference_records.jsonl is written separately
      * every evidence line validates against the contract (build self-check)
    """

    import scripts.build_index as build_index

    materials = tmp_path / "materials"
    materials.mkdir()
    # Provide only S06 so a lib-free evidence record is produced.
    (materials / "S06_Laboratory_Link.txt").write_text(
        "https://mirphotonics.com/laboratory/\n", encoding="utf-8"
    )

    out = tmp_path / "index"
    build_index.build(str(materials), str(out))

    evidence_path = out / "evidence.jsonl"
    references_path = out / "reference_records.jsonl"
    catalog_path = out / "catalog.json"
    manifest_path = out / "manifest.json"
    assert evidence_path.is_file()
    assert references_path.is_file()
    assert catalog_path.is_file()
    assert manifest_path.is_file()

    evidence = [json.loads(line) for line in evidence_path.read_text().splitlines() if line.strip()]
    kinds = {rec["kind"] for rec in evidence}
    allowed = {"pdf", "curated_note", "table_transcription", "text"}
    assert kinds.issubset(allowed)
    assert "reference" not in kinds
    # Every evidence row carries evidence_id + source_id and validates.
    for rec in evidence:
        assert rec["source_id"] and rec["evidence_id"]
        Evidence.model_validate(rec)


# ---------------------------------------------------------------------------
# CRITICAL: no H01-H06 scenario text ends up in the evidence index
# ---------------------------------------------------------------------------
def _h_signatures() -> list[str]:
    """Read distinctive H01-H06 phrases from the scenario file at runtime.

    No scenario IDs or wording are hardcoded: we derive signatures from the
    file itself, so the test cannot be fooled by hardcoded logic.
    """

    if not os.path.isfile(H_SCENARIOS_PATH):
        pytest.skip("H scenarios file not available")
    raw = open(H_SCENARIOS_PATH, encoding="utf-8").read()
    signatures: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        # Long narrative sentences are distinctive; skip headers/separators.
        if len(line) >= 40 and not line.startswith(("=", "-", "H0", "AFS Hackathon")):
            signatures.append(line.lower())
    return signatures[:30]


def test_no_h_scenarios_in_index(tmp_path):
    import scripts.build_index as build_index

    signatures = _h_signatures()
    assert signatures, "expected to derive H signatures from the scenario file"

    # Build a full index against the real materials folder if present.
    materials = MATERIALS_DIR if os.path.isdir(MATERIALS_DIR) else str(tmp_path)
    out = tmp_path / "index"
    try:
        build_index.build(materials, str(out))
    except ModuleNotFoundError:
        # Optional parser libs missing: fall back to the lib-free evidence we
        # can produce, writing it ourselves so the assertion still has teeth.
        recs = _build_lib_free_evidence()
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "evidence.jsonl", "w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(to_dict(r), ensure_ascii=False))
                fh.write("\n")

    blob = (out / "evidence.jsonl").read_text(encoding="utf-8").lower()
    for sig in signatures:
        assert sig not in blob, f"H scenario text leaked into evidence index: {sig[:60]!r}"
