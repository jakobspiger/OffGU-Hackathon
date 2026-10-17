"""Tests for the T05 few-shot example store + selector (src.knowledge.examples).

Design mirrors the rest of the suite (see tests/conftest.py): the pure-logic
paths (YAML parsing, structural validation, normalization, lexical scoring,
ranking, input validation, the relevance ranking on the real D-texts) run on the
standard library alone, while the paths that build / validate a contract
``FewShotExample`` (pydantic via ``src.models``) are guarded with
``pytest.importorskip``. The full run happens locally on the maintainer's
machine via ``uv run --locked pytest -q``.
"""

from __future__ import annotations

import ast
import inspect
import os
import re

import pytest

from src.knowledge import examples as ex_mod
from src.knowledge.examples import (
    DEFAULT_K,
    EXPECTED_EXAMPLE_IDS,
    IDS_WITH_REFERENCE_ANSWER,
    MAX_K,
    ExampleConfigError,
    _lexical_score,
    _normalize,
    _parse_raw_examples,
    _rank,
    select_examples,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES_PATH = os.path.join(_ROOT, "data", "examples", "dev_examples.yaml")
_MODELS_PATH = os.path.join(_ROOT, "src", "models.py")


def _module_code_without_comments(module) -> str:
    """Return the module source with comments and all string literals removed.

    Docstrings and other string literals (which legitimately *describe* the
    separation from the evidence index) are blanked out so the guard only
    inspects executable code. Pure stdlib (``tokenize``), no pydantic.
    """

    import io
    import tokenize

    src = inspect.getsource(module)
    out: list[str] = []
    readline = io.StringIO(src).readline
    for tok in tokenize.generate_tokens(readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


# ---------------------------------------------------------------------------
# Pure-logic: parse + structural validation (no pydantic).
# ---------------------------------------------------------------------------
def test_examples_load_all_eight_dev_cases() -> None:
    """The file parses to exactly D01-D08, in stable order, no duplicates."""

    raw = _parse_raw_examples(EXAMPLES_PATH)
    ids = [r.example_id for r in raw]
    assert ids == list(EXPECTED_EXAMPLE_IDS)
    assert len(ids) == 8
    assert len(set(ids)) == 8
    # Every case has a non-empty scenario query and provenance.
    for r in raw:
        assert r.query.strip()
        assert r.provenance.strip()


def test_only_d01_d02_have_reference_answers() -> None:
    """Acceptance 1 + 4: only real reference answers; D03-D08 are None."""

    raw = {r.example_id: r for r in _parse_raw_examples(EXAMPLES_PATH)}
    assert IDS_WITH_REFERENCE_ANSWER == frozenset({"D01", "D02"})
    for eid, record in raw.items():
        if eid in ("D01", "D02"):
            assert isinstance(record.reference_answer, str) and record.reference_answer.strip()
        else:
            assert record.reference_answer is None


def test_reference_answers_are_not_cited_as_independent_evidence() -> None:
    """D01/D02 provenance flags them as a development reference, not evidence."""

    raw = {r.example_id: r for r in _parse_raw_examples(EXAMPLES_PATH)}
    for eid in ("D01", "D02"):
        assert "not independent evidence" in raw[eid].provenance.lower()


# ---------------------------------------------------------------------------
# H-exclusion (three ways): file, loader guard, contract regex.
# ---------------------------------------------------------------------------
def test_no_h_ids_in_examples_file() -> None:
    """Acceptance 5: no H0x scenario is used as an example in the data file.

    The file may *mention* H01-H06 in a comment to document the exclusion, but
    no example may carry an H id, and no non-comment line may reference one.
    """

    lines = open(EXAMPLES_PATH, encoding="utf-8").read().splitlines()
    non_comment = [ln for ln in lines if not ln.lstrip().startswith("#")]
    body = "\n".join(non_comment)
    assert not re.search(r"\bH0[1-6]\b", body)
    assert not re.search(r"example_id:\s*H", body)
    # And every parsed id is a D case.
    for r in _parse_raw_examples(EXAMPLES_PATH):
        assert r.example_id.startswith("D")


def test_loader_rejects_non_d_ids(tmp_path) -> None:
    """A file carrying a non-D (e.g. H01) id is rejected on load."""

    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "examples:\n"
        '  - example_id: H01\n'
        '    provenance: "x"\n'
        "    query: |\n"
        "      some text\n"
        "    reference_answer: null\n",
        encoding="utf-8",
    )
    with pytest.raises(ExampleConfigError):
        _parse_raw_examples(str(bad))


def test_loader_rejects_reference_answer_on_non_calibration_case(tmp_path) -> None:
    """D03 carrying a reference_answer is rejected (no invented answers)."""

    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "examples:\n"
        '  - example_id: D03\n'
        '    provenance: "x"\n'
        "    query: |\n"
        "      some text\n"
        "    reference_answer: |\n"
        "      invented answer\n",
        encoding="utf-8",
    )
    with pytest.raises(ExampleConfigError):
        _parse_raw_examples(str(bad))


def test_loader_rejects_duplicate_ids(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "examples:\n"
        '  - example_id: D01\n'
        '    provenance: "x"\n'
        "    query: |\n"
        "      a\n"
        "    reference_answer: |\n"
        "      ans\n"
        '  - example_id: D01\n'
        '    provenance: "x"\n'
        "    query: |\n"
        "      b\n"
        "    reference_answer: |\n"
        "      ans\n",
        encoding="utf-8",
    )
    with pytest.raises(ExampleConfigError):
        _parse_raw_examples(str(bad))


def test_contract_regex_rejects_non_d_ids() -> None:
    """The FewShotExample.example_id regex structurally forbids H0x / D09.

    Read from src/models.py source via ``ast`` so it runs without pydantic.
    """

    tree = ast.parse(open(_MODELS_PATH, encoding="utf-8").read())
    pattern = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "StringConstraints"
        ):
            for kw in node.keywords:
                if kw.arg == "pattern" and isinstance(kw.value, ast.Constant):
                    if kw.value.value == r"^D0[1-8]$":
                        pattern = kw.value.value
    assert pattern == r"^D0[1-8]$", "FewShotExample id regex changed or not found"
    rx = re.compile(pattern)
    for good in EXPECTED_EXAMPLE_IDS:
        assert rx.match(good)
    for bad in ("H01", "H06", "D00", "D09", "d01", "D1", "X01"):
        assert not rx.match(bad)


# ---------------------------------------------------------------------------
# Pure-logic: normalization + lexical scoring.
# ---------------------------------------------------------------------------
def test_normalize_is_case_and_whitespace_robust() -> None:
    assert _normalize("  Petroleum   WATER  ") == "petroleum water"
    # NFC: composed vs decomposed e-acute normalize equal.
    assert _normalize("cafe\u0301") == _normalize("caf\u00e9")


def test_lexical_score_rewards_overlap_and_zero_without() -> None:
    assert _lexical_score("petroleum water", "water in a petroleum stream") > 0.0
    assert _lexical_score("petroleum water", "a dairy fat and protein product") == 0.0
    assert _lexical_score("", "anything") == 0.0


# ---------------------------------------------------------------------------
# Selection input validation.
# ---------------------------------------------------------------------------
def test_select_rejects_bad_input() -> None:
    for bad_query in ("", "   ", None, 123):
        with pytest.raises(ValueError):
            select_examples(bad_query)  # type: ignore[arg-type]
    for bad_k in (0, -1, MAX_K + 1, 1.0, "2"):
        with pytest.raises(ValueError):
            select_examples("petroleum water", bad_k)  # type: ignore[arg-type]
    # bool must be rejected even though bool is an int subclass.
    with pytest.raises(ValueError):
        select_examples("petroleum water", True)  # type: ignore[arg-type]


def test_default_k_is_two_and_documented() -> None:
    assert DEFAULT_K == 2
    assert MAX_K == 8 == len(EXPECTED_EXAMPLE_IDS)


# ---------------------------------------------------------------------------
# Ranking (generic, deterministic) on the REAL D-texts, via _rank + stubs so it
# runs without pydantic.
# ---------------------------------------------------------------------------
def _stub_records():
    """Real parsed D01-D08 as plain records (no pydantic needed)."""

    return _parse_raw_examples(EXAMPLES_PATH)


def test_select_is_deterministic_and_limited() -> None:
    records = _stub_records()
    first = [r.example_id for r in _rank("petroleum water content", records, DEFAULT_K)]
    second = [r.example_id for r in _rank("petroleum water content", records, DEFAULT_K)]
    assert first == second  # deterministic
    assert len(first) == DEFAULT_K == 2  # default limit
    assert len(_rank("petroleum water content", records, MAX_K)) == MAX_K  # bounded


def test_select_ranks_relevant_example_first() -> None:
    """Generic lexical match surfaces the matching scenario first.

    No hardcoded id logic in the engine: the ids below are an emergent result of
    the shared words in the real D-texts.
    """

    records = _stub_records()
    assert _rank("water content in a petroleum stream", records, 1)[0].example_id == "D06"
    assert _rank("opaque dairy fat and protein product", records, 1)[0].example_id == "D02"
    assert _rank("hot polymer extrusion API melt", records, 1)[0].example_id == "D07"
    assert _rank("heterogeneous model tissue MIR fluorescence", records, 1)[0].example_id == "D08"


def test_reference_answer_examples_preferred_on_tie() -> None:
    """On an exact score tie, a record WITH a reference_answer ranks first.

    Generic weighting ("has reference_answer"), not scenario-id branching: two
    otherwise-identical queries, one with and one without a reference answer.
    """

    class _Rec:
        def __init__(self, eid, query, ref):
            self.example_id = eid
            self.query = query
            self.reference_answer = ref

    # Same query text -> identical lexical score; D02 (has ref) must win.
    tie = [
        _Rec("D05", "same words here", None),
        _Rec("D02", "same words here", "a worked answer"),
    ]
    assert _rank("same words here", tie, 1)[0].example_id == "D02"
    # And with no reference answers anywhere, the tie falls back to example_id.
    both_none = [
        _Rec("D05", "same words here", None),
        _Rec("D02", "same words here", None),
    ]
    assert _rank("same words here", both_none, 1)[0].example_id == "D02"


def test_select_never_reads_evidence_index() -> None:
    """Acceptance 2: the selector never touches evidence.jsonl / data/index.

    Checked against the executable code (comments and the module docstring
    stripped), so the docstring may *describe* the separation without tripping
    the guard. The module must not reference the index path, the index-dir
    setting, or import the retriever.
    """

    code = _module_code_without_comments(ex_mod)
    assert "evidence.jsonl" not in code
    assert "afs_index_dir" not in code
    assert os.path.join("data", "index") not in code
    assert "data/index" not in code
    assert "retrieval" not in code  # does not import or call the T04 retriever
    # It reads only the curated examples path.
    assert "dev_examples.yaml" in ex_mod.DEFAULT_EXAMPLES_PATH
    assert os.path.join("data", "examples") in ex_mod.DEFAULT_EXAMPLES_PATH


def test_no_scenario_id_branching_in_engine() -> None:
    """No per-scenario conditionals in the selection/loading code."""

    src = inspect.getsource(ex_mod)
    # No hardcoded scenario-id comparisons like == "D06" or 'if "petroleum"'.
    assert not re.search(r"==\s*[\"']D0[1-8][\"']", src)
    assert not re.search(r"==\s*[\"']H0[1-6][\"']", src)


# ---------------------------------------------------------------------------
# pydantic-dependent paths (guarded): full load + ExampleSelector protocol.
# ---------------------------------------------------------------------------
def test_load_examples_returns_contract_objects() -> None:
    pytest.importorskip("pydantic")
    from src.models import FewShotExample

    loaded = ex_mod.load_examples(EXAMPLES_PATH)
    assert len(loaded) == 8
    assert all(isinstance(e, FewShotExample) for e in loaded)
    by_id = {e.example_id: e for e in loaded}
    assert set(by_id) == set(EXPECTED_EXAMPLE_IDS)
    for eid, e in by_id.items():
        if eid in ("D01", "D02"):
            assert e.reference_answer is not None
        else:
            assert e.reference_answer is None


def test_contract_rejects_non_d_ids_via_pydantic() -> None:
    pytest.importorskip("pydantic")
    from pydantic import ValidationError

    from src.models import FewShotExample

    for bad in ("H01", "D09", "D00"):
        with pytest.raises(ValidationError):
            FewShotExample(example_id=bad, query="x", reference_answer=None, provenance="p")


def test_select_matches_exampleselector_protocol() -> None:
    pytest.importorskip("pydantic")
    from src.contracts import ExampleSelector

    selector: ExampleSelector = select_examples  # structural type check
    result = selector("water content in a petroleum stream", 2)
    from src.models import FewShotExample

    assert len(result) == 2
    assert all(isinstance(e, FewShotExample) for e in result)
    assert result[0].example_id == "D06"
    # Default k path too.
    assert len(selector("opaque dairy fat and protein")) == DEFAULT_K
