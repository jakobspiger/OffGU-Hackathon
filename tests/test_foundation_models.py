"""Synthetic contract tests: no AFS scientific claims or final scenarios."""

import pytest
from pydantic import ValidationError

from src.models import (
    AnalysisResult,
    Evidence,
    ExtractedFact,
    ExtractionResult,
    FewShotExample,
    SourceReference,
    SpectralRange,
    ValidationFinding,
    ValidationReport,
)


def result_payload():
    return dict(
        decision_status="insufficient_information",
        stated_facts=[],
        assumptions=[],
        unknowns=["Target substance is unknown."],
        clarification_questions=[],
        recommendations=[],
        measurement_concept="Pending clarification.",
        risks_and_limits=["No method selected."],
        feasibility_plan=[],
        go_no_go_criteria=[],
        overall_sources=[],
    )


def test_incomplete_request_can_abstain_and_roundtrip():
    result = AnalysisResult(**result_payload())
    assert AnalysisResult.model_validate_json(result.model_dump_json()) == result
    assert result.recommendations == []


@pytest.mark.parametrize(
    "change",
    [
        {"decision_status": "approved"},
        {"accuracy": 99.9},
        {"unknowns": "unknown"},
    ],
)
def test_invalid_provider_payload_is_rejected(change):
    with pytest.raises(ValidationError):
        AnalysisResult(**(result_payload() | change))


@pytest.mark.parametrize("page", [None, 0, -1, True, "6"])
def test_pdf_requires_positive_integer_page(page):
    with pytest.raises(ValidationError):
        SourceReference(source_id="S01", page=page)


def test_text_source_does_not_invent_page():
    assert SourceReference(source_id="S06").page is None
    with pytest.raises(ValidationError):
        SourceReference(source_id="S06", page=1)


@pytest.mark.parametrize("source", ["D01", "H01", "external", "S99"])
def test_only_catalog_sources_are_citable(source):
    with pytest.raises(ValidationError):
        SourceReference(source_id=source, page=1)


def test_business_context_cannot_claim_technical_evidence():
    with pytest.raises(ValidationError):
        Evidence(
            source_id="S05",
            origin_source_id="S05",
            page=1,
            evidence_id="synthetic",
            text="Synthetic test passage",
            kind="pdf",
            purpose="technical",
        )


def test_research_retains_scope():
    with pytest.raises(ValidationError):
        Evidence(
            source_id="S03",
            origin_source_id="S03",
            page=1,
            evidence_id="synthetic",
            text="Synthetic test passage",
            kind="pdf",
            purpose="technical",
        )


def test_quotes_must_exist_in_original_input():
    extraction = ExtractionResult(
        stated_facts=[ExtractedFact(parameter="matrix", value="powder", input_quote="powder")],
        assumptions=[],
        unknowns=["target"],
    )
    extraction.verify_quotes("Measure this powder.")
    with pytest.raises(ValueError):
        extraction.verify_quotes("Measure this liquid.")


@pytest.mark.parametrize(
    "overrides",
    [
        {"lower": 2000.0, "upper": 1000.0},
        {"unit": "cm^-1"},
        {"lower": float("nan")},
    ],
)
def test_ranges_reject_confused_units_and_invalid_values(overrides):
    fields = dict(
        lower=1000.0,
        upper=2000.0,
        unit="nm",
        quantity="wavelength",
        scope="nominal_method_only",
        compatibility_note="Synthetic test, not a specification.",
    )
    with pytest.raises(ValidationError):
        SpectralRange(**(fields | overrides))


def test_recommendation_must_be_listed_in_overall_sources():
    payload = result_payload()
    payload["recommendations"] = [
        dict(
            method="Synthetic method",
            role="alternative",
            why="Synthetic contract test",
            conditions=["Requires evidence"],
            measurement_geometry="Undetermined",
            spectral_range=None,
            source_refs=[dict(source_id="S01", page=1)],
            evidence_ids=["synthetic"],
        )
    ]
    with pytest.raises(ValidationError):
        AnalysisResult(**payload)
    payload["overall_sources"] = [dict(source_id="S01", page=1)]
    assert len(AnalysisResult(**payload).recommendations) == 1


def test_gate_report_preserves_unchecked_and_error():
    report = ValidationReport(
        findings=[
            ValidationFinding(
                code="not_reviewed",
                severity="not_checked",
                message="Needs expert review",
                field_path="recommendations",
            ),
        ]
    )
    assert not report.has_errors
    report.findings.append(
        ValidationFinding(
            code="citation_missing",
            severity="error",
            message="Missing evidence",
            field_path="recommendations.0",
        )
    )
    assert report.has_errors


def test_examples_cannot_admit_final_scenario_ids():
    with pytest.raises(ValidationError):
        FewShotExample(
            example_id="H01",
            query="Synthetic input",
            reference_answer=None,
            provenance="Synthetic fixture",
        )


def test_json_schema_is_exportable():
    schema = AnalysisResult.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "decision_status" in schema["required"]
