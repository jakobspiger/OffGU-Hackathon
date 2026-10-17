"""B4/B5 solution synthesis (T08): derive conditional method candidates and a
measurement concept from evidence.

SCAFFOLDING ONLY. The public shape and contracts are fixed here so T11 (graph)
can integrate against stable signatures, but the synthesis logic is not
implemented yet -- synthesize raises ComponentNotReadyError.

B4/B5 is evidence-grounded and conservative: it proposes only conditional
candidates backed by concrete evidence passages, never invents facts, numbers,
spectral specifications or sources, and abstains instead of forcing a choice.

Interfaces this builds on (already on the shared contract):
  * input  extraction: ExtractionResult        (T06)
  * input  rules:      list[RuleFinding]        (T03; excluded/conditional/unknown)
  * input  questions:  list[ClarificationQuestion]  (T07)
  * input  evidence:   list[Evidence]           (T04 retrieval)
  * output             AnalysisResult           (synthesis draft; validated later by T10)
"""

from src.errors import ComponentNotReadyError
from src.models import (
    AnalysisResult,
    ClarificationQuestion,
    Evidence,
    ExtractionResult,
    RuleFinding,
)


def synthesize(
    extraction: ExtractionResult,
    rules: list[RuleFinding],
    questions: list[ClarificationQuestion],
    evidence: list[Evidence],
) -> AnalysisResult:
    """Produce the synthesis draft AnalysisResult (not yet implemented).

    Planned behavior (per T08 acceptance criteria):

    1. Each Recommendation carries why, conditions, measurement_geometry, risks
       (via risks_and_limits) and source_refs/evidence_ids.
    2. Every material technical claim links to a concrete Evidence passage
       (evidence_ids), not just a source id.
    3. SpectralRange uses correct units (nm for wavelength, cm^-1 for
       wavenumber/Raman shift) and is marked scope="nominal_method_only" vs.
       "verified_instrument". Missing spectral data stays None, never guessed.
    4. Missing evidence leads to uncertainty or abstention, not a forced pick:
       excluded rules remove candidates, unknown findings and open blocking
       questions push toward insufficient_information.
    5. decision_status is one of provisional / insufficient_information /
       out_of_scope.
    6. The model's structured answer is validated against AnalysisResult; parsing
       failures get bounded retries (reuse the provider/retry pattern from
       engine.extraction, no raw provider body in logs).

    AnalysisResult.check_recommendation_sources already enforces that every
    recommendation source also appears in overall_sources.
    """
    raise ComponentNotReadyError("Solution synthesis (B4/B5/T08) is not implemented yet.")


def synthesis_node(state: dict) -> dict:
    """T11 adapter: only update draft; do not execute the rest of the graph.

    Mirrors engine.extraction.extraction_node / engine.gaps.gaps_node. Reads the
    extraction, rule findings, questions and evidence already present in the
    pipeline state and writes the draft field.
    """
    return {
        "draft": synthesize(
            state["extraction"],
            state.get("rules", []),
            state.get("questions", []),
            state.get("evidence", []),
        )
    }
