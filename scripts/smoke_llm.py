"""Manual smoke test for the T06 extractor against a REAL LLM provider.

This is NOT part of the automated suite: it performs live API calls and costs
tokens. It requires a configured .env (OPENAI_API_KEY + OPENAI_MODEL, optionally
OPENAI_BASE_URL for OpenAI-compatible endpoints) and installed dependencies
(``uv sync --locked``).

Run:
    uv run --locked python -m scripts.smoke_llm

What it checks (grounding guarantees, tolerant to LLM non-determinism):
  * extracted fact values are verbatim spans of the input (verify_quotes passes);
  * supported scalars get a numeric_value, ambiguous ones stay text-only;
  * no invented target_range when the customer gave none;
  * missing parameters land in unknowns;
  * contradictory process states are kept and flagged as a conflict;
  * typographic variants (smart quotes / NFD umlauts) do NOT break verify_quotes.

Exit code is 0 only if every hard assertion holds. Soft observations are printed
but do not fail the run, because exact extraction wording is model-dependent.
"""

import sys
from dataclasses import dataclass
from collections.abc import Callable

from src.config import Settings
from src.engine.extraction import extract
from src.errors import AFSError
from src.models import ExtractionResult


@dataclass
class Check:
    name: str
    query: str
    verify: Callable[[ExtractionResult], list[str]]  # returns list of failure messages


def _params(result: ExtractionResult) -> set[str]:
    return {fact.parameter for fact in result.stated_facts}


def check_basic_grounding(result: ExtractionResult) -> list[str]:
    failures = []
    # Hard: every value must equal its own quote (contract) -- extract() already
    # enforces this, so reaching here means it held; we re-assert defensively.
    for fact in result.stated_facts:
        if fact.value != fact.input_quote:
            failures.append(f"value != input_quote for {fact.parameter!r}")
    # Hard: no invented range when the prompt names only a quantity.
    if any(fact.parameter == "target_range" for fact in result.stated_facts):
        failures.append("invented a target_range that was never stated")
    # Soft-ish: a temperature of '80 °C' should parse to a scalar.
    temps = [f for f in result.stated_facts if f.parameter == "temperature"]
    if temps and all(f.numeric_value is None for f in temps):
        failures.append("temperature '80 °C' present but no numeric_value parsed")
    # Hard: a parameter the text never mentions must be in unknowns.
    if "required_accuracy" not in result.unknowns:
        failures.append("required_accuracy was not reported as unknown")
    return failures


def check_no_invented_numbers(result: ExtractionResult) -> list[str]:
    failures = []
    # The text gives a quantity but NO numeric accuracy/range -> none may appear.
    for fact in result.stated_facts:
        if fact.parameter in ("target_range", "required_accuracy") and fact.numeric_value:
            failures.append(f"invented numeric_value for {fact.parameter!r}: {fact.value!r}")
    return failures


def check_contradiction_is_flagged(result: ExtractionResult) -> list[str]:
    failures = []
    temps = [f for f in result.stated_facts if f.parameter == "temperature"]
    if len(temps) < 2:
        failures.append(
            f"expected both temperature statements to be kept as separate facts (got {len(temps)})"
        )
    if not any(c.parameter == "temperature" for c in result.conflicts):
        failures.append("contradictory temperatures were not flagged as a conflict")
    if "temperature" not in result.unknowns:
        failures.append("contradictory temperature not surfaced in unknowns")
    return failures


def check_typography_does_not_break(result: ExtractionResult) -> list[str]:
    # Reaching here at all means verify_quotes accepted the quotes despite smart
    # quotes / NFD umlauts. Empty extraction is acceptable; a crash is not (and
    # would have raised before this function runs).
    return []


CHECKS = [
    Check(
        name="basic grounding (powder / 80 °C / moisture)",
        query="Pulver nach dem Trockner; Temperatur 80 °C; Feuchtigkeit messen.",
        verify=check_basic_grounding,
    ),
    Check(
        name="no invented numbers (quantity without range/accuracy)",
        query="Wir wollen die Konzentration bestimmen. Genauigkeit ist uns wichtig.",
        verify=check_no_invented_numbers,
    ),
    Check(
        name="contradiction kept and flagged",
        query="Die Probe ist vorher 20 °C, nachher 80 °C.",
        verify=check_contradiction_is_flagged,
    ),
    Check(
        name="typographic variants do not break verify_quotes",
        # smart quotes + NFD-decomposed umlaut ('u' + combining diaeresis)
        query="Der Kunde nennt \u201eMilchkonzentrat\u201c und misst fu\u0308r die Qualita\u0308t.",
        verify=check_typography_does_not_break,
    ),
]


def main() -> int:
    # Fail fast with a clear message if the environment is not configured.
    try:
        Settings().require_llm()
    except AFSError as error:
        print(f"Configuration incomplete: {error}", file=sys.stderr)
        print(
            "Set OPENAI_API_KEY and OPENAI_MODEL in .env (see .env.example), "
            "then run: uv run --locked python -m scripts.smoke_llm",
            file=sys.stderr,
        )
        return 2

    total_failures = 0
    for check in CHECKS:
        print(f"\n=== {check.name} ===")
        print(f"query: {check.query}")
        try:
            result = extract(check.query)
        except AFSError as error:
            # Sanitized error only; no secrets or raw bodies by contract.
            print(f"  LLM/extraction FAILED: {error}")
            total_failures += 1
            continue

        facts_summary = ", ".join(
            f"{f.parameter}={f.value!r}"
            + (f" [{f.numeric_value.magnitude} {f.numeric_value.unit}]" if f.numeric_value else "")
            for f in result.stated_facts
        )
        conflicts_summary = [(c.parameter, c.fact_indices) for c in result.conflicts]
        print(f"  facts: {facts_summary or '(none)'}")
        print(f"  conflicts: {conflicts_summary or '(none)'}")
        print(f"  unknowns ({len(result.unknowns)}): {', '.join(result.unknowns)}")

        failures = check.verify(result)
        if failures:
            total_failures += len(failures)
            for message in failures:
                print(f"  FAIL: {message}")
        else:
            print("  OK")

    print("\n" + "=" * 60)
    if total_failures:
        print(f"SMOKE TEST FAILED: {total_failures} assertion(s) did not hold.")
        return 1
    print("SMOKE TEST PASSED: all grounding guarantees held on live output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
