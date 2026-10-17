"""Tests for the T03 deterministic rule matrix (src.knowledge.rules).

Design mirrors the rest of the suite (see tests/conftest.py): the pure-logic
paths (YAML parsing, the parameter-version set gate, predicate matching, the
rule-file content invariants) run on the standard library alone, while the
paths that build a contract ``RuleFinding`` (pydantic via ``src.models``) are
guarded with ``pytest.importorskip``. The full run happens locally on the
maintainer's machine via ``uv run --locked pytest -q``.
"""

from __future__ import annotations

import inspect
import os
import re

import pytest

from src.knowledge import rules
from src.knowledge.rules import (
    RuleCondition,
    RuleConfigError,
    RulesMeta,
    _condition_holds,
    _verify_parameter_version,
    load_rule_set,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(_ROOT, "data", "rules")

# The canonical 16 ParameterName values (verbatim from T06 / docs/parameters.md).
# Kept here so the positive gate test does not depend on importing pydantic.
CANONICAL_PARAMETERS = (
    "matrix",
    "sample_composition",
    "target_substance",
    "target_quantity",
    "target_range",
    "temperature",
    "pressure",
    "flow_conditions",
    "measurement_location",
    "measurement_mode",
    "existing_equipment",
    "optical_access",
    "required_accuracy",
    "required_response_time",
    "reference_method",
    "process_constraints",
)


# ---------------------------------------------------------------------------
# Small stdlib stand-ins for ExtractedFact / ExtractionResult. evaluate_rules
# only reads .stated_facts[*].parameter/.value, .unknowns and (optionally)
# .conflicts, so these duck-typed stubs are enough for the pure-logic checks.
# ---------------------------------------------------------------------------
class _Fact:
    def __init__(self, parameter: str, value: str) -> None:
        self.parameter = parameter
        self.value = value
        self.input_quote = value


class _Extraction:
    def __init__(self, stated_facts, unknowns=None, conflicts=None) -> None:
        self.stated_facts = stated_facts
        self.assumptions: list[str] = []
        self.unknowns = unknowns or []
        if conflicts is not None:
            self.conflicts = conflicts


# ---------------------------------------------------------------------------
# Loading + the parameter-version gate (pure logic, no pydantic).
# ---------------------------------------------------------------------------
def test_rules_load_structurally_without_contract():
    """The declarative files load and self-validate without the live contract."""

    rule_set = load_rule_set(RULES_DIR, verify_parameter_version=False)
    assert rule_set.rules, "rule set must not be empty"
    assert rule_set.meta.rule_set_version
    assert len(rule_set.meta.expected_parameter_names) == 16
    # Deterministic order by rule_id.
    ids = [r.rule_id for r in rule_set.rules]
    assert ids == sorted(ids)
    # rule_ids are unique.
    assert len(ids) == len(set(ids))


def test_meta_expected_names_match_canonical_sixteen():
    """rules_meta.yaml freezes exactly the 16 canonical ParameterName values."""

    rule_set = load_rule_set(RULES_DIR, verify_parameter_version=False)
    assert set(rule_set.meta.expected_parameter_names) == set(CANONICAL_PARAMETERS)


def test_parameter_version_gate_positive():
    """Gate passes when rules_meta matches the expected parameter set."""

    meta = RulesMeta(
        rule_set_version="1.0",
        parameter_contract="x",
        expected_parameter_names=CANONICAL_PARAMETERS,
    )
    # Must not raise.
    _verify_parameter_version(meta, CANONICAL_PARAMETERS)


def test_parameter_version_gate_negative_tampered_names():
    """A tampered expected_parameter_names raises RuleConfigError (steering)."""

    tampered = RulesMeta(
        rule_set_version="1.0",
        parameter_contract="x",
        # Drop one real name, add a bogus one: both a missing and an extra.
        expected_parameter_names=CANONICAL_PARAMETERS[:-1] + ("totally_new_param",),
    )
    with pytest.raises(RuleConfigError) as exc:
        _verify_parameter_version(tampered, CANONICAL_PARAMETERS)
    message = str(exc.value)
    assert "process_constraints" in message  # missing from the tampered meta
    assert "totally_new_param" in message  # extra in the tampered meta


def test_load_verifies_against_live_contract_when_available():
    """If src.models exposes ParameterName, the full gate runs against it.

    ParameterName is introduced by T06 (not merged yet). Until then src.models
    has no ParameterName, so this skips rather than failing: T03 was written and
    frozen against the canonical 16 names, and the live gate activates
    automatically once T06 lands.
    """

    pytest.importorskip("pydantic", reason="pydantic is provided by `uv sync --locked`")
    from typing import get_args

    try:
        from src.models import ParameterName
    except ImportError:
        pytest.skip("ParameterName not in src.models yet (T06 not merged)")

    live = set(get_args(ParameterName))
    # Our canonical copy must equal the live contract set.
    assert live == set(CANONICAL_PARAMETERS)
    # And the full load (gate ON) must succeed against the live contract.
    rule_set = load_rule_set(RULES_DIR)
    assert rule_set.rules


# ---------------------------------------------------------------------------
# Rule content invariants (pure logic over the loaded dataclasses / files).
# ---------------------------------------------------------------------------
def test_every_rule_has_id_conditions_outcome_source():
    """Acceptance criterion 1: stable id, conditions, outcome and >=1 source."""

    rule_set = load_rule_set(RULES_DIR, verify_parameter_version=False)
    for rule in rule_set.rules:
        assert rule.rule_id and rule.rule_id.strip()
        assert rule.outcome in rules.VALID_OUTCOMES
        assert rule.reason and rule.reason.strip()
        assert len(rule.source_refs) >= 1
        # Each rule has at least one decision input: a condition or a require.
        assert rule.when or rule.requires
        for cond in rule.when:
            assert cond.parameter in CANONICAL_PARAMETERS
            assert cond.predicate in rules.VALID_PREDICATES
        for ref in rule.source_refs:
            if ref.source_id == "S06":
                assert ref.page is None
            else:
                assert isinstance(ref.page, int) and ref.page >= 1


def test_rules_never_declare_approved_outcome():
    """Outcomes are only {excluded, conditional, unknown}; never 'approved'."""

    rule_set = load_rule_set(RULES_DIR, verify_parameter_version=False)
    for rule in rule_set.rules:
        assert rule.outcome != "approved"
        assert rule.outcome in {"excluded", "conditional", "unknown"}


def test_no_scenario_ids_in_rule_files():
    """Acceptance criterion 5: no scenario-id branching / strings in the rules."""

    forbidden = re.compile(r"\b([HD]0[1-9])\b")
    for filename in os.listdir(RULES_DIR):
        if not filename.endswith(".yaml"):
            continue
        with open(os.path.join(RULES_DIR, filename), encoding="utf-8") as fh:
            text = fh.read()
        assert not forbidden.search(text), f"scenario id found in {filename}"


def test_rules_source_code_has_no_scenario_branching():
    """The engine code must not branch on scenario ids (H0x / D0x)."""

    with open(os.path.join(_ROOT, "src", "knowledge", "rules.py"), encoding="utf-8") as fh:
        code = fh.read()
    assert not re.search(r"\b[HD]0[1-9]\b", code)


def test_qualitative_ratings_not_emitted_as_numbers():
    """Acceptance criterion 3: qualitative ratings never become numbers/specs.

    Any rule reason that mentions the qualitative rating columns must keep them
    qualitative (the words low/average/high/qualitative) and must not attach a
    numeric specification to sensitivity/selectivity/cost.
    """

    rule_set = load_rule_set(RULES_DIR, verify_parameter_version=False)
    rating_words = ("sensitivity", "selectivity", "cost")
    numeric_spec = re.compile(
        r"(sensitivity|selectivity|cost)\s*(?:of|=|:)?\s*\d",
        re.IGNORECASE,
    )
    for rule in rule_set.rules:
        reason = rule.reason
        assert numeric_spec.search(reason) is None, rule.rule_id
        if any(word in reason.lower() for word in rating_words):
            # It must flag them as qualitative, never as measured values.
            assert "qualitative" in reason.lower(), rule.rule_id


def test_nominal_vs_fiber_range_separation():
    """Acceptance criterion 4: nominal method ranges stay separate from fibers.

    The dedicated rule must keep the nominal method range distinct from the
    usable fiber/probe range and never equate the two.
    """

    rule_set = load_rule_set(RULES_DIR, verify_parameter_version=False)
    by_id = {r.rule_id: r for r in rule_set.rules}
    rule = by_id["nominal_range_not_fiber_range"]
    reason = rule.reason.lower()
    assert "nominal" in reason
    assert "fiber" in reason or "probe" in reason
    assert "not" in reason  # explicitly states they are not the same


# ---------------------------------------------------------------------------
# Predicate matching (pure logic).
# ---------------------------------------------------------------------------
def test_value_contains_any_is_case_insensitive():
    facts = {"matrix": [_Fact("matrix", "A CLEAR transparent liquid")]}
    hit = RuleCondition("matrix", "value_contains_any", ("clear",))
    miss = RuleCondition("matrix", "value_contains_any", ("turbid",))
    assert _condition_holds(hit, facts) is True
    assert _condition_holds(miss, facts) is False


def test_presence_predicates():
    facts = {"matrix": [_Fact("matrix", "clear liquid")]}
    assert _condition_holds(RuleCondition("matrix", "parameter_present", ()), facts) is True
    assert _condition_holds(RuleCondition("matrix", "parameter_absent", ()), facts) is False
    assert (
        _condition_holds(RuleCondition("target_substance", "parameter_absent", ()), facts) is True
    )


def test_negate_inverts_predicate():
    facts = {"matrix": [_Fact("matrix", "clear liquid")]}
    cond = RuleCondition("matrix", "parameter_present", (), negate=True)
    assert _condition_holds(cond, facts) is False


def test_loading_rejects_unknown_predicate():
    bad = {
        "rule_id": "bad",
        "when": [{"parameter": "matrix", "predicate": "value_gt", "keywords": ["x"]}],
        "requires": ["matrix"],
        "outcome": "conditional",
        "reason": "x",
        "source_refs": [{"source_id": "S01", "page": 6}],
    }
    with pytest.raises(RuleConfigError):
        rules._parse_rule(bad)


def test_loading_rejects_unknown_outcome():
    bad = {
        "rule_id": "bad",
        "when": [],
        "requires": ["matrix"],
        "outcome": "approved",
        "reason": "x",
        "source_refs": [{"source_id": "S01", "page": 6}],
    }
    with pytest.raises(RuleConfigError):
        rules._parse_rule(bad)


# ---------------------------------------------------------------------------
# evaluate_rules - the only pydantic-dependent path (RuleFinding construction).
# The full engine also needs the live ParameterName (T06) for its gate, so
# these skip until T06 is merged (pydantic present but ParameterName absent).
# ---------------------------------------------------------------------------
def _require_live_contract() -> None:
    pytest.importorskip("pydantic", reason="pydantic is provided by `uv sync --locked`")
    try:
        import src.models as _models  # noqa: F401
    except ImportError:  # pragma: no cover - environment dependent
        pytest.skip("src.models not importable")
    if not hasattr(_models, "ParameterName"):
        pytest.skip("ParameterName not in src.models yet (T06 not merged)")


def test_evaluate_matches_ruleevaluator_protocol():
    """evaluate_rules signature matches src.contracts.RuleEvaluator exactly."""

    pytest.importorskip("pydantic", reason="pydantic is provided by `uv sync --locked`")
    from src.contracts import RuleEvaluator

    sig = inspect.signature(rules.evaluate_rules)
    params = list(sig.parameters)
    assert params == ["extraction"]
    # Structural: evaluate_rules is accepted where a RuleEvaluator is expected.
    evaluator: RuleEvaluator = rules.evaluate_rules
    assert callable(evaluator)


def test_missing_required_parameter_yields_unknown_not_approval():
    """A required parameter that is absent => unknown, never a positive result."""

    _require_live_contract()
    from src.models import ExtractedFact, ExtractionResult

    # target_substance missing entirely => undefined_target_no_spec => unknown.
    extraction = ExtractionResult(
        stated_facts=[ExtractedFact(parameter="matrix", value="clear liquid", input_quote="x")],
        assumptions=[],
        unknowns=["target_substance"],
    )
    findings = rules.evaluate_rules(extraction)
    by_id = {f.rule_id: f for f in findings}
    assert by_id["undefined_target_no_spec"].outcome == "unknown"
    # Nothing is ever cleared / approved.
    assert all(f.outcome in {"excluded", "conditional", "unknown"} for f in findings)


def test_evaluate_emits_conditional_and_excluded_on_match():
    _require_live_contract()
    from src.models import ExtractedFact, ExtractionResult

    # A clear-liquid matrix hits the transmission geometry hint (conditional);
    # a surgical location hits invitro_not_clinical (excluded).
    extraction = ExtractionResult(
        stated_facts=[
            ExtractedFact(
                parameter="matrix", value="a clear transparent solution", input_quote="x"
            ),
            ExtractedFact(
                parameter="measurement_location",
                value="used during surgery in the OP",
                input_quote="y",
            ),
        ],
        assumptions=[],
        unknowns=[],
    )
    findings = rules.evaluate_rules(extraction)
    by_id = {f.rule_id: f.outcome for f in findings}
    assert by_id.get("matrix_clear_liquid_transmission_geometry") == "conditional"
    assert by_id.get("invitro_not_clinical") == "excluded"
    assert all(f.outcome != "approved" for f in findings)


def test_findings_have_source_refs_and_valid_outcomes():
    _require_live_contract()
    from src.models import ExtractedFact, ExtractionResult, RuleFinding

    extraction = ExtractionResult(
        stated_facts=[ExtractedFact(parameter="matrix", value="turbid broth", input_quote="x")],
        assumptions=[],
        unknowns=[],
    )
    findings = rules.evaluate_rules(extraction)
    assert findings, "expected at least one finding"
    for finding in findings:
        assert isinstance(finding, RuleFinding)
        assert finding.source_refs  # contract already enforces min_length=1
        assert finding.outcome in {"excluded", "conditional", "unknown"}
