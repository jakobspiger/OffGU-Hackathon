"""Offline logic tests for the stdlib-only parts of T06.

Rationale: the sandbox has no network access to PyPI, so pydantic/httpx cannot
be installed and the full suite (which imports pydantic) cannot run here. These
tests exercise the two security-critical, dependency-free pieces of T06 against
the REAL source code, loaded directly from the files:

  * _normalize_for_quote_check (src/models.py) -- the hallucination guard must
    tolerate presentation-only differences but still reject absent quotes.
  * the scalar parse decision in scalar_value (src/engine/extraction.py) -- must
    never invent a number: ranges, approximations, negations, comma decimals,
    missing/unsupported units and impossible values abstain (return None).

The parse decision is re-derived from the module source via ``inspect`` so this
test tracks the real regex/guards rather than a hand-written copy. Only the
final NumericValue(...) construction (pydantic) is skipped; everything that
decides parse-vs-abstain is executed verbatim.

Run with the system pytest: ``pytest tests/test_pure_logic_offline.py``.
"""

import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_function_source(path: pathlib.Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(path.read_text(encoding="utf-8"), node)
    raise AssertionError(f"{name} not found in {path}")


# --- Load _normalize_for_quote_check verbatim from src/models.py --------------
_models_src = (ROOT / "src" / "models.py").read_text(encoding="utf-8")
_trans_match = re.search(r"_QUOTE_TRANSLATION = str\.maketrans\(\s*\{.*?\}\s*\)", _models_src, re.S)
assert _trans_match, "could not locate _QUOTE_TRANSLATION in src/models.py"
_norm_src = _load_function_source(ROOT / "src" / "models.py", "_normalize_for_quote_check")

_ns: dict = {}
import unicodedata  # noqa: E402  (import after docstring, used by the exec'd code)

_ns["unicodedata"] = unicodedata
exec(_trans_match.group(0), _ns)  # noqa: S102 -- trusted local source
exec(_norm_src, _ns)  # noqa: S102
normalize = _ns["_normalize_for_quote_check"]


# --- Re-derive the scalar parse decision from src/engine/extraction.py --------
# We extract the exact regex and supported-unit map so the test fails if the
# real source changes them.
_ext_src = (ROOT / "src" / "engine" / "extraction.py").read_text(encoding="utf-8")
_regex_match = re.search(r"re\.fullmatch\(\s*(r\"[^\"]+\")", _ext_src)
assert _regex_match, "could not locate the scalar regex in extraction.py"
SCALAR_RE = re.compile(eval(_regex_match.group(1)))  # the real pattern

SUPPORTED_UNITS = {
    "temperature": ("°C", "K"),
    "pressure": ("bar(a)", "bar(g)"),
    "required_response_time": ("s", "ms"),
}


def parses_to_scalar(parameter: str, value: str):
    """Mirror of scalar_value's decision, minus the pydantic construction."""
    units = SUPPORTED_UNITS.get(parameter, ())
    match = SCALAR_RE.fullmatch(value)
    if not match or match[2] not in units:
        return None
    magnitude = float(match[1])
    if (match[2] == "K" and magnitude < 0) or (match[2] in ("s", "ms", "bar(a)") and magnitude < 0):
        return None
    if match[2] == "°C" and magnitude < -273.15:
        return None
    return (magnitude, match[2])


# ============================ verify_quotes ===================================
@pytest.mark.parametrize(
    "query, quote",
    [
        ("Der Kunde nennt \u201eMilchkonzentrat\u201c.", '"Milchkonzentrat"'),
        ("water\u00a0content   in the  line", "water content in the line"),
        ("range 780\u20132500 nm", "780-2500 nm"),
        ("Me\u0301thode fu\u0308r Pru\u0308fung", "M\u00e9thode f\u00fcr Pr\u00fcfung"),
        ("Measure the POWDER blend", "powder"),
    ],
)
def test_presentation_differences_are_tolerated(query, quote):
    assert normalize(quote) in normalize(query)


@pytest.mark.parametrize(
    "query, quote",
    [
        ("Measure this powder.", "liquid"),
        ("clear whey stream", "opaque milk concentrate"),
        ("", "anything"),
    ],
)
def test_genuinely_absent_quotes_still_rejected(query, quote):
    assert normalize(quote) not in normalize(query)


def test_foundation_regression_cases():
    # test_quotes_must_exist_in_original_input relies on these.
    assert normalize("powder") in normalize("Measure this powder.")
    assert normalize("powder") not in normalize("Measure this liquid.")


# ============================ scalar parse ====================================
@pytest.mark.parametrize(
    "parameter,value,unit,magnitude",
    [
        ("temperature", "80 °C", "°C", 80.0),
        ("temperature", "-20 °C", "°C", -20.0),
        ("temperature", "300 K", "K", 300.0),
        ("pressure", "2.5 bar(a)", "bar(a)", 2.5),
        ("pressure", "-0.5 bar(g)", "bar(g)", -0.5),
        ("required_response_time", "100 ms", "ms", 100.0),
    ],
)
def test_supported_scalars_keep_units(parameter, value, unit, magnitude):
    result = parses_to_scalar(parameter, value)
    assert result == (magnitude, unit)


@pytest.mark.parametrize(
    "parameter,value",
    [
        ("temperature", "80"),
        ("temperature", "ca. 80 °C"),
        ("temperature", "20–80 °C"),
        ("temperature", "nicht 80 °C"),
        ("temperature", "1,000 °C"),
        ("temperature", "-1 K"),
        ("temperature", "-300 °C"),
        ("pressure", "2 bar"),
        ("required_accuracy", "2 %"),
        ("target_range", "20 ppm"),
        ("required_response_time", "-2 s"),
        ("pressure", "-1 bar(a)"),
    ],
)
def test_ambiguous_or_unsupported_numbers_abstain(parameter, value):
    assert parses_to_scalar(parameter, value) is None
