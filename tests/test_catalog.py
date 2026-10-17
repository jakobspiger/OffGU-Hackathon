"""Tests for the source catalogue and the indexable allowlist (AP2/AP3)."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("pydantic", reason="pydantic is provided by `uv sync --locked`")

from tests.conftest import MATERIALS_DIR  # noqa: E402

from src.knowledge import catalog, ingest  # noqa: E402


def test_catalog_reports_missing_and_present(tmp_path):
    # An empty directory => every expected input reported missing, none invented.
    entries_empty = catalog.check_materials(tmp_path)
    assert entries_empty, "catalog must list entries even when nothing is present"
    assert all(e.present is False for e in entries_empty)
    # Descriptions are static/verified and present regardless of files on disk.
    assert all(e.description for e in entries_empty)

    # Against the real materials folder, the known inputs are detected as present.
    if os.path.isdir(MATERIALS_DIR):
        entries = catalog.check_materials(MATERIALS_DIR)
        by_id = {e.source_id: e for e in entries}
        assert by_id["S01"].present is True
        assert by_id["XLSX"].present is True
        assert by_id["S06"].present is True


def test_catalog_citation_hints_follow_rules():
    by_id = {e.source_id: e for e in catalog.source_catalog()}
    assert by_id["S01"].citation_hint == "S01 p.10"
    assert by_id["S02"].citation_hint == "S02 p.13"
    assert by_id["XLSX"].citation_hint == "S01 Table 1 (p.6)"


def test_catalog_still_inventories_brief_xlsx_docx():
    by_id = {e.source_id: e for e in catalog.source_catalog()}
    # The catalogue may inventory non-evidence documents (handover table).
    for non_evidence in ("BRIEF", "XLSX", "DOCX"):
        assert non_evidence in by_id, f"catalogue should still list {non_evidence}"


def test_allowlist_excludes_h_scenarios_brief_docx_and_qa_schedule():
    # H scenarios and QA-schedule PDFs are NOT indexable sources.
    assert "H" not in ingest.INDEXABLE_SOURCES
    for name in ingest.EXCLUDED_FROM_INDEX:
        assert name not in ingest.INDEXABLE_SOURCES
    assert "customer_scenarios_for_final_evaluation.txt" in ingest.EXCLUDED_FROM_INDEX
    # BRIEF and the dev-reference DOCX are ReferenceRecords, not evidence.
    assert "BRIEF" not in ingest.INDEXABLE_SOURCES
    assert "DOCX" not in ingest.INDEXABLE_SOURCES
    # The expected indexable set per the migration plan.
    assert ingest.INDEXABLE_SOURCES == frozenset({"S01", "S02", "S03", "S04", "S05", "S06", "XLSX"})


def test_dev_reference_kind_is_separate():
    docx_entry = catalog.get_entry("DOCX")
    assert docx_entry is not None
    # Inventory label is a plain contract Text; DOCX is a reference document.
    assert docx_entry.kind == "reference"
