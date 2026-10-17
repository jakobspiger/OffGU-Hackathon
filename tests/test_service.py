"""T11 service entry-point tests. Synthetic inputs only; no network, no AFS claims.

analyze(query) ist die EINE Funktion, die UI (T12) und Batch (T14) aufrufen.
Hier wird der Guard, das Fail-fast auf fehlende Credentials und der Lauf durch
den kompilierten Graphen (mit gestubbter Synthese) geprueft. Ohne
pydantic/langgraph ueberspringt pytest.importorskip das Modul sauber.
"""

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("langgraph")

from src.config import Settings  # noqa: E402
from src.engine import graph as graph_mod  # noqa: E402
from src.engine import service as service_mod  # noqa: E402
from src.engine.service import analyze  # noqa: E402
from src.errors import ConfigurationError  # noqa: E402
from src.models import AnalysisResult, ExtractionResult  # noqa: E402


def _extraction():
    return ExtractionResult(stated_facts=[], assumptions=[], unknowns=[], conflicts=[])


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
    monkeypatch.setattr(graph_mod, "_COMPILED", None, raising=False)
    graph_mod.set_max_revisions(0)
    yield


@pytest.mark.parametrize("bad", ["", "   ", "\n\t "])
def test_empty_query_raises_value_error(bad):
    with pytest.raises(ValueError):
        analyze(bad)


def test_non_string_query_raises_value_error():
    with pytest.raises(ValueError):
        analyze(None)  # type: ignore[arg-type]


def test_missing_key_raises_configuration_error(monkeypatch):
    # Settings ohne Key/Model -> require_llm() scheitert fruehzeitig.
    monkeypatch.setattr(service_mod, "Settings", lambda: Settings(_env_file=None))
    with pytest.raises(ConfigurationError):
        analyze("synthetic query")


def test_happy_path_returns_analysis_result(monkeypatch):
    # Settings mit Key/Model, damit require_llm() durchlaeuft.
    monkeypatch.setattr(
        service_mod,
        "Settings",
        lambda: Settings(_env_file=None, openai_api_key="sk-test", openai_model="test-model"),
    )
    # Schwere Schritte durch Fakes ersetzen; kein Netzwerk.
    monkeypatch.setattr("src.engine.extraction.extract", lambda query, **kw: _extraction())
    monkeypatch.setattr(graph_mod, "evaluate_rules", lambda extraction: [])
    monkeypatch.setattr(graph_mod, "retrieve", lambda query, k: [])
    monkeypatch.setattr(
        "src.engine.synthesis.synthesize",
        lambda *a, **k: _analysis_result(status="provisional"),
    )

    result = analyze("synthetic query")
    assert isinstance(result, AnalysisResult)
    assert result.decision_status == "provisional"


def test_result_falls_back_to_draft(monkeypatch):
    """Wenn das Gate kein result setzt, faellt analyze auf den draft zurueck."""

    monkeypatch.setattr(
        service_mod,
        "Settings",
        lambda: Settings(_env_file=None, openai_api_key="sk-test", openai_model="test-model"),
    )
    monkeypatch.setattr("src.engine.extraction.extract", lambda query, **kw: _extraction())
    monkeypatch.setattr(graph_mod, "evaluate_rules", lambda extraction: [])
    monkeypatch.setattr(graph_mod, "retrieve", lambda query, k: [])
    draft = _analysis_result(status="insufficient_information")
    monkeypatch.setattr("src.engine.synthesis.synthesize", lambda *a, **k: draft)
    # Gate gibt kein result zurueck -> service nutzt draft.
    monkeypatch.setattr(graph_mod, "gate_node", lambda state: {})

    result = analyze("synthetic query")
    assert result.decision_status == "insufficient_information"
