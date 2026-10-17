"""B3 gap analysis (T07): turn an extraction plus rule findings into prioritized
clarification questions.

B3 only asks questions. It never invents facts, numbers, sensor specifications or
sources (T07 acceptance criterion 4). The analysis is deterministic: no LLM call,
no retrieval, no method selection.

Interfaces this builds on (already on the shared contract):
  * input  extraction: ExtractionResult  (T06; stated_facts/unknowns/conflicts)
  * input  rules:      list[RuleFinding]  (T03; outcome excluded/conditional/unknown)
  * output             list[ClarificationQuestion]
                       (question/why_it_matters/priority/blocking)
"""

from src.models import ClarificationQuestion, ExtractionResult, RuleFinding

# Priority bands (1 = highest; contracts.md says B3 sorts ascending, ties allowed).
PRIORITY_RULE_BLOCKING = 1  # a rule cannot clear without this parameter
PRIORITY_CONFLICT = 2  # contradictory statements must be resolved
PRIORITY_MISSING_PARAMETER = 3  # parameter unknown but no rule currently needs it

# Human-readable labels for the closed ParameterName set. Kept descriptive, not
# authoritative units/specs -- B3 asks, it does not assert values.
_PARAMETER_LABELS = {
    "matrix": "the physical/optical sample form (e.g. powder, clear liquid, slurry)",
    "sample_composition": "the sample composition or recipe",
    "target_substance": "the substance or substance group to analyze",
    "target_quantity": "the quantity to measure (e.g. moisture, concentration)",
    "target_range": "the expected measurement range of the target quantity",
    "temperature": "the sample/process temperature",
    "pressure": "the process pressure",
    "flow_conditions": "the flow conditions (flow, stagnation, etc.)",
    "measurement_location": "the physical measurement location",
    "measurement_mode": "the integration mode (in-line, on-line, at-line or lab)",
    "existing_equipment": "any already present hardware, probes or calibration",
    "optical_access": "the available optical access to the sample",
    "required_accuracy": "the required accuracy or uncertainty",
    "required_response_time": "the required response time or measurement frequency",
    "reference_method": "an available independent reference method",
    "process_constraints": "further constraints (hygiene, cleaning, Ex, budget, ...)",
}


def _label(parameter: str) -> str:
    return _PARAMETER_LABELS.get(parameter, parameter)


def _conflicted_parameters(extraction: ExtractionResult) -> set[str]:
    return {conflict.parameter for conflict in getattr(extraction, "conflicts", []) or []}


def analyze_gaps(
    extraction: ExtractionResult,
    rules: list[RuleFinding],
) -> list[ClarificationQuestion]:
    """Determine decision-relevant information gaps and prioritized questions.

    Behavior (per T07 acceptance criteria):

    1. Checks extracted parameters against the rule findings: a RuleFinding with
       outcome="unknown" marks a rule that cannot clear because a required
       parameter is missing or disputed -> a decision-BLOCKING gap.
    2. Each question carries a priority (1 = highest) and a factual
       why_it_matters that names the rule / why the gap blocks a decision.
    3. Rule-blocking gaps and unresolved conflicts are blocking=True; parameters
       that are merely unknown (no rule needs them yet) are blocking=False and
       lower priority.
    4. Produces questions only -- never numeric or sensor specifications, even
       when the target substance is unknown.
    5. Returns a priority-ascending list usable by synthesis (T08) and the UI.

    Deduplicates so one gap yields one question; a rule-blocking parameter is not
    repeated as a plain missing-parameter question.
    """
    unknowns = list(getattr(extraction, "unknowns", []) or [])
    conflicted = _conflicted_parameters(extraction)

    questions: list[ClarificationQuestion] = []
    covered: set[str] = set()

    # (1)+(2) Rule-driven blocking gaps. An "unknown" finding means a rule could
    # not be applied because a required parameter is not stated or is disputed.
    for finding in rules:
        if finding.outcome != "unknown":
            continue
        questions.append(
            ClarificationQuestion(
                question=(
                    "Which information is missing so that the "
                    f"applicable rule ({finding.rule_id}) can be evaluated?"
                ),
                why_it_matters=(
                    f"Rule {finding.rule_id} cannot reach a decision yet: {finding.reason}"
                ),
                priority=PRIORITY_RULE_BLOCKING,
                blocking=True,
            )
        )

    # (3) Unresolved contradictions from T06 -- blocking, must be clarified.
    for parameter in sorted(conflicted):
        if parameter in covered:
            continue
        covered.add(parameter)
        questions.append(
            ClarificationQuestion(
                question=(
                    f"Multiple conflicting statements were given about {_label(parameter)}. "
                    "Which value applies, and to which process state?"
                ),
                why_it_matters=(
                    "Contradictory values cannot be used by downstream rules until "
                    "their scope is clarified."
                ),
                priority=PRIORITY_CONFLICT,
                blocking=True,
            )
        )

    # (4)+(5) Remaining unknown parameters that no rule currently blocks on:
    # worth asking, but not decision-blocking. No specs are invented here.
    for parameter in unknowns:
        if parameter in covered or parameter in conflicted:
            continue
        covered.add(parameter)
        questions.append(
            ClarificationQuestion(
                question=f"Could you specify {_label(parameter)}?",
                why_it_matters=(
                    f"{parameter} was not stated; it may refine the method choice but "
                    "does not block a provisional assessment on its own."
                ),
                priority=PRIORITY_MISSING_PARAMETER,
                blocking=False,
            )
        )

    # Stable, priority-ascending order; ties keep insertion order.
    return sorted(questions, key=lambda q: q.priority)


def gaps_node(state: dict) -> dict:
    """T11 adapter: only update questions; do not execute the rest of the graph.

    Mirrors engine.extraction.extraction_node. Reads the extraction and rule
    findings already present in the pipeline state and writes the questions field.
    """
    return {"questions": analyze_gaps(state["extraction"], state.get("rules", []))}
