"""B3 gap analysis (T07): turn an extraction plus rule findings into prioritized
clarification questions.

SCAFFOLDING ONLY. The public shape and contracts are fixed here so T08 (synthesis)
and T11 (graph) can integrate against stable signatures, but the decision logic is
not implemented yet -- analyze_gaps raises ComponentNotReadyError.

Interfaces this builds on (already on the shared contract):
  * input  extraction: ExtractionResult  (T06; stated_facts/unknowns/conflicts)
  * input  rules:      list[RuleFinding]  (T03; outcome excluded/conditional/unknown)
  * output             list[ClarificationQuestion]
                       (question/why_it_matters/priority/blocking)

B3 only asks questions. It never invents facts, numbers, sensor specifications or
sources (T07 acceptance criterion 4).
"""

from src.errors import ComponentNotReadyError
from src.models import ClarificationQuestion, ExtractionResult, RuleFinding


def analyze_gaps(
    extraction: ExtractionResult,
    rules: list[RuleFinding],
) -> list[ClarificationQuestion]:
    """Determine decision-relevant information gaps and prioritized questions.

    Planned behavior (not yet implemented -- see T07 acceptance criteria):

    1. Check extracted parameters against relevant requirements and rule findings.
       A RuleFinding with outcome="unknown" marks a rule that cannot clear because
       a required parameter is missing or disputed -> a decision-BLOCKING gap.
    2. Each question carries a priority (1 = highest, ascending) and a factual
       why_it_matters that names the rule/parameter responsible for the gap.
    3. Separate decision-blocking gaps (blocking=True) from details that can be
       clarified later (blocking=False, lower priority).
    4. Never translate an unknown target substance into exact sensor specs; B3
       produces questions only, no numeric or performance values.
    5. Return a structured, priority-ascending list usable by synthesis (T08) and
       the UI, matching contracts.md (B3 sorts ascending; ties allowed).

    Open interface point with T03 (Kevin): confirm how a disputed parameter
    (ExtractionResult.conflicts) should be phrased vs. a fully missing one.
    """
    raise ComponentNotReadyError("Gap analysis (B3/T07) is not implemented yet.")


def gaps_node(state: dict) -> dict:
    """T11 adapter: only update questions; do not execute the rest of the graph.

    Mirrors engine.extraction.extraction_node. Reads the extraction and rule
    findings already present in the pipeline state and writes the questions field.
    """
    return {"questions": analyze_gaps(state["extraction"], state.get("rules", []))}
