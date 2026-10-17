"""Tests for the ingestion logic (AP3/AP4/AP5).

These run without PyMuPDF / python-docx / openpyxl / pydantic / PyYAML. The
library-dependent code paths are guarded with ``pytest.importorskip``; the pure
logic (chunk ids, YAML note parsing, business context, allowlist, schema shape)
is tested directly on fixtures.
"""

from __future__ import annotations

import json
import os

import pytest

from tests.conftest import H_SCENARIOS_PATH, MATERIALS_DIR, S02_NOTES_PATH

from src.knowledge import ingest
from src.knowledge.types import Evidence, SourceKind, to_dict


# ---------------------------------------------------------------------------
# chunk-id determinism
# ---------------------------------------------------------------------------
def test_chunk_ids_are_deterministic_and_formatted():
    assert ingest.pdf_chunk_id("S01", 10) == "S01-p010"
    assert ingest.pdf_chunk_id("S01", 1) == "S01-p001"
    assert ingest.table_chunk_id(3) == "XLSX-row03"
    assert ingest.s02_note_chunk_id(13) == "S02-note-p13"
    assert ingest.business_chunk_id("S06") == "S06-context"


# ---------------------------------------------------------------------------
# verified S02 notes (YAML, no PyYAML needed via fallback parser)
# ---------------------------------------------------------------------------
def test_s02_notes_load_and_are_marked_verified():
    assert os.path.isfile(S02_NOTES_PATH), "s02_notes.yaml fixture must exist"
    recs = ingest.ingest_verified_s02_notes(S02_NOTES_PATH)
    assert recs, "expected verified S02 notes"
    pages = {r.page for r in recs}
    # Key image-heavy slides from the ticket: 6 and 13-16.
    for required in (6, 13, 14, 15, 16):
        assert required in pages, f"missing S02 note for p.{required}"
    for r in recs:
        assert r.source_id == "S02"
        assert r.kind == SourceKind.verified_note
        assert r.chunk_id == ingest.s02_note_chunk_id(r.page)
        assert "provenance" in r.text  # marked as a reviewed transcription


def test_s02_notes_graceful_on_missing_file(tmp_path):
    missing = tmp_path / "nope.yaml"
    assert ingest.ingest_verified_s02_notes(missing) == []


# ---------------------------------------------------------------------------
# business context: S05 + S06 (no libs needed)
# ---------------------------------------------------------------------------
def test_s06_has_no_page_and_is_business_context():
    recs = ingest.ingest_business_context(MATERIALS_DIR)
    s06 = [r for r in recs if r.source_id == "S06"]
    assert len(s06) == 1
    assert s06[0].page is None
    assert s06[0].kind == SourceKind.business_context
    assert "mirphotonics.com/laboratory" in s06[0].text


def test_s05_is_business_context_when_present():
    recs = ingest.ingest_business_context(MATERIALS_DIR)
    s05 = [r for r in recs if r.source_id == "S05"]
    if s05:  # only when the flyer file is present
        assert s05[0].kind == SourceKind.business_context
        assert s05[0].page == 1


# ---------------------------------------------------------------------------
# schema shape: every evidence record has source_id + stable id; pages 1-based
# ---------------------------------------------------------------------------
def _build_lib_free_evidence() -> list[Evidence]:
    """Collect the evidence we can build WITHOUT the optional libraries."""

    records: list[Evidence] = []
    records.extend(ingest.ingest_verified_s02_notes(S02_NOTES_PATH))
    records.extend(ingest.ingest_business_context(MATERIALS_DIR))
    return records


def test_pages_are_1_based_and_have_source_id():
    for rec in _build_lib_free_evidence():
        assert rec.source_id, "every evidence record needs a source_id"
        assert rec.chunk_id, "every evidence record needs a stable chunk_id"
        if rec.page is not None:
            assert rec.page >= 1, "PDF/slide pages must be 1-based"


def test_table_ratings_marked_qualitative():
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
        assert r.source_id == "XLSX"
        assert r.page == 6
        assert r.kind == SourceKind.table_transcription
        assert "qualitative" in r.text.lower()
    assert any(r.chunk_id == ingest.table_chunk_id(1) for r in recs)


# ---------------------------------------------------------------------------
# kinds are separated; dev_reference never in evidence.jsonl
# ---------------------------------------------------------------------------
def test_kinds_are_separated_in_build(tmp_path):
    """Run the build script against a stub materials dir and inspect artifacts.

    No optional libs are present, so only the lib-free sources (S02 notes,
    S06 context) land in evidence.jsonl. The key invariants still hold:
      * evidence.jsonl contains no dev_reference records
      * dev_reference is written to a separate file
      * kinds within evidence.jsonl are a subset of the technical kinds
    """

    import scripts.build_index as build_index

    materials = tmp_path / "materials"
    materials.mkdir()
    # Provide only S06 so a lib-free evidence record is produced.
    (materials / "S06_Laboratory_Link.txt").write_text(
        "https://mirphotonics.com/laboratory/\n", encoding="utf-8"
    )

    out = tmp_path / "index"
    # Point the S02 notes loader at the real fixture via monkeypatch-free default.
    cwd = os.getcwd()
    try:
        os.chdir(build_index._ROOT)  # so default data/source_notes path resolves
        build_index.build(str(materials), str(out))
    finally:
        os.chdir(cwd)

    evidence_path = out / "evidence.jsonl"
    dev_path = out / "dev_reference.jsonl"
    catalog_path = out / "catalog.json"
    manifest_path = out / "manifest.json"
    assert evidence_path.is_file()
    assert dev_path.is_file()
    assert catalog_path.is_file()
    assert manifest_path.is_file()

    evidence = [json.loads(line) for line in evidence_path.read_text().splitlines() if line.strip()]
    kinds = {rec["kind"] for rec in evidence}
    assert SourceKind.dev_reference.value not in kinds, "dev_reference must stay out of evidence.jsonl"
    allowed = {
        SourceKind.pdf_text.value,
        SourceKind.verified_note.value,
        SourceKind.table_transcription.value,
        SourceKind.business_context.value,
    }
    assert kinds.issubset(allowed)
    # Every evidence row carries source_id + chunk_id.
    for rec in evidence:
        assert rec["source_id"] and rec["chunk_id"]


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
    cwd = os.getcwd()
    try:
        os.chdir(build_index._ROOT)
        try:
            build_index.build(materials, str(out))
        except ModuleNotFoundError:
            # Optional libs missing: fall back to the lib-free evidence we can
            # produce, writing it ourselves so the assertion still has teeth.
            recs = _build_lib_free_evidence()
            out.mkdir(parents=True, exist_ok=True)
            with open(out / "evidence.jsonl", "w", encoding="utf-8") as fh:
                for r in recs:
                    fh.write(json.dumps(to_dict(r), ensure_ascii=False))
                    fh.write("\n")
    finally:
        os.chdir(cwd)

    blob = (out / "evidence.jsonl").read_text(encoding="utf-8").lower()
    for sig in signatures:
        assert sig not in blob, f"H scenario text leaked into evidence index: {sig[:60]!r}"
