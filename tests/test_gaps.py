"""T07 B3 gap-analyzer tests. Synthetic inputs only; no AFS scientific claims."""

from src.engine.gaps import (
    PRIORITY_CONFLICT,
    PRIORITY_MISSING_PARAMETER,
    PRIORITY_RULE_BLOCKING,
    analyze_gaps,
    gaps_node,
)
from src.models import (
    ExtractedFact,
    ExtractionResult,
    ParameterConflict,
    RuleFinding,
    SourceReference,
)


def _extraction(stated=None, unknowns=None, conflicts=None):
    return ExtractionResult(
        stated_facts=stated or [],
        assumptions=[],
        unknowns=unknowns or [],
        conflicts=conflicts or [],
    )


def _finding(rule_id, outcome, reason="synthetic reason"):
    return RuleFinding(
        rule_id=rule_id,
        outcome=outcome,
        reason=reason,
        source_refs=[SourceReference(source_id="S01", page=1)],
    )


def test_no_gaps_yields_no_questions():
    extraction = _extraction(
        stated=[ExtractedFact(parameter="matrix", value="Pulver", input_quote="Pulver")],
    )
    assert analyze_gaps(extraction, []) == []


def test_unknown_rule_finding_is_blocking_and_top_priority():
    extraction = _extraction(unknowns=["target_substance"])
    rules = [_finding("R01", "unknown", "needs target_substance")]
    questions = analyze_gaps(extraction, rules)
    blocking = [q for q in questions if q.blocking]
    assert blocking, "an unknown rule finding must create a blocking question"
    assert blocking[0].priority == PRIORITY_RULE_BLOCKING
    assert "R01" in blocking[0].why_it_matters


def test_excluded_and_conditional_findings_do_not_create_gaps():
    extraction = _extraction(
        stated=[ExtractedFact(parameter="matrix", value="Pulver", input_quote="Pulver")],
    )
    rules = [_finding("R02", "excluded"), _finding("R03", "conditional")]
    assert analyze_gaps(extraction, rules) == []


def test_conflict_produces_blocking_question():
    extraction = _extraction(
        stated=[
            ExtractedFact(parameter="temperature", value="20 °C", input_quote="20 °C"),
            ExtractedFact(parameter="temperature", value="80 °C", input_quote="80 °C"),
        ],
        unknowns=["temperature"],
        conflicts=[
            ParameterConflict(parameter="temperature", fact_indices=[0, 1], reason="unclear")
        ],
    )
    questions = analyze_gaps(extraction, [])
    conflict_qs = [q for q in questions if q.priority == PRIORITY_CONFLICT]
    assert len(conflict_qs) == 1
    assert conflict_qs[0].blocking is True
    # The conflicted parameter must not also appear as a plain missing-parameter question.
    assert not any(q.priority == PRIORITY_MISSING_PARAMETER for q in questions)


def test_plain_unknown_is_non_blocking_and_lower_priority():
    extraction = _extraction(unknowns=["required_accuracy"])
    questions = analyze_gaps(extraction, [])
    assert len(questions) == 1
    assert questions[0].blocking is False
    assert questions[0].priority == PRIORITY_MISSING_PARAMETER


def test_questions_are_sorted_by_priority_ascending():
    extraction = _extraction(
        unknowns=["required_accuracy", "temperature"],
        conflicts=[
            ParameterConflict(parameter="temperature", fact_indices=[0, 1], reason="unclear")
        ],
        stated=[
            ExtractedFact(parameter="temperature", value="20 °C", input_quote="20 °C"),
            ExtractedFact(parameter="temperature", value="80 °C", input_quote="80 °C"),
        ],
    )
    rules = [_finding("R01", "unknown", "needs target_substance")]
    priorities = [q.priority for q in analyze_gaps(extraction, rules)]
    assert priorities == sorted(priorities)


def test_unknown_target_substance_never_produces_numbers():
    extraction = _extraction(unknowns=["target_substance", "target_range"])
    for question in analyze_gaps(extraction, []):
        text = question.question + " " + question.why_it_matters
        # B3 asks, it never asserts a numeric spec.
        assert not any(ch.isdigit() for ch in text)


def test_gaps_node_updates_only_questions():
    extraction = _extraction(unknowns=["required_accuracy"])
    update = gaps_node({"query": "x", "extraction": extraction, "rules": []})
    assert set(update) == {"questions"}
    assert update["questions"][0].blocking is False
