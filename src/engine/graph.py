"""T11 LangGraph orchestration: wire the pipeline bricks behind analyze(query).

Dieses Modul verbindet die bereits gemergten Bausteine zu einer kontrollierten
Pipeline:

    extraction (B2) -> rules (B3-Matrix) -> retrieval (B4) -> gaps (B3-Fragen)
        -> synthesis (B4/B5) -> [experiment-plan seam / B6] -> gate (B7)

LangGraph 1.x wird mit einem typisierten :class:`~src.state.PipelineState`
(TypedDict) betrieben. Jeder Knoten liefert ein partielles Dict-Update; v1 hat
keine konkurrierenden Schreiber auf dasselbe Feld, daher ist die Topologie
bewusst linear sequenziert, sodass jedes Feld von genau einem Knoten geschrieben
wird, bevor es gelesen wird. Diese Reihenfolge erfuellt alle Datenabhaengigkeiten:

  * ``rules`` wird vor ``gaps`` geschrieben (gaps_node liest ``state['rules']``);
  * ``rules`` UND ``evidence`` liegen vor ``synthesis`` vor (synthesize liest
    extraction, rules, questions und evidence).

Die Knoten extraction_node / gaps_node / synthesis_node stammen aus den
bestehenden Engine-Modulen und werden hier NICHT neu implementiert. rules_node
und retrieval_node sind duenne Adapter um Kevins ``src.knowledge``-Funktionen;
sie leben laut Teamregel hier in graph.py, nicht in rules.py/retrieval.py.

Korrekturschleife und definiertes Fehlerergebnis
------------------------------------------------
Die Obergrenze :data:`MAX_REVISIONS` wird aus ``Settings().afs_max_retries``
abgeleitet (dokumentierte Wiederverwendung). Nach dem Gate entscheidet eine
bedingte Kante:

  * meldet die :class:`~src.models.ValidationReport` Fehler UND ist
    ``revision_count < MAX_REVISIONS``, wird ``revision_count`` erhoeht und zu
    synthesis zurueckgesprungen;
  * andernfalls endet der Graph.

Wird die Obergrenze erreicht und die Validierung meldet weiterhin Fehler, erzeugt
der Gate-Knoten ein DEFINIERTES Fehlerergebnis: eine gueltige
:class:`~src.models.AnalysisResult` mit ``decision_status =
"insufficient_information"`` (bewusst nicht ``provisional``), die die
Gate-Befunde in ``validation_findings`` traegt. So wird nie aus einem
Validierungsfehler eine wissenschaftliche Freigabe.

Offene Grenzen (Seams)
----------------------
  * T10 B7 Validierungs-Gate (``src/engine/validators.py``, Kevin) ist NICHT
    implementiert. Der Default-Pfad ohne Validator laesst den Synthese-Entwurf
    als ``state['result']`` durch (Pass-through) und terminiert nach einem Lauf.
    Sobald T10 landet, wird der Validator an :func:`gate_node` eingehaengt und
    die Schleife konsumiert ``ValidationReport.has_errors`` -- die Struktur ist
    bereits dafuer vorbereitet.
  * T09 B6 Versuchsplan (``src/engine/experiment.py``, Jakob) ist NICHT
    implementiert. AnalysisResult traegt bereits ``feasibility_plan`` und
    ``go_no_go_criteria`` aus der Synthese, daher ist noch kein eigener
    Experiment-Knoten noetig. :func:`experiment_node` ist ein markierter
    Platzhalter (Pass-through), in den T09 spaeter einsteigt.
  * T05 Few-Shot-Beispiele (``examples``) sind nicht implementiert; das Feld
    bleibt optional/leer, die Synthese akzeptiert einen leeren Pfad.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.config import Settings
from src.engine.extraction import extraction_node
from src.engine.gaps import gaps_node
from src.engine.synthesis import synthesis_node
from src.knowledge.rules import evaluate_rules
from src.knowledge.retrieval import retrieve

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.models import ValidationReport

# Default-Settings-Provider. In Tests monkeypatchbar (wie extraction/synthesis
# ein injizierbares Settings-Objekt erhalten), ohne dass der Graph bei jedem
# Knotenaufruf .env neu laedt.
_DEFAULT_SETTINGS: Settings | None = None


def _settings() -> Settings:
    """Liefert die (gecachten) Settings fuer die Knoten-Adapter.

    Lazy, damit das Importieren dieses Moduls nie Credentials liest; Tests
    koennen ``_DEFAULT_SETTINGS`` setzen oder die Node-Funktionen direkt mit
    Stubs monkeypatchen.
    """

    global _DEFAULT_SETTINGS
    if _DEFAULT_SETTINGS is None:
        _DEFAULT_SETTINGS = Settings()
    return _DEFAULT_SETTINGS


# Obergrenze der Korrekturschleife. Wiederverwendung von afs_max_retries: die
# Synthese darf genauso oft nachgebessert werden, wie ein Provider-Aufruf
# wiederholt werden darf. Bei afs_max_retries=0 laeuft die Pipeline genau einmal.
# Der Default wird einmalig aus den Settings abgeleitet; Tests koennen den Wert
# ueber set_max_revisions() setzen, ohne .env zu benoetigen.
MAX_REVISIONS: int = Settings(_env_file=None).afs_max_retries


def set_max_revisions(value: int) -> None:
    """Setze die Korrekturschleifen-Obergrenze (z. B. aus Settings oder in Tests)."""

    global MAX_REVISIONS
    MAX_REVISIONS = value


# Fehlercode des definierten Fehlerergebnisses, wenn die Korrekturschleife ihre
# Obergrenze erreicht und die Validierung weiterhin Fehler meldet.
REVISION_LIMIT_CODE = "revision_limit_reached"


def rules_node(state: dict) -> dict:
    """T11-Adapter: Regel-Matrix (B3/T03) auf die Extraktion anwenden.

    Duenner Wrapper um :func:`src.knowledge.rules.evaluate_rules`; die eigentliche
    Logik bleibt in Kevins Modul. Muss vor gaps_node laufen, da gaps_node
    ``state['rules']`` liest.
    """

    return {"rules": evaluate_rules(state["extraction"])}


def retrieval_node(state: dict) -> dict:
    """T11-Adapter: Evidenz-Retrieval (B4/T04) zur Query.

    Duenner Wrapper um :func:`src.knowledge.retrieval.retrieve`; ``k`` kommt aus
    ``Settings().afs_retrieval_k``. Muss vor synthesis_node laufen, da die
    Synthese ``state['evidence']`` liest.
    """

    k = _settings().afs_retrieval_k
    return {"evidence": retrieve(state["query"], k)}


def experiment_node(state: dict) -> dict:
    """SEAM fuer T09 B6 (``src/engine/experiment.py``, noch nicht implementiert).

    Der Versuchsplan (feasibility_plan) und die Go/No-Go-Kriterien werden heute
    bereits von der Synthese gefuellt, daher ist hier kein eigener Schritt
    noetig: Pass-through. Wenn T09 landet, erzeugt dieser Knoten den Plan und
    liefert z. B. ``{"draft": draft_mit_plan}`` zurueck.
    """

    return {}


def gate_node(state: dict) -> dict:
    """B7-Gate (T10). Validator noch nicht implementiert -> minimaler Pass-through.

    Verhalten:

      * Liegt eine :class:`~src.models.ValidationReport` in ``state['validation']``
        vor (durch einen injizierten/zukuenftigen Validator) und meldet sie
        Fehler, waehrend die Obergrenze erreicht ist, wird ein DEFINIERTES
        Fehlerergebnis erzeugt (``insufficient_information`` mit den Befunden in
        ``validation_findings``).
      * Ohne Validator (Default) wird der Synthese-Entwurf unveraendert als
        ``state['result']`` durchgereicht und die Pipeline terminiert nach einem
        Lauf.

    Sobald T10s Validator landet, wird er hier aufgerufen und schreibt die
    ValidationReport; :func:`should_revise` konsumiert dann ``has_errors``.
    """

    draft = state.get("draft")
    report: ValidationReport | None = state.get("validation")
    revision_count = state.get("revision_count", 0)

    # Default-Pfad ohne Validator: Entwurf durchreichen.
    if report is None or not report.has_errors:
        return {"result": draft}

    # Validierung meldet Fehler. Solange die Obergrenze nicht erreicht ist,
    # wird NICHT durchgereicht; should_revise() routet zurueck zur Synthese.
    if revision_count < MAX_REVISIONS:
        return {}

    # Obergrenze erreicht und weiterhin Fehler: definiertes Fehlerergebnis.
    return {"result": _failure_result(draft, report)}


def _failure_result(draft, report: ValidationReport):
    """Definiertes Fehlerergebnis der Korrekturschleife.

    Eine gueltige :class:`~src.models.AnalysisResult` mit
    ``decision_status="insufficient_information"`` (nicht ``provisional``), die
    die Gate-Befunde traegt. Es werden keine Fakten, Kennwerte oder Quellen
    erfunden: alle deterministischen Felder stammen aus dem Synthese-Entwurf;
    Empfehlungen und Quellen werden geleert, da sie das Gate nicht bestanden
    haben.
    """

    from src.models import AnalysisResult, ValidationFinding

    findings = list(report.findings)
    findings.append(
        ValidationFinding(
            code=REVISION_LIMIT_CODE,
            severity="error",
            message=(
                "Correction loop reached its revision limit while validation still "
                "reported errors; no provisional result is released."
            ),
            field_path="decision_status",
        )
    )

    if draft is None:
        return AnalysisResult(
            decision_status="insufficient_information",
            stated_facts=[],
            assumptions=[],
            unknowns=[],
            clarification_questions=[],
            recommendations=[],
            measurement_concept="Analysis did not pass validation.",
            risks_and_limits=[],
            feasibility_plan=[],
            go_no_go_criteria=[],
            overall_sources=[],
            validation_findings=findings,
        )

    return draft.model_copy(
        update={
            "decision_status": "insufficient_information",
            "recommendations": [],
            "overall_sources": [],
            "validation_findings": findings,
        }
    )


def should_revise(state: dict) -> str:
    """Bedingte Kante nach dem Gate: ``"revise"`` oder ``"end"``.

    Die Korrekturschleife springt nur dann zur Synthese zurueck, wenn eine
    ValidationReport Fehler meldet UND die Obergrenze noch nicht erreicht ist.
    Ohne Validator (Default) oder ohne Fehler endet der Graph sofort.
    """

    report: ValidationReport | None = state.get("validation")
    if report is None or not report.has_errors:
        return "end"
    if state.get("revision_count", 0) < MAX_REVISIONS:
        return "revise"
    return "end"


def _increment_revision(state: dict) -> dict:
    """Erhoeht revision_count vor dem Ruecksprung zur Synthese (Schleifenzaehler)."""

    return {"revision_count": state.get("revision_count", 0) + 1}


def build_graph():
    """Baue und kompiliere den StateGraph.

    Topologie (linear sequenziert, da v1 keine konkurrierenden Schreiber kennt):

        START -> extraction -> rules -> retrieval -> gaps -> synthesis
              -> experiment(seam) -> gate -> {revise -> increment -> synthesis | end}

    Diese Reihenfolge erfuellt alle Datenabhaengigkeiten: rules vor gaps,
    rules+evidence vor synthesis.
    """

    from langgraph.graph import END, START, StateGraph

    from src.state import PipelineState

    graph = StateGraph(PipelineState)

    graph.add_node("extraction", extraction_node)
    graph.add_node("rules", rules_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("gaps", gaps_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("experiment", experiment_node)
    graph.add_node("gate", gate_node)
    graph.add_node("increment_revision", _increment_revision)

    graph.add_edge(START, "extraction")
    graph.add_edge("extraction", "rules")
    graph.add_edge("rules", "retrieval")
    graph.add_edge("retrieval", "gaps")
    graph.add_edge("gaps", "synthesis")
    graph.add_edge("synthesis", "experiment")
    graph.add_edge("experiment", "gate")

    graph.add_conditional_edges(
        "gate",
        should_revise,
        {"revise": "increment_revision", "end": END},
    )
    graph.add_edge("increment_revision", "synthesis")

    return graph.compile()


_COMPILED = None


def compiled_graph():
    """Liefert den (einmal kompilierten) Graphen; von service.analyze genutzt."""

    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_graph()
    return _COMPILED
