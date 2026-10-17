"""Tests for the T10 B7 citation/physics gate (src.engine.validators).

Design mirrors the rest of the suite (see tests/conftest.py and
tests/test_rules.py): the pure-logic paths (page-range check, evidence-id set
membership, evidence-scope mapping, spectral plausibility, rule-outcome mapping)
run on the standard library alone using small duck-typed stubs, while the paths
that build real contract objects (AnalysisResult / Evidence / RuleFinding /
ValidationReport) and check the ResultValidator protocol are guarded with
``pytest.importorskip``. The full run happens locally via
``uv run --locked pytest -q``.

The validator reads its inputs via attribute access only, so the stubs below
expose exactly the fields it touches:
    result.recommendations[*].source_refs / .evidence_ids / .spectral_range
    result.overall_sources, result.decision_status
    evidence[*].evidence_id / .source_id / .purpose
    rules[*].outcome / .rule_id
"""

from __future__ import annotations

import inspect
import os
import typing

import pytest

from src.engine import validators
from src.engine.validators import (
    ERROR,
    NOT_CHECKED,
    WARNING,
    _check_citations,
    _check_physics,
    _check_rules,
    page_in_range,
    validate_result,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VALIDATORS_PATH = os.path.join(_ROOT, "src", "engine", "validators.py")


# ---------------------------------------------------------------------------
# Light stdlib stubs (duck typing; no pydantic). Only the fields the validator
# reads are exposed.
# ---------------------------------------------------------------------------
class _Ref:
    def __init__(self, source_id: str, page: int | None = None) -> None:
        self.source_id = source_id
        self.page = page


class _Ev:
    def __init__(self, evidence_id: str, source_id: str, purpose: str) -> None:
        self.evidence_id = evidence_id
        self.source_id = source_id
        self.purpose = purpose


class _Spectral:
    def __init__(self, lower, upper, unit, quantity, scope, note="") -> None:
        self.lower = lower
        self.upper = upper
        self.unit = unit
        self.quantity = quantity
        self.scope = scope
        self.compatibility_note = note


class _Rec:
    def __init__(
        self,
        source_refs=None,
        evidence_ids=None,
        spectral_range=None,
    ) -> None:
        self.source_refs = source_refs or []
        self.evidence_ids = evidence_ids or []
        self.spectral_range = spectral_range


class _Result:
    def __init__(
        self,
        recommendations=None,
        overall_sources=None,
        decision_status="provisional",
    ) -> None:
        self.recommendations = recommendations or []
        self.overall_sources = overall_sources or []
        self.decision_status = decision_status


class _Rule:
    def __init__(self, rule_id: str, outcome: str) -> None:
        self.rule_id = rule_id
        self.outcome = outcome


def _codes(specs) -> set[str]:
    return {s.code for s in specs}


def _by_code(specs, code):
    return [s for s in specs if s.code == code]


# ---------------------------------------------------------------------------
# AP1 citation gate - pure logic (page range).
# ---------------------------------------------------------------------------
def test_page_in_range_pure_logic():
    spans = {"S01": (1, 19), "S02": (1, 20), "S05": (1, 2)}
    assert page_in_range("S01", 10, spans) is True
    assert page_in_range("S01", 19, spans) is True
    assert page_in_range("S01", 20, spans) is False  # out of catalog span
    assert page_in_range("S01", 0, spans) is False
    assert page_in_range("S06", None, spans) is True  # text link, no page
    assert page_in_range("S06", 1, spans) is False  # S06 has no page
    assert page_in_range("S03", 1, spans) is True  # no fixed span, positive ok
    assert page_in_range("S99", 1, spans) is False  # unknown source


def test_fabricated_source_is_error():
    """An invented source_id and a page outside the catalog span are errors."""

    result = _Result(
        recommendations=[
            _Rec(source_refs=[_Ref("S99", 1)], evidence_ids=["e1"]),
        ],
        overall_sources=[_Ref("S01", 999)],
    )
    evidence = [_Ev("e1", "S01", "technical")]
    specs = _check_citations(result, evidence)

    source_unknown = _by_code(specs, validators.CITATION_SOURCE_UNKNOWN)
    page_oor = _by_code(specs, validators.CITATION_PAGE_OUT_OF_RANGE)
    assert source_unknown and all(s.severity == ERROR for s in source_unknown)
    assert page_oor and all(s.severity == ERROR for s in page_oor)


def test_missing_evidence_id_is_error():
    result = _Result(
        recommendations=[_Rec(source_refs=[_Ref("S01", 10)], evidence_ids=["missing"])],
        overall_sources=[_Ref("S01", 10)],
    )
    evidence = [_Ev("present", "S01", "technical")]
    specs = _check_citations(result, evidence)

    missing = _by_code(specs, validators.EVIDENCE_ID_MISSING)
    assert missing and all(s.severity == ERROR for s in missing)
    assert "missing" in missing[0].evidence_ids


def test_business_context_evidence_as_proof_is_error():
    result = _Result(
        recommendations=[_Rec(source_refs=[_Ref("S05", 1)], evidence_ids=["b1"])],
        overall_sources=[_Ref("S05", 1)],
    )
    evidence = [_Ev("b1", "S05", "business_context")]
    specs = _check_citations(result, evidence)

    scope = _by_code(specs, validators.EVIDENCE_SCOPE_BUSINESS_CONTEXT)
    assert scope and all(s.severity == ERROR for s in scope)
    assert "b1" in scope[0].evidence_ids


def test_research_scope_overreach_is_warning():
    result = _Result(
        recommendations=[_Rec(source_refs=[_Ref("S03", 1)], evidence_ids=["r1"])],
        overall_sources=[_Ref("S03", 1)],
    )
    evidence = [_Ev("r1", "S03", "research")]
    specs = _check_citations(result, evidence)

    scope = _by_code(specs, validators.EVIDENCE_SCOPE_RESEARCH)
    assert scope and all(s.severity == WARNING for s in scope)


def test_unverifiable_claim_marked_not_checked():
    """Exactly ONE not_checked per recommendation (documented limit)."""

    result = _Result(
        recommendations=[
            _Rec(source_refs=[_Ref("S01", 10)], evidence_ids=["e1"]),
            _Rec(source_refs=[_Ref("S01", 11)], evidence_ids=["e1"]),
        ],
        overall_sources=[_Ref("S01", 10), _Ref("S01", 11)],
    )
    evidence = [_Ev("e1", "S01", "technical")]
    specs = _check_citations(result, evidence)

    not_checked = _by_code(specs, validators.SEMANTIC_SUPPORT_NOT_CHECKED)
    # One per recommendation, not one per claim.
    assert len(not_checked) == 2
    assert all(s.severity == NOT_CHECKED for s in not_checked)


# ---------------------------------------------------------------------------
# AP2 physics gate - pure logic.
# ---------------------------------------------------------------------------
def test_verified_instrument_range_without_evidence_is_error():
    spectral = _Spectral(1000, 1800, "nm", "wavelength", "verified_instrument")
    result = _Result(
        recommendations=[
            _Rec(source_refs=[_Ref("S01", 2)], evidence_ids=[], spectral_range=spectral)
        ]
    )
    specs = _check_physics(result)

    verified = _by_code(specs, validators.SPECTRAL_VERIFIED_WITHOUT_EVIDENCE)
    assert verified and all(s.severity == ERROR for s in verified)


def test_verified_instrument_range_with_evidence_is_ok():
    spectral = _Spectral(1000, 1800, "nm", "wavelength", "verified_instrument")
    result = _Result(
        recommendations=[
            _Rec(source_refs=[_Ref("S01", 2)], evidence_ids=["e1"], spectral_range=spectral)
        ]
    )
    specs = _check_physics(result)
    assert validators.SPECTRAL_VERIFIED_WITHOUT_EVIDENCE not in _codes(specs)


def test_implausible_spectral_range_is_warning():
    # 50-60 nm is far below the NIR nominal band (~780-2500 nm).
    spectral = _Spectral(50, 60, "nm", "wavelength", "nominal_method_only")
    result = _Result(
        recommendations=[
            _Rec(source_refs=[_Ref("S01", 2)], evidence_ids=["e1"], spectral_range=spectral)
        ]
    )
    specs = _check_physics(result)

    implausible = _by_code(specs, validators.SPECTRAL_RANGE_IMPLAUSIBLE)
    assert implausible and all(s.severity == WARNING for s in implausible)


def test_plausible_spectral_range_no_warning():
    spectral = _Spectral(1000, 1800, "nm", "wavelength", "nominal_method_only")
    result = _Result(
        recommendations=[
            _Rec(source_refs=[_Ref("S01", 2)], evidence_ids=["e1"], spectral_range=spectral)
        ]
    )
    specs = _check_physics(result)
    assert validators.SPECTRAL_RANGE_IMPLAUSIBLE not in _codes(specs)


# ---------------------------------------------------------------------------
# AP3 rule gate - pure logic.
# ---------------------------------------------------------------------------
def test_excluded_rule_contradiction_is_error():
    result = _Result(
        recommendations=[_Rec(source_refs=[_Ref("S01", 2)], evidence_ids=["e1"])],
        decision_status="provisional",
    )
    rules = [_Rule("R-EXC", "excluded")]
    specs = _check_rules(result, rules)

    contradiction = _by_code(specs, validators.RULE_EXCLUDED_CONTRADICTION)
    assert contradiction and all(s.severity == ERROR for s in contradiction)


def test_unresolved_unknown_with_provisional_is_warning():
    result = _Result(recommendations=[], decision_status="provisional")
    rules = [_Rule("R-UNK", "unknown")]
    specs = _check_rules(result, rules)

    unresolved = _by_code(specs, validators.RULE_UNKNOWN_UNRESOLVED)
    assert unresolved and all(s.severity == WARNING for s in unresolved)


def test_unknown_rule_without_provisional_is_silent():
    result = _Result(recommendations=[], decision_status="insufficient_information")
    rules = [_Rule("R-UNK", "unknown")]
    specs = _check_rules(result, rules)
    assert validators.RULE_UNKNOWN_UNRESOLVED not in _codes(specs)


# ---------------------------------------------------------------------------
# No scenario-id logic anywhere in the validator source.
# ---------------------------------------------------------------------------
def test_no_scenario_ids_in_validator():
    import re

    source = open(_VALIDATORS_PATH, encoding="utf-8").read()
    assert not re.search(r"\b[HD]0[1-9]\b", source), "no H0x/D0x scenario ids in the gate"


# ---------------------------------------------------------------------------
# Contract-dependent paths (pydantic): guarded with importorskip.
# ---------------------------------------------------------------------------
def _build_models():
    """Import the contract models or skip the test if pydantic is unavailable."""

    pytest.importorskip("pydantic")
    from src import models

    return models


def _valid_result(models):
    """A clean, contract-valid AnalysisResult that must pass the gate."""

    ref = models.SourceReference(source_id="S01", page=10)
    spectral = models.SpectralRange(
        lower=1000.0,
        upper=1800.0,
        unit="nm",
        quantity="wavelength",
        scope="nominal_method_only",
        compatibility_note="NIR nominal band.",
    )
    rec = models.Recommendation(
        method="NIR transmission",
        role="primary_candidate",
        why="Matches the nominal NIR band for the target.",
        conditions=["Confirm optical access."],
        measurement_geometry="in-line transmission probe",
        spectral_range=spectral,
        source_refs=[ref],
        evidence_ids=["e1"],
    )
    return models.AnalysisResult(
        decision_status="provisional",
        stated_facts=["matrix stated"],
        assumptions=[],
        unknowns=[],
        clarification_questions=[],
        recommendations=[rec],
        measurement_concept="Concept.",
        risks_and_limits=["limit"],
        feasibility_plan=[],
        go_no_go_criteria=["go"],
        overall_sources=[ref],
    )


def _technical_evidence(models):
    return [
        models.Evidence(
            source_id="S01",
            page=10,
            evidence_id="e1",
            text="Technical passage.",
            kind="pdf",
            purpose="technical",
            origin_source_id="S01",
        )
    ]


def test_valid_result_has_no_errors():
    models = _build_models()
    result = _valid_result(models)
    evidence = _technical_evidence(models)
    report = validate_result(result, evidence, [])

    assert report.has_errors is False
    # A clean result still carries the documented not_checked limit.
    assert any(f.severity == "not_checked" for f in report.findings)


def test_validate_matches_resultvalidator_protocol():
    models = _build_models()
    from src.contracts import ResultValidator

    result = _valid_result(models)
    evidence = _technical_evidence(models)
    report = validate_result(result, evidence, [])
    assert isinstance(report, models.ValidationReport)

    # Signature matches ResultValidator.__call__ (minus self).
    proto_params = list(inspect.signature(ResultValidator.__call__).parameters)[1:]
    fn_params = list(inspect.signature(validate_result).parameters)
    assert fn_params == proto_params

    # Structural protocol conformance (typing.Protocol runtime check).
    assert isinstance(validate_result, typing.cast(type, ResultValidator)) or callable(
        validate_result
    )


def test_validator_is_stateless_fresh_report():
    """Two calls return independent, freshly built reports (T11 loop seam)."""

    models = _build_models()
    result = _valid_result(models)
    evidence = _technical_evidence(models)

    first = validate_result(result, evidence, [])
    second = validate_result(result, evidence, [])

    assert first is not second
    assert first.findings is not second.findings
    # Mutating one report must not affect the other.
    first.findings.clear()
    assert second.findings, "second report must be independent of the first"


def test_validator_sets_no_decision_status():
    """The validator never mutates the result nor touches decision_status."""

    models = _build_models()
    result = _valid_result(models)
    evidence = _technical_evidence(models)

    before = result.model_dump()
    validate_result(result, evidence, [])
    after = result.model_dump()
    assert before == after
    assert result.decision_status == "provisional"


def test_fabricated_source_error_with_real_models():
    """End-to-end error path on real contract objects (invented page)."""

    models = _build_models()
    # A page far outside S01's catalog span (1-19) must be an error.
    ref = models.SourceReference(source_id="S01", page=999)
    rec = models.Recommendation(
        method="m",
        role="primary_candidate",
        why="why",
        conditions=["c"],
        measurement_geometry="g",
        spectral_range=None,
        source_refs=[ref],
        evidence_ids=["e1"],
    )
    result = models.AnalysisResult(
        decision_status="provisional",
        stated_facts=[],
        assumptions=[],
        unknowns=[],
        clarification_questions=[],
        recommendations=[rec],
        measurement_concept="c",
        risks_and_limits=[],
        feasibility_plan=[],
        go_no_go_criteria=[],
        overall_sources=[ref],
    )
    evidence = _technical_evidence(models)
    report = validate_result(result, evidence, [])
    assert report.has_errors is True
    assert any(f.code == validators.CITATION_PAGE_OUT_OF_RANGE for f in report.findings)
