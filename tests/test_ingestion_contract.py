"""T02 handover contracts: synthetic records, no changes to Kevin's branch."""

import pytest
from pydantic import ValidationError

from src.models import Evidence, ReferenceRecord, SourceCatalogEntry


def test_spreadsheet_preserves_origin_and_cites_primary_pdf():
    record = Evidence(
        evidence_id="XLSX-row03",
        source_id="S01",
        page=6,
        origin_source_id="XLSX",
        text="Synthetic table row",
        kind="table_transcription",
        purpose="technical",
    )
    assert Evidence.model_validate_json(record.model_dump_json()) == record
    assert record.origin_source_id != record.source_id


def test_table_cannot_claim_another_page():
    with pytest.raises(ValidationError, match="S01 page 6"):
        Evidence(
            evidence_id="XLSX-row03",
            source_id="S01",
            page=7,
            origin_source_id="XLSX",
            text="Synthetic table row",
            kind="table_transcription",
            purpose="technical",
        )


def test_pending_visual_review_survives_json_roundtrip():
    record = Evidence(
        evidence_id="S02-note-p13",
        source_id="S02",
        page=13,
        origin_source_id="S02",
        text="Synthetic unverified note",
        kind="curated_note",
        purpose="technical",
        review_status="pending_visual_check",
        review_note="Awaiting visual review.",
    )
    assert Evidence.model_validate_json(record.model_dump_json()).review_status == (
        "pending_visual_check"
    )


def test_reviewed_requires_review_note():
    with pytest.raises(ValidationError, match="review note"):
        Evidence(
            evidence_id="S02-note-p13",
            source_id="S02",
            page=13,
            origin_source_id="S02",
            text="Synthetic note",
            kind="curated_note",
            purpose="technical",
            review_status="reviewed",
        )


@pytest.mark.parametrize("source_id", ["BRIEF", "DOCX"])
def test_non_evidence_documents_have_separate_records(source_id):
    catalog = SourceCatalogEntry(
        source_id=source_id,
        filename="synthetic.txt",
        present=True,
        kind="reference",
        rank="reference",
    )
    raw = ReferenceRecord(record_id="synthetic", source_id=source_id, text="Synthetic reference")
    assert raw.source_id == catalog.source_id
    with pytest.raises(ValidationError):
        Evidence.model_validate(raw.model_dump())


def test_pdf_mapping_uses_single_evidence_id():
    record = Evidence(
        evidence_id="S01-p001",
        source_id="S01",
        page=1,
        origin_source_id="S01",
        text="Synthetic passage",
        kind="pdf",
        purpose="technical",
    )
    assert record.review_status == "unreviewed"
    assert "chunk_id" not in record.model_dump()
