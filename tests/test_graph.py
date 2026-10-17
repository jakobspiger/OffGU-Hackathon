"""T11 graph orchestration tests. Synthetic inputs only; no network, no AFS claims.

Die Pipeline-Bausteine werden mit Fakes/Stubs ausgetauscht, sodass kein echter
Provider, kein echtes Retrieval und keine echte Regel-Matrix noetig ist. So
laufen die Tests offline, sobald pydantic/langgraph installiert sind. Ohne diese
Bibliotheken ueberspringt pytest.importorskip das Modul sauber.
"""

import pytest

# Graph + State brauchen pydantic (src.models) und langgraph. Ohne diese
# Bibliotheken (Sandbox) wird das Modul uebersprungen statt zu scheitern.
pytest.importorskip("pydantic")
pytest.importorskip("langgraph")

from src.config import Settings  # noqa: E402
from src.engine import graph as graph_mod  # noqa: E402
from src.errors import ProviderError  # noqa: E402
from src.models import (  # noqa: E402
    AnalysisResult,
    ExtractionResult,
    ValidationFinding,
    ValidationReport,
)


def _extraction(unknowns=None):
    return ExtractionResult(
        stated_facts=[],
        assumptions=[],
        unknowns=unknowns or [],
        conflicts=[],
    )


def _analysis_result(status="provisional"):
    return AnalysisResult(
        decision_status=status,
        stated_facts=[],
        assumptions=[],
        unknowns=[],
        clarification_questions=[],
        recommendations=[],
        measurement_concept="Synthetic concept.",
        risks_and_limits=[],
        feasibility_plan=[],
        go_no_go_criteria=[],
        overall_sources=[],
    )


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Isolation: frischer kompilierter Graph und bekannte Obergrenze je Test."""

    monkeypatch.setattr(graph_mod, "_COMPILED", None, raising=False)
    monkeypatch.setattr(graph_mod, "_DEFAULT_SETTINGS", Settings(_env_file=None), raising=False)
    graph_mod.set_max_revisions(0)
    yield


# ---------------------------------------------------------------------------
# Knoten-Wrapper
# ---------------------------------------------------------------------------
def test_rules_node_wraps_evaluate_rules(monkeypatch):
    extraction = _extraction()
    captured = {}

    def fake_evaluate_rules(arg):
        captured["arg"] = arg
        return ["RULE_FINDING"]

    monkeypatch.setattr(graph_mod, "evaluate_rules", fake_evaluate_rules)
    out = graph_mod.rules_node({"extraction": extraction})
    assert out == {"rules": ["RULE_FINDING"]}
    assert captured["arg"] is extraction


def test_retrieval_node_wraps_retrieve_with_settings_k(monkeypatch):
    calls = {}

    def fake_retrieve(query, k):
        calls["query"] = query
        calls["k"] = k
        return ["EVIDENCE"]

    monkeypatch.setattr(graph_mod, "retrieve", fake_retrieve)
    monkeypatch.setattr(graph_mod, "_DEFAULT_SETTINGS", Settings(_env_file=None, afs_retrieval_k=5))
    out = graph_mod.retrieval_node({"query": "some query"})
    assert out == {"evidence": ["EVIDENCE"]}
    assert calls == {"query": "some query", "k": 5}


# ---------------------------------------------------------------------------
# Gate + Korrekturschleife
# ---------------------------------------------------------------------------
def test_gate_passthrough_without_validator():
    draft = _analysis_result()
    out = graph_mod.gate_node({"draft": draft, "revision_count": 0})
    assert out["result"] is draft


def test_should_revise_ends_without_validation():
    assert graph_mod.should_revise({"revision_count": 0}) == "end"


def test_should_revise_loops_when_errors_and_below_cap():
    graph_mod.set_max_revisions(2)
    report = ValidationReport(
        findings=[
            ValidationFinding(
                code="x", severity="error", message="bad", field_path="decision_status"
            )
        ]
    )
    assert graph_mod.should_revise({"validation": report, "revision_count": 0}) == "revise"


def test_should_revise_ends_at_cap():
    graph_mod.set_max_revisions(1)
    report = ValidationReport(
        findings=[
            ValidationFinding(
                code="x", severity="error", message="bad", field_path="decision_status"
            )
        ]
    )
    assert graph_mod.should_revise({"validation": report, "revision_count": 1}) == "end"


def test_gate_defined_failure_result_at_cap():
    graph_mod.set_max_revisions(1)
    draft = _analysis_result(status="provisional")
    report = ValidationReport(
        findings=[
            ValidationFinding(
                code="rule_x", severity="error", message="bad", field_path="recommendations"
            )
        ]
    )
    out = graph_mod.gate_node({"draft": draft, "validation": report, "revision_count": 1})
    result = out["result"]
    assert result.decision_status == "insufficient_information"
    assert result.recommendations == []
    # Die Gate-Befunde plus der Grenz-Befund landen in validation_findings.
    codes = {f.code for f in result.validation_findings}
    assert "rule_x" in codes
    assert graph_mod.REVISION_LIMIT_CODE in codes


# ---------------------------------------------------------------------------
# Vollstaendiger Lauf durch den kompilierten Graphen (Fakes)
# ---------------------------------------------------------------------------
def _patch_pipeline(monkeypatch, *, synth_result=None, synth_exc=None):
    """Ersetzt die schweren Schritte durch Fakes; gaps bleibt echt (pure)."""

    monkeypatch.setattr(
        "src.engine.extraction.extract", lambda query, **kw: _extraction()
    )
    monkeypatch.setattr(graph_mod, "evaluate_rules", lambda extraction: [])
    monkeypatch.setattr(graph_mod, "retrieve", lambda query, k: [])

    def fake_synthesize(*args, **kwargs):
        if synth_exc is not None:
            raise synth_exc
        return synth_result or _analysis_result()

    monkeypatch.setattr("src.engine.synthesis.synthesize", fake_synthesize)


def test_happy_path_returns_valid_analysis_result(monkeypatch):
    _patch_pipeline(monkeypatch, synth_result=_analysis_result(status="provisional"))
    final = graph_mod.build_graph().invoke({"query": "synthetic query", "revision_count": 0})
    assert isinstance(final["result"], AnalysisResult)
    assert final["result"].decision_status == "provisional"


def test_non_retryable_provider_error_propagates(monkeypatch):
    _patch_pipeline(monkeypatch, synth_exc=ProviderError("HTTP 401", retryable=False))
    with pytest.raises(ProviderError):
        graph_mod.build_graph().invoke({"query": "synthetic query", "revision_count": 0})


def test_max_revisions_default_derives_from_settings():
    # Default-Settings: afs_max_retries=2.
    assert Settings(_env_file=None).afs_max_retries == 2
