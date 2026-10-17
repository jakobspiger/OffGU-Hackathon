"""B4/B5 solution synthesis (T08): derive conditional method candidates and a
measurement concept from evidence.

B4/B5 is evidence-grounded and conservative. The LLM only drafts the free-form
narrative and candidate rationale; this module enforces the hard guarantees
deterministically AROUND the model so the output cannot force an unsupported
choice:

  * no evidence -> abstain (insufficient_information, no recommendations);
  * every recommendation must cite evidence_ids that actually exist in the
    provided evidence, otherwise it is dropped;
  * a method a rule marks "excluded" is never recommended;
  * stated_facts / unknowns / clarification_questions are filled from the T06/T07
    inputs, never invented by the model;
  * the model answer is validated against AnalysisResult with bounded retries,
    reusing the provider/retry pattern from engine.extraction.

Interfaces (shared contract):
  * input  extraction: ExtractionResult        (T06)
  * input  rules:      list[RuleFinding]        (T03; excluded/conditional/unknown)
  * input  questions:  list[ClarificationQuestion]  (T07)
  * input  evidence:   list[Evidence]           (T04 retrieval)
  * output             AnalysisResult           (synthesis draft; validated later by T10)
"""

import json
import time
from typing import Protocol

from pydantic import Field

from src.config import Settings
from src.engine.extraction import MAX_QUERY_LENGTH
from src.engine.prompts import SYNTHESIS_SYSTEM_PROMPT, SYNTHESIS_USER_TEMPLATE
from src.engine.provider import ChatJSONProvider
from src.errors import ProviderError, SynthesisError
from src.models import (
    AnalysisResult,
    ClarificationQuestion,
    ContractModel,
    DecisionStatus,
    Evidence,
    ExtractionResult,
    Recommendation,
    RuleFinding,
    SourceReference,
)


class SynthesisProvider(Protocol):
    def complete(self, system: str, query: str) -> str: ...


class SynthesisDraft(ContractModel):
    """What the model is allowed to draft. The deterministic fields of
    AnalysisResult (stated_facts/unknowns/clarification_questions) are added by
    this module, not by the model."""

    decision_status: DecisionStatus
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=20)
    measurement_concept: str = ""
    risks_and_limits: list[str] = Field(default_factory=list, max_length=50)
    go_no_go_criteria: list[str] = Field(default_factory=list, max_length=50)


def _excluded_methods(rules: list[RuleFinding]) -> set[str]:
    return {r.rule_id for r in rules if r.outcome == "excluded"}


def _facts_block(extraction: ExtractionResult) -> str:
    lines = [f"- {f.parameter}: {f.value}" for f in extraction.stated_facts]
    return "\n".join(lines) or "(none stated)"


def _questions_block(questions: list[ClarificationQuestion]) -> str:
    lines = [f"- (p{q.priority}, blocking={q.blocking}) {q.question}" for q in questions]
    return "\n".join(lines) or "(none)"


def _rules_block(rules: list[RuleFinding]) -> str:
    lines = [f"- {r.rule_id}: {r.outcome} — {r.reason}" for r in rules]
    return "\n".join(lines) or "(no rule findings)"


def _evidence_block(evidence: list[Evidence]) -> str:
    lines = [f"- [{e.evidence_id}] (S:{e.source_id} p:{e.page}) {e.text}" for e in evidence]
    return "\n".join(lines) or "(no evidence retrieved)"


def _has_blocking_question(questions: list[ClarificationQuestion]) -> bool:
    return any(q.blocking for q in questions)


def _assemble(
    draft: SynthesisDraft,
    extraction: ExtractionResult,
    questions: list[ClarificationQuestion],
    evidence: list[Evidence],
    rules: list[RuleFinding],
) -> AnalysisResult:
    """Apply the deterministic guardrails and build the validated AnalysisResult."""
    available_evidence_ids = {e.evidence_id for e in evidence}
    excluded = _excluded_methods(rules)

    # Keep only recommendations grounded in evidence we actually have, and never
    # one a rule excluded. Recommendation already requires >=1 evidence_id.
    grounded: list[Recommendation] = []
    for rec in draft.recommendations:
        if rec.method in excluded:
            continue
        if not set(rec.evidence_ids) <= available_evidence_ids:
            continue
        grounded.append(rec)

    # Abstain unless we can actually support a candidate; open blocking questions
    # or missing evidence must not be overridden into a provisional pick.
    status: DecisionStatus = draft.decision_status
    if not evidence or not grounded or _has_blocking_question(questions):
        if status != "out_of_scope":
            status = "insufficient_information"
        grounded = []

    # overall_sources must cover every recommendation source (contract validator).
    overall: list[SourceReference] = []
    seen: set[tuple] = set()
    for rec in grounded:
        for ref in rec.source_refs:
            key = (ref.source_id, ref.page)
            if key not in seen:
                seen.add(key)
                overall.append(SourceReference(source_id=ref.source_id, page=ref.page))

    return AnalysisResult(
        decision_status=status,
        stated_facts=[f"{f.parameter}: {f.value}" for f in extraction.stated_facts],
        assumptions=list(extraction.assumptions),
        unknowns=list(extraction.unknowns),
        clarification_questions=list(questions),
        recommendations=grounded,
        measurement_concept=draft.measurement_concept or "Pending further evidence.",
        risks_and_limits=draft.risks_and_limits,
        feasibility_plan=[],
        go_no_go_criteria=draft.go_no_go_criteria,
        overall_sources=overall,
    )


def synthesize(
    extraction: ExtractionResult,
    rules: list[RuleFinding],
    questions: list[ClarificationQuestion],
    evidence: list[Evidence],
    *,
    query: str = "",
    provider: SynthesisProvider | None = None,
    settings: Settings | None = None,
) -> AnalysisResult:
    """Produce the synthesis draft AnalysisResult.

    At most 1 + afs_max_retries provider calls; a provider/validation failure
    never becomes a scientific result. See module docstring for the guarantees.
    """
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"query exceeds {MAX_QUERY_LENGTH} characters.")
    settings = settings or Settings()
    provider = provider or ChatJSONProvider(settings)
    schema = json.dumps(SynthesisDraft.model_json_schema(), ensure_ascii=False)
    system = SYNTHESIS_SYSTEM_PROMPT + schema
    user = SYNTHESIS_USER_TEMPLATE.format(
        query=query or "(not provided)",
        facts=_facts_block(extraction),
        questions=_questions_block(questions),
        rules=_rules_block(rules),
        evidence=_evidence_block(evidence),
    )
    for attempt in range(settings.afs_max_retries + 1):
        try:
            raw = provider.complete(system, user)
            draft = SynthesisDraft.model_validate_json(raw)
            return _assemble(draft, extraction, questions, evidence, rules)
        except ProviderError as error:
            if not error.retryable:
                raise
        except ValueError:
            # No raw provider body in logs; just reinforce the schema requirement.
            system = (
                SYNTHESIS_SYSTEM_PROMPT
                + schema
                + "\nPrevious output failed validation. Return schema-valid JSON; "
                "cite only provided evidence_ids; invent nothing."
            )
        if attempt < settings.afs_max_retries:
            time.sleep(min(2**attempt, 4))
    raise SynthesisError("Synthesis failed after bounded attempts; no result was accepted.")


def synthesis_node(state: dict) -> dict:
    """T11 adapter: only update draft; do not execute the rest of the graph.

    Mirrors engine.extraction.extraction_node / engine.gaps.gaps_node.
    """
    return {
        "draft": synthesize(
            state["extraction"],
            state.get("rules", []),
            state.get("questions", []),
            state.get("evidence", []),
            query=state.get("query", ""),
        )
    }
