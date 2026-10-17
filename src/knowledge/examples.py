"""T05 - curated few-shot development examples D01-D08 and their selection.

This module exposes two things to the rest of the system:

* :func:`load_examples` - read ``data/examples/dev_examples.yaml`` and return the
  eight curated development scenarios as contract :class:`~src.models.FewShotExample`
  objects, validated on load.
* :func:`select_examples` - the shared :class:`src.contracts.ExampleSelector`
  adapter: ``select_examples(query, k=2) -> list[FewShotExample]``. It ranks the
  curated examples by a **generic**, deterministic lexical score against the
  caller's query and returns the top ``k``.

Design notes
------------
* **Generic, no scenario-id branching.** Nothing in this module knows about any
  specific scenario id, customer name or application. The selector only sees
  ``example.query`` text and a boolean "has a reference_answer". The relevance
  of e.g. a petroleum query to D06 is an emergent property of the shared words,
  not a hardcoded rule.
* **Separate from citable evidence.** These examples are a tone/structure
  calibration store. The selector reads ONLY ``data/examples/dev_examples.yaml``;
  it never reads ``data/index/evidence.jsonl`` and the examples are never emitted
  as retrieval evidence. The D01/D02 worked answers are a development reference,
  not independent proof of any method's performance.
* **Only real reference answers.** Exactly D01 and D02 carry a worked
  ``reference_answer`` (verbatim from the DOCX). D03-D08 carry ``None``; no
  answer is invented for them. ``load_examples`` enforces this.
* **H01-H06 excluded three ways.** The contract regex ``^D0[1-8]$`` on
  ``FewShotExample.example_id`` (src.models), this data file containing only
  D01-D08, and a test forbidding any ``H0x`` string.

Sandbox note
------------
Only building the contract :class:`~src.models.FewShotExample` needs pydantic
(via ``src.models``). Everything else - YAML parsing (with a stdlib fallback,
same approach as :mod:`src.knowledge.rules`), unicode normalization, lexical
scoring, input validation and the ranking/limit logic - is pure stdlib and is
testable without pydantic or PyYAML.
"""

from __future__ import annotations

import os
import unicodedata
from typing import TYPE_CHECKING, Any

from src.errors import AFSError

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a hard pydantic import
    from src.models import FewShotExample

# Default location of the curated examples file.
DEFAULT_EXAMPLES_PATH = os.path.join("data", "examples", "dev_examples.yaml")

# The eight development case ids, verbatim. Used as a structural guard: the file
# must contain exactly these, with no duplicates and no other (e.g. H0x) ids.
EXPECTED_EXAMPLE_IDS: tuple[str, ...] = ("D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08")

# Only these development cases have a worked reference answer in the DOCX
# (section 2). Every other case must have reference_answer = None; no answer is
# invented. This mirrors the "only real reference answers" acceptance criterion.
IDS_WITH_REFERENCE_ANSWER: frozenset[str] = frozenset({"D01", "D02"})

# Selection limit: default 2, valid range 1..8 (8 = number of development cases).
# Documented and bounded on purpose (acceptance criterion: selection count is
# limited and documented).
DEFAULT_K = 2
MAX_K = len(EXPECTED_EXAMPLE_IDS)


class ExampleConfigError(AFSError):
    """The curated examples file is inconsistent with the T05 contract.

    Defined locally (a subclass of :class:`src.errors.AFSError`) on purpose,
    mirroring :class:`src.knowledge.rules.RuleConfigError`: T05 does not extend
    ``src/errors.py`` (T01's file). If T01 later wants a central class, this can
    be aligned.
    """


# ---------------------------------------------------------------------------
# Plain record type (no pydantic needed to parse/score/select).
# ---------------------------------------------------------------------------
class _RawExample:
    """A parsed example before it becomes a contract FewShotExample.

    Kept as a tiny stdlib object so the parsing, scoring and selection logic can
    be exercised in the sandbox without pydantic.
    """

    __slots__ = ("example_id", "query", "reference_answer", "provenance")

    def __init__(
        self,
        example_id: str,
        query: str,
        reference_answer: str | None,
        provenance: str,
    ) -> None:
        self.example_id = example_id
        self.query = query
        self.reference_answer = reference_answer
        self.provenance = provenance


# ---------------------------------------------------------------------------
# YAML loading - PyYAML if present, otherwise a minimal stdlib fallback for the
# specific structure of data/examples/dev_examples.yaml (same approach as
# src.knowledge.rules / src.knowledge.ingest). The fallback supports a top-level
# ``examples:`` list of mappings whose values are inline scalars or block
# literal (``|``) scalars.
# ---------------------------------------------------------------------------
def _load_yaml(raw: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(raw) or {}
    except ModuleNotFoundError:
        return _fallback_parse(raw)


def _is_blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _scalar(token: str) -> Any:
    token = token.strip()
    if not token:
        return None
    if token in ("null", "~", "Null", "NULL"):
        return None
    if (len(token) >= 2) and token[0] == token[-1] and token[0] in "\"'":
        return _unquote(token)
    return token


def _unquote(token: str) -> str:
    quote = token[0]
    body = token[1:-1]
    if quote == '"':
        return body.replace('\\"', '"').replace("\\\\", "\\")
    return body.replace("''", "'")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _fallback_parse(raw: str) -> dict[str, Any]:
    """Parse the limited YAML subset used by dev_examples.yaml without PyYAML.

    Grammar handled:
      examples:
        - example_id: D01
          provenance: "..."
          query: |
            multi-line block literal ...
          reference_answer: |
            multi-line block literal ...
      (reference_answer may instead be ``null`` as an inline scalar.)

    Good enough to run the pure-logic tests offline; production uses PyYAML via
    uv.lock.
    """

    lines = raw.splitlines()
    i = 0
    n = len(lines)

    # Skip to the top-level ``examples:`` key.
    while i < n and not lines[i].strip().startswith("examples:"):
        i += 1
    if i >= n:
        return {}
    list_indent_seen: int | None = None
    i += 1

    examples: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    while i < n:
        line = lines[i]
        if _is_blank_or_comment(line):
            i += 1
            continue
        indent = _indent(line)
        stripped = line.strip()

        if stripped.startswith("- "):
            # New list item: "- key: value".
            list_indent_seen = indent
            current = {}
            examples.append(current)
            key, rest, i = _parse_key_value(lines, i, indent + 2, stripped[2:].strip())
            current[key] = rest
            continue

        if current is not None and (list_indent_seen is not None and indent > list_indent_seen):
            key, value, i = _parse_key_value(lines, i, indent, stripped)
            current[key] = value
            continue

        # Dedent out of the list: stop.
        break

    return {"examples": examples}


def _parse_key_value(
    lines: list[str], i: int, child_indent: int, stripped: str
) -> tuple[str, Any, int]:
    """Parse a single ``key: value`` (inline scalar or block literal ``|``)."""

    if ":" not in stripped:
        raise ExampleConfigError(f"Malformed example line (expected 'key: value'): {stripped!r}.")
    key, token = stripped.split(":", 1)
    key = key.strip()
    token = token.strip()
    i += 1

    if token in ("|", "|-", "|+", ">", ">-", ">+"):
        folded = token[0] == ">"
        block, i = _read_block_scalar(lines, i, child_indent)
        return key, _finish_block(block, folded, token), i

    return key, _scalar(token), i


def _read_block_scalar(lines: list[str], i: int, child_indent: int) -> tuple[list[str], int]:
    """Collect the indented body lines of a block scalar.

    The block runs while lines are blank or indented at least to the first
    non-blank body line's indentation. Leading indentation is stripped relative
    to that first body line.
    """

    n = len(lines)
    body: list[str] = []
    base_indent: int | None = None
    while i < n:
        line = lines[i]
        if not line.strip():
            body.append("")
            i += 1
            continue
        indent = _indent(line)
        if base_indent is None:
            if indent < child_indent:
                break
            base_indent = indent
        if indent < base_indent:
            break
        body.append(line[base_indent:])
        i += 1
    # Trim trailing blank lines captured before the next key.
    while body and body[-1] == "":
        body.pop()
    return body, i


def _finish_block(body: list[str], folded: bool, token: str) -> str:
    if folded:
        # Folded (``>``): blank lines separate paragraphs, single newlines fold
        # to spaces. Not used by dev_examples.yaml but handled for robustness.
        text = "\n".join(body)
        paragraphs = [" ".join(p.split("\n")) for p in text.split("\n\n")]
        result = "\n\n".join(paragraphs)
    else:
        result = "\n".join(body)
    if token.endswith("+"):
        return result + "\n"
    if token.endswith("-"):
        return result
    return (result + "\n") if result else result


# ---------------------------------------------------------------------------
# Loading + validation.
# ---------------------------------------------------------------------------
def _parse_raw_examples(path: str) -> list[_RawExample]:
    """Read + structurally validate the file into plain ``_RawExample`` records.

    Pure stdlib (no pydantic). Enforces: exactly D01-D08, no duplicates, no
    other (e.g. H0x) ids, reference_answer only for D01/D02, non-empty
    provenance and query.
    """

    if not os.path.isfile(path):
        raise ExampleConfigError(f"Missing examples file: {path}.")
    with open(path, encoding="utf-8") as fh:
        data = _load_yaml(fh.read())

    raw_list = data.get("examples") if isinstance(data, dict) else None
    if not isinstance(raw_list, list) or not raw_list:
        raise ExampleConfigError("examples file must contain a non-empty 'examples' list.")

    parsed: list[_RawExample] = []
    seen: set[str] = set()
    for entry in raw_list:
        if not isinstance(entry, dict):
            raise ExampleConfigError("Each example must be a mapping.")
        example_id = str(entry.get("example_id", "")).strip()
        query = entry.get("query")
        provenance = entry.get("provenance")
        reference_answer = entry.get("reference_answer")

        if example_id not in EXPECTED_EXAMPLE_IDS:
            raise ExampleConfigError(
                f"Unexpected example_id {example_id!r}; allowed ids are exactly "
                f"{list(EXPECTED_EXAMPLE_IDS)} (H0x and any other id are forbidden)."
            )
        if example_id in seen:
            raise ExampleConfigError(f"Duplicate example_id {example_id!r}.")
        seen.add(example_id)

        if not isinstance(query, str) or not query.strip():
            raise ExampleConfigError(f"Example {example_id!r} needs a non-empty query.")
        if not isinstance(provenance, str) or not provenance.strip():
            raise ExampleConfigError(f"Example {example_id!r} needs a non-empty provenance.")

        if isinstance(reference_answer, str):
            reference_answer = reference_answer.strip() or None
        elif reference_answer is not None:
            raise ExampleConfigError(
                f"Example {example_id!r} reference_answer must be text or null."
            )

        has_reference = reference_answer is not None
        should_have = example_id in IDS_WITH_REFERENCE_ANSWER
        if has_reference and not should_have:
            raise ExampleConfigError(
                f"Example {example_id!r} carries a reference_answer, but only "
                f"{sorted(IDS_WITH_REFERENCE_ANSWER)} have a worked answer in the source."
            )
        if should_have and not has_reference:
            raise ExampleConfigError(
                f"Example {example_id!r} must carry its worked reference_answer."
            )

        parsed.append(
            _RawExample(
                example_id=example_id,
                query=query.strip(),
                reference_answer=reference_answer,
                provenance=provenance.strip(),
            )
        )

    missing = [eid for eid in EXPECTED_EXAMPLE_IDS if eid not in seen]
    if missing:
        raise ExampleConfigError(f"examples file is missing ids: {missing}.")

    # Deterministic order by example_id (D01..D08).
    parsed.sort(key=lambda ex: ex.example_id)
    return parsed


def load_examples(
    path: str | os.PathLike[str] = DEFAULT_EXAMPLES_PATH,
) -> list[FewShotExample]:
    """Load and validate the curated development examples (contract objects).

    Returns the eight :class:`~src.models.FewShotExample` objects in stable
    ``example_id`` order. Raises :class:`ExampleConfigError` on any structural
    inconsistency (wrong/duplicate/forbidden ids, missing fields, a
    reference_answer where the source has none, etc.).

    Building the contract object is the only pydantic-dependent step; the parse
    and validation above run on stdlib alone.
    """

    from src.models import FewShotExample

    raw = _parse_raw_examples(os.fspath(path))
    return [
        FewShotExample(
            example_id=ex.example_id,
            query=ex.query,
            reference_answer=ex.reference_answer,
            provenance=ex.provenance,
        )
        for ex in raw
    ]


# ---------------------------------------------------------------------------
# Pure-logic scoring helpers (stdlib only; no pydantic / PyYAML). Own copy on
# purpose (kept decoupled from src.knowledge.retrieval) - duplication is a
# deliberate, documented choice to keep the example store independent of the
# evidence index.
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    """NFC + casefold + whitespace-collapse.

    Deterministic and case/unicode robust so lexical scoring is stable across
    presentation differences without stemming or synonyms.
    """

    normalized = unicodedata.normalize("NFC", text)
    return " ".join(normalized.split()).casefold()


def _tokenize(text: str) -> list[str]:
    """Split normalized text into alphanumeric tokens (non-alnum is a boundary)."""

    tokens: list[str] = []
    current: list[str] = []
    for char in _normalize(text):
        if char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _lexical_score(query: str, text: str) -> float:
    """Deterministic lexical relevance of ``text`` for ``query``.

    Token-overlap with term-frequency weighting, length-normalized so long
    passages do not win on size alone. Returns 0.0 when there is no overlap.
    Same normalization idea as the T04 retriever, but an independent copy.
    """

    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    text_tokens = _tokenize(text)
    if not text_tokens:
        return 0.0

    counts: dict[str, int] = {}
    for token in text_tokens:
        counts[token] = counts.get(token, 0) + 1

    unique_query = set(query_tokens)
    matched_terms = 0
    total_hits = 0
    for term in unique_query:
        hits = counts.get(term, 0)
        if hits:
            matched_terms += 1
            total_hits += hits

    if matched_terms == 0:
        return 0.0

    coverage = matched_terms / len(unique_query)
    frequency_bonus = total_hits / (total_hits + len(text_tokens))
    return coverage + 0.25 * frequency_bonus


# Small, generic tie-break bonus for examples that carry a reference_answer
# (D01/D02 = the tone/structure calibration template). Strictly smaller than the
# smallest meaningful lexical difference so it only ever breaks exact ties; it
# never lets a less relevant example outrank a more relevant one.
_REFERENCE_ANSWER_TIE_BONUS = 1e-9


def _rank(
    query: str,
    records: list[Any],
    k: int,
) -> list[Any]:
    """Score, order and return the top ``k`` records (generic, deterministic).

    Base score is :func:`_lexical_score` over ``record.query``. Ties are broken
    by a tiny generic bonus for records that HAVE a ``reference_answer`` (the
    calibration examples), then by ``example_id`` ascending. Works on any object
    exposing ``query``, ``reference_answer`` and ``example_id`` (model or stub).
    """

    scored: list[tuple[float, str, Any]] = []
    for record in records:
        base = _lexical_score(query, _get(record, "query") or "")
        has_reference = _get(record, "reference_answer") is not None
        final = base + (_REFERENCE_ANSWER_TIE_BONUS if has_reference else 0.0)
        scored.append((final, str(_get(record, "example_id")), record))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [record for _, _, record in scored[:k]]


def _get(record: Any, field: str) -> Any:
    """Read ``field`` from a FewShotExample / _RawExample / dict (test stub)."""

    if isinstance(record, dict):
        return record.get(field)
    return getattr(record, field, None)


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------
def select_examples(query: str, k: int = DEFAULT_K) -> list[FewShotExample]:
    """Return the top-``k`` development examples most relevant to ``query``.

    Matches :class:`src.contracts.ExampleSelector` exactly:
    ``(query: str, k: int = 2) -> list[FewShotExample]``.

    Input validation: ``query`` must be a non-empty string; ``k`` must be an
    ``int`` (``bool`` is rejected) in ``1..8`` (8 = number of development
    cases). Otherwise ``ValueError``.

    Ranking is **generic** and deterministic: lexical relevance of ``query``
    against each example's own ``query`` text, ties broken slightly in favour of
    examples that carry a ``reference_answer`` (D01/D02) and then by
    ``example_id``. No scenario-id branching. The examples come only from the
    curated store; ``data/index/evidence.jsonl`` is never read here.
    """

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")
    if type(k) is not int or not 1 <= k <= MAX_K:
        raise ValueError(f"k must be an integer between 1 and {MAX_K}.")

    examples = load_examples()
    return _rank(query, examples, k)


__all__ = [
    "DEFAULT_EXAMPLES_PATH",
    "EXPECTED_EXAMPLE_IDS",
    "IDS_WITH_REFERENCE_ANSWER",
    "DEFAULT_K",
    "MAX_K",
    "ExampleConfigError",
    "load_examples",
    "select_examples",
]
