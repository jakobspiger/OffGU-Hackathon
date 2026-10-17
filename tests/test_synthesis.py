"""T08 B4/B5 synthesis tests. Synthetic inputs only; no AFS scientific claims."""

import json

import pytest

from src.config import Settings
from src.engine.synthesis import synthesize
from src.errors import ProviderError, SynthesisError
from src.models import (
    Evidence,
    ExtractedFact,
    ExtractionResult,
    RuleFinding,
    SourceReference,
)


class FakeProvider:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def complete(self, system, query):
        self.calls.append((system, query))
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setattr("src.engine.synthesis.time.sleep", lambda _: None)
    return Settings(_env_file=None, afs_max_retries=0)


def _extraction(facts=None, unknowns=None):
    return ExtractionResult(
        stated_facts=facts or [],
        assumptions=[],
        unknowns=unknowns or [],
        conflicts=[],
    )


def _evidence(evidence_id="E1", source_id="S01", page=1):
    return Evidence(
        source_id=source_id,
        origin_source_id=source_id,
        page=page,
        evidence_id=evidence_id,
        text="Synthetic evidence passage.",
        kind="pdf",
        purpose="technical",
    )


def _recommendation(method="Synthetic NIR", evidence_ids=("E1",), source=("S01", 1)):
    return {
        "method": method,
        "role": "primary_candidate",
        "why": "Synthetic rationale",
        "conditions": ["Requires confirmation"],
        "measurement_geometry": "Undetermined",
        "spectral_range": None,
        "source_refs": [{"source_id": source[0], "page": source[1]}],
        "evidence_ids": list(evidence_ids),
    }


def _draft(status="provisional", recommendations=None):
    return json.dumps(
        {
            "decision_status": status,
            "recommendations": recommendations or [],
            "measurement_concept": "Synthetic concept.",
            "risks_and_limits": ["Synthetic risk."],
            "go_no_go_criteria": ["Synthetic criterion."],
        }
    )


def test_grounded_recommendation_is_kept(settings):
    extraction = _extraction(
        facts=[ExtractedFact(parameter="matrix", value="Pulver", input_quote="Pulver")]
    )
    provider = FakeProvider(_draft(recommendations=[_recommendation()]))
    result = synthesize(extraction, [], [], [_evidence("E1")], provider=provider, settings=settings)
    assert result.decision_status == "provisional"
    assert len(result.recommendations) == 1
    # overall_sources must cover the recommendation source (contract validator).
    assert any(s.source_id == "S01" for s in result.overall_sources)


def test_no_evidence_forces_abstention(settings):
    provider = FakeProvider(_draft(recommendations=[_recommendation()]))
    result = synthesize(_extraction(), [], [], [], provider=provider, settings=settings)
    assert result.decision_status == "insufficient_information"
    assert result.recommendations == []


def test_recommendation_citing_unknown_evidence_is_dropped(settings):
    # Model cites E9 but only E1 was retrieved -> dropped -> abstain.
    provider = FakeProvider(_draft(recommendations=[_recommendation(evidence_ids=("E9",))]))
    result = synthesize(
        _extraction(), [], [], [_evidence("E1")], provider=provider, settings=settings
    )
    assert result.recommendations == []
    assert result.decision_status == "insufficient_information"


def test_rule_excluded_method_is_removed(settings):
    rules = [
        RuleFinding(
            rule_id="Synthetic NIR",
            outcome="excluded",
            reason="synthetic exclusion",
            source_refs=[SourceReference(source_id="S01", page=1)],
        )
    ]
    provider = FakeProvider(_draft(recommendations=[_recommendation(method="Synthetic NIR")]))
    result = synthesize(
        _extraction(), rules, [], [_evidence("E1")], provider=provider, settings=settings
    )
    assert result.recommendations == []


def test_blocking_question_forces_abstention(settings):
    from src.models import ClarificationQuestion

    q = ClarificationQuestion(
        question="Which value applies?", why_it_matters="synthetic", priority=1, blocking=True
    )
    provider = FakeProvider(_draft(recommendations=[_recommendation()]))
    result = synthesize(
        _extraction(), [], [q], [_evidence("E1")], provider=provider, settings=settings
    )
    assert result.decision_status == "insufficient_information"
    assert result.recommendations == []
    assert result.clarification_questions == [q]


def test_facts_and_unknowns_come_from_extraction_not_model(settings):
    extraction = _extraction(
        facts=[ExtractedFact(parameter="temperature", value="80 °C", input_quote="80 °C")],
        unknowns=["required_accuracy"],
    )
    provider = FakeProvider(_draft(status="insufficient_information"))
    result = synthesize(extraction, [], [], [], provider=provider, settings=settings)
    assert result.stated_facts == ["temperature: 80 °C"]
    assert result.unknowns == ["required_accuracy"]


def test_invalid_json_is_retried_then_fails(settings):
    settings.afs_max_retries = 1
    provider = FakeProvider("not json", "still not json")
    with pytest.raises(SynthesisError):
        synthesize(_extraction(), [], [], [], provider=provider, settings=settings)
    assert len(provider.calls) == 2


def test_auth_error_not_retried(settings):
    settings.afs_max_retries = 2
    provider = FakeProvider(ProviderError("HTTP 401"))
    with pytest.raises(ProviderError):
        synthesize(_extraction(), [], [], [], provider=provider, settings=settings)
    assert len(provider.calls) == 1
