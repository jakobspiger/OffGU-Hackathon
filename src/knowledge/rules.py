"""T03 - deterministic rule matrix.

A **generic** rule engine: declarative rules live in ``data/rules/*.yaml`` and
are evaluated against an :class:`~src.models.ExtractionResult`. There is no
scenario-id branching anywhere (no ``H0x`` / ``D0x``, no customer names, no
scenario-specific conditionals); the engine only knows ``ParameterName`` keys,
quote text and three outcomes (``excluded`` / ``conditional`` / ``unknown``).

Design notes
------------
* **Pure logic needs no third-party library.** The rule datatypes are plain
  stdlib dataclasses, YAML is parsed with a PyYAML fallback (same approach as
  ``src.knowledge.ingest``), and the parameter-version gate reads
  ``typing.get_args(src.models.ParameterName)`` lazily. Only building a
  contract :class:`~src.models.RuleFinding` needs pydantic (via ``src.models``),
  so that single step is the only one that requires the full environment.
* **Parameter-version gate (T03 steering core).** ``load_rules`` verifies that
  ``rules_meta.yaml``'s ``expected_parameter_names`` equals the live
  ``ParameterName`` set and raises :class:`RuleConfigError` otherwise, so rules
  can never match silently against a drifted parameter list.
* **Missing data never clears.** ``evaluate_rules`` checks a rule's ``requires``
  first: any required parameter that is missing (or disputed via the optional
  T06 ``conflicts`` field) yields ``outcome="unknown"``, never a positive result.
* **No numeric interpretation.** Conditions match on the raw quote text
  (``value``) with keyword / presence predicates, case-insensitively. T06's
  additive ``numeric_value`` / ``conflicts`` fields are read getattr-safely and
  are never required.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, get_args

from src.errors import AFSError

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a hard pydantic import
    from src.models import ExtractionResult, RuleFinding

# Outcomes mirror src.models.RuleFinding.outcome exactly. There is deliberately
# no "approved": a missing required parameter becomes "unknown", never a go.
Outcome = Literal["excluded", "conditional", "unknown"]
VALID_OUTCOMES: frozenset[str] = frozenset({"excluded", "conditional", "unknown"})

Predicate = Literal["value_contains_any", "parameter_present", "parameter_absent"]
VALID_PREDICATES: frozenset[str] = frozenset(
    {"value_contains_any", "parameter_present", "parameter_absent"}
)

# Default location of the declarative rule files.
DEFAULT_RULES_DIR = os.path.join("data", "rules")
_META_FILE = "rules_meta.yaml"
_RULE_FILES = ("method_matrix.yaml", "compatibility_rules.yaml")


class RuleConfigError(AFSError):
    """A rule file is inconsistent with the contract (e.g. parameter drift).

    Defined locally (a subclass of :class:`src.errors.AFSError`) on purpose:
    T03 does not extend ``src/errors.py`` (T01's file). If T01 later wants a
    central class, this can be aligned.
    """


# ---------------------------------------------------------------------------
# Rule datatypes - plain stdlib dataclasses (no pydantic needed for loading).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RuleCondition:
    parameter: str
    predicate: str
    keywords: tuple[str, ...] = ()
    negate: bool = False


@dataclass(frozen=True)
class RuleSource:
    """A parsed source reference (validated against the catalog on load)."""

    source_id: str
    page: int | None = None


@dataclass(frozen=True)
class Rule:
    rule_id: str
    when: tuple[RuleCondition, ...]
    requires: tuple[str, ...]
    outcome: str
    reason: str
    source_refs: tuple[RuleSource, ...]


@dataclass(frozen=True)
class RulesMeta:
    rule_set_version: str
    parameter_contract: str
    expected_parameter_names: tuple[str, ...]


@dataclass(frozen=True)
class RuleSet:
    meta: RulesMeta
    rules: tuple[Rule, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# YAML loading - PyYAML if present, otherwise a minimal stdlib fallback for the
# specific structure of the T03 rule files (same approach as ingest.py).
# ---------------------------------------------------------------------------
def _load_yaml(raw: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(raw) or {}
    except ModuleNotFoundError:
        return _fallback_parse(raw)


def _strip_comment(line: str) -> str:
    """Drop a trailing ``#`` comment that is not inside quotes."""

    in_single = in_double = False
    for idx, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:idx]
    return line


def _scalar(token: str) -> Any:
    token = token.strip()
    if not token:
        return None
    if (token[0] == token[-1]) and token[0] in "\"'" and len(token) >= 2:
        return token[1:-1]
    if token in ("true", "True"):
        return True
    if token in ("false", "False"):
        return False
    if token in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    return token


def _inline_list(token: str) -> list[Any]:
    inner = token.strip()[1:-1].strip()
    if not inner:
        return []
    return [_scalar(part) for part in _split_top_level(inner)]


def _split_top_level(inner: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    in_single = in_double = False
    buf: list[str] = []
    for ch in inner:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == "[" and not in_single and not in_double:
            depth += 1
        elif ch == "]" and not in_single and not in_double:
            depth -= 1
        if ch == "," and depth == 0 and not in_single and not in_double:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts]


@dataclass
class _Line:
    indent: int
    content: str

    @property
    def is_item(self) -> bool:
        return self.content.startswith("- ") or self.content == "-"


def _prepare_lines(raw: str) -> list[_Line]:
    """Strip comments/blanks and fold ``>-`` block scalars into single lines.

    A list-item mapping key ("- key:") is normalised to two logical lines: the
    bare "-" marker at the item indent and the "key:" at indent+2. That keeps
    the recursive parser uniform (every mapping sits at its own indent).
    """

    rows = raw.splitlines()
    out: list[_Line] = []
    i = 0
    n = len(rows)
    while i < n:
        row = _strip_comment(rows[i])
        if not row.strip():
            i += 1
            continue
        indent = len(row) - len(row.lstrip(" "))
        content = row.strip()

        folded = re.match(r"^(-\s+)?([\w-]+):\s*>[-+]?\s*$", content)
        if folded:
            key = folded.group(2)
            had_dash = bool(folded.group(1))
            i += 1
            parts: list[str] = []
            while i < n:
                nxt = rows[i]
                if not nxt.strip():
                    i += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if nxt_indent <= indent:
                    break
                parts.append(nxt.strip())
                i += 1
            joined = " ".join(parts)
            content = f"- {key}: ::FOLDED::" if had_dash else f"{key}: ::FOLDED::"
            _emit(out, indent, content, folded_value=joined)
            continue

        _emit(out, indent, content)
        i += 1
    return out


def _emit(out: list[_Line], indent: int, content: str, folded_value: str | None = None) -> None:
    if content.startswith("- ") and content != "-":
        body = content[2:].strip()
        if folded_value is None and ":" not in body:
            # Bare scalar list item, e.g. "- matrix": keep it on one line.
            out.append(_Line(indent=indent, content=f"- {body}"))
            return
        # Split "- key: val" into a bare item marker + the mapping key beneath.
        out.append(_Line(indent=indent, content="-"))
        inner_indent = indent + 2
        if folded_value is not None:
            key = body.split(":", 1)[0].strip()
            out.append(_Line(indent=inner_indent, content=f"{key}: {_quote(folded_value)}"))
        else:
            out.append(_Line(indent=inner_indent, content=body))
    elif folded_value is not None:
        key = content.split(":", 1)[0].strip()
        out.append(_Line(indent=indent, content=f"{key}: {_quote(folded_value)}"))
    else:
        out.append(_Line(indent=indent, content=content))


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _fallback_parse(raw: str) -> dict[str, Any]:
    """Parse the limited YAML subset used by the T03 rule files.

    Supports top-level scalar keys, top-level lists, nested mappings and lists,
    list items that are mappings (``rules`` / ``when`` / ``source_refs``),
    inline ``[a, b]`` lists and folded ``>-`` block scalars. Good enough to run
    the pure-logic tests without PyYAML; production uses PyYAML via uv.lock.
    """

    lines = _prepare_lines(raw)
    value, _ = _parse_block(lines, 0, 0)
    return value if isinstance(value, dict) else {"_": value}


def _parse_block(lines: list[_Line], start: int, indent: int) -> tuple[Any, int]:
    if start >= len(lines):
        return {}, start
    if lines[start].is_item:
        return _parse_list(lines, start, indent)
    return _parse_map(lines, start, indent)


def _parse_list(lines: list[_Line], start: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    i = start
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.indent != indent or not line.is_item:
            break
        if line.content != "-":
            # Scalar item kept inline: "- value".
            items.append(_scalar(line.content[2:].strip()))
            i += 1
            continue
        i += 1
        # The item body is the block indented deeper than the marker.
        if i < n and lines[i].indent > indent:
            value, i = _parse_block(lines, i, lines[i].indent)
            items.append(value)
        else:
            items.append(None)
    return items, i


def _parse_map(lines: list[_Line], start: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    i = start
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.is_item or line.indent < indent:
            break
        if line.indent > indent:
            i += 1
            continue
        km = re.match(r"^([\w-]+):\s*(.*)$", line.content)
        if not km:
            i += 1
            continue
        key, token = km.group(1), km.group(2).strip()
        if token.startswith("[") and token.endswith("]"):
            result[key] = _inline_list(token)
            i += 1
        elif token != "":
            result[key] = _scalar(token)
            i += 1
        else:
            # Nested block on the following deeper-indented lines.
            i += 1
            if i < n and lines[i].indent > indent:
                child, i = _parse_block(lines, i, lines[i].indent)
                result[key] = child
            else:
                result[key] = {}
    return result, i


# ---------------------------------------------------------------------------
# Parsing parsed-dict -> dataclasses.
# ---------------------------------------------------------------------------
def _parse_condition(data: dict[str, Any]) -> RuleCondition:
    predicate = str(data.get("predicate", "")).strip()
    if predicate not in VALID_PREDICATES:
        raise RuleConfigError(
            f"Unknown predicate {predicate!r}; allowed: {sorted(VALID_PREDICATES)}."
        )
    keywords = tuple(str(k) for k in (data.get("keywords") or []))
    if predicate == "value_contains_any" and not keywords:
        raise RuleConfigError("predicate value_contains_any requires non-empty keywords.")
    return RuleCondition(
        parameter=str(data.get("parameter", "")).strip(),
        predicate=predicate,
        keywords=keywords,
        negate=bool(data.get("negate", False)),
    )


def _parse_source(data: dict[str, Any]) -> RuleSource:
    page = data.get("page")
    return RuleSource(source_id=str(data.get("source_id", "")).strip(), page=page)


def _parse_rule(data: dict[str, Any]) -> Rule:
    rule_id = str(data.get("rule_id", "")).strip()
    if not rule_id:
        raise RuleConfigError("Every rule needs a non-empty rule_id.")
    when = tuple(_parse_condition(c) for c in (data.get("when") or []))
    requires = tuple(str(p).strip() for p in (data.get("requires") or []))
    outcome = str(data.get("outcome", "")).strip()
    if outcome not in VALID_OUTCOMES:
        raise RuleConfigError(
            f"Rule {rule_id!r} has outcome {outcome!r}; allowed: {sorted(VALID_OUTCOMES)}."
        )
    reason = str(data.get("reason", "")).strip()
    if not reason:
        raise RuleConfigError(f"Rule {rule_id!r} needs a non-empty reason.")
    source_refs = tuple(_parse_source(s) for s in (data.get("source_refs") or []))
    if not source_refs:
        raise RuleConfigError(f"Rule {rule_id!r} needs at least one source_ref.")
    return Rule(
        rule_id=rule_id,
        when=when,
        requires=requires,
        outcome=outcome,
        reason=reason,
        source_refs=source_refs,
    )


# ---------------------------------------------------------------------------
# Loading + validation.
# ---------------------------------------------------------------------------
def _expected_parameter_names() -> tuple[str, ...]:
    """The live ParameterName literal set from the shared contract.

    Imported lazily so pure-logic paths do not force a pydantic import at
    module load. Raises RuleConfigError if the contract cannot be imported.
    """

    try:
        from src.models import ParameterName  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuleConfigError(
            f"Cannot import ParameterName from src.models to run the parameter-version gate: {exc}."
        ) from exc
    return tuple(get_args(ParameterName))


def _verify_parameter_version(meta: RulesMeta, live_names: tuple[str, ...]) -> None:
    expected = set(meta.expected_parameter_names)
    live = set(live_names)
    if expected == live:
        return
    missing = sorted(live - expected)  # in contract, absent from rules_meta
    extra = sorted(expected - live)  # in rules_meta, absent from contract
    raise RuleConfigError(
        "rules_meta.yaml expected_parameter_names does not match "
        "ParameterName in src.models. "
        f"missing_from_rules_meta={missing}; extra_in_rules_meta={extra}."
    )


def _validate_parameters(rules: tuple[Rule, ...], live_names: tuple[str, ...]) -> None:
    allowed = set(live_names)
    for rule in rules:
        for cond in rule.when:
            if cond.parameter not in allowed:
                raise RuleConfigError(
                    f"Rule {rule.rule_id!r} condition uses unknown parameter "
                    f"{cond.parameter!r} (not a ParameterName)."
                )
        for param in rule.requires:
            if param not in allowed:
                raise RuleConfigError(
                    f"Rule {rule.rule_id!r} requires unknown parameter "
                    f"{param!r} (not a ParameterName)."
                )


# The S0x evidence sources a rule may cite (catalog ids BRIEF/XLSX/DOCX are
# inventory labels, not SourceReference source_ids). Mirrors src.models.SourceID.
_KNOWN_SOURCE_IDS: frozenset[str] = frozenset({"S01", "S02", "S03", "S04", "S05", "S06"})


def _known_source_ids() -> frozenset[str]:
    """Catalog source ids if importable, else the static S0x set.

    The catalog import pulls in pydantic transitively (src.models). When that is
    unavailable (sandbox), fall back to the static ids so the page rules can
    still be validated without the full environment.
    """

    try:
        from . import catalog

        return frozenset(
            e.source_id for e in catalog.source_catalog() if e.source_id in _KNOWN_SOURCE_IDS
        )
    except Exception:  # pragma: no cover - environment dependent
        return _KNOWN_SOURCE_IDS


def _validate_sources(rules: tuple[Rule, ...]) -> None:
    """Cross-check every source_ref against the known source ids.

    S06 must have no page; S01-S05 require a 1-based page. The source_id must be
    a known S0x source. No invented pages.
    """

    known = _known_source_ids()

    for rule in rules:
        for ref in rule.source_refs:
            if ref.source_id not in known:
                raise RuleConfigError(
                    f"Rule {rule.rule_id!r} cites unknown source {ref.source_id!r}."
                )
            if ref.source_id == "S06":
                if ref.page is not None:
                    raise RuleConfigError(
                        f"Rule {rule.rule_id!r} cites S06 with a page; S06 is a text link."
                    )
            else:
                if not isinstance(ref.page, int) or ref.page < 1:
                    raise RuleConfigError(
                        f"Rule {rule.rule_id!r} cites {ref.source_id} without a 1-based page."
                    )


def parse_meta(data: dict[str, Any]) -> RulesMeta:
    names = tuple(str(n).strip() for n in (data.get("expected_parameter_names") or []))
    if not names:
        raise RuleConfigError("rules_meta.yaml must list expected_parameter_names.")
    return RulesMeta(
        rule_set_version=str(data.get("rule_set_version", "")).strip(),
        parameter_contract=str(data.get("parameter_contract", "")).strip(),
        expected_parameter_names=names,
    )


def load_rule_set(
    rules_dir: str | os.PathLike[str] = DEFAULT_RULES_DIR,
    *,
    verify_parameter_version: bool = True,
) -> RuleSet:
    """Load and validate the declarative rule set.

    Steps: parse ``rules_meta.yaml`` + the rule files, run the
    parameter-version gate (``verify_parameter_version``), confirm every
    referenced parameter is a ``ParameterName`` and every source_ref matches the
    catalog. Raises :class:`RuleConfigError` on any inconsistency.

    ``verify_parameter_version=False`` skips only the live-contract comparison
    (useful when pydantic/``src.models`` is unavailable) but still validates the
    file structure, predicates, outcomes and source pages.
    """

    rules_dir = os.fspath(rules_dir)

    meta_path = os.path.join(rules_dir, _META_FILE)
    if not os.path.isfile(meta_path):
        raise RuleConfigError(f"Missing rule metadata file: {meta_path}.")
    with open(meta_path, encoding="utf-8") as fh:
        meta = parse_meta(_load_yaml(fh.read()))

    rules: list[Rule] = []
    seen: set[str] = set()
    for filename in _RULE_FILES:
        path = os.path.join(rules_dir, filename)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            data = _load_yaml(fh.read())
        for raw_rule in data.get("rules") or []:
            rule = _parse_rule(raw_rule)
            if rule.rule_id in seen:
                raise RuleConfigError(f"Duplicate rule_id {rule.rule_id!r}.")
            seen.add(rule.rule_id)
            rules.append(rule)

    # Deterministic order by rule_id.
    ordered = tuple(sorted(rules, key=lambda r: r.rule_id))

    if verify_parameter_version:
        live_names = _expected_parameter_names()
        _verify_parameter_version(meta, live_names)
        _validate_parameters(ordered, live_names)
    else:
        # Structural self-consistency: rules must reference meta's own names.
        _validate_parameters(ordered, meta.expected_parameter_names)
    _validate_sources(ordered)

    return RuleSet(meta=meta, rules=ordered)


def load_rules(
    rules_dir: str | os.PathLike[str] = DEFAULT_RULES_DIR,
) -> tuple[RulesMeta, list[Rule]]:
    """Convenience wrapper: ``(meta, rules)`` with the full version gate on."""

    rule_set = load_rule_set(rules_dir)
    return rule_set.meta, list(rule_set.rules)


# ---------------------------------------------------------------------------
# Evaluation.
# ---------------------------------------------------------------------------
def _facts_by_parameter(extraction: ExtractionResult) -> dict[str, list[Any]]:
    facts: dict[str, list[Any]] = {}
    for fact in getattr(extraction, "stated_facts", []) or []:
        facts.setdefault(fact.parameter, []).append(fact)
    return facts


def _conflicted_parameters(extraction: ExtractionResult) -> set[str]:
    """Optional T06 field: parameters named in unresolved conflicts.

    Read getattr-safely; absent on the current main contract, so an empty set
    is the robust default.
    """

    conflicts = getattr(extraction, "conflicts", None) or []
    names: set[str] = set()
    for conflict in conflicts:
        name = getattr(conflict, "parameter", None)
        if isinstance(name, str):
            names.add(name)
    return names


def _condition_holds(cond: RuleCondition, facts: dict[str, list[Any]]) -> bool:
    present = cond.parameter in facts and bool(facts[cond.parameter])
    if cond.predicate == "parameter_present":
        result = present
    elif cond.predicate == "parameter_absent":
        result = not present
    elif cond.predicate == "value_contains_any":
        result = False
        if present:
            lowered = [str(getattr(f, "value", "")).lower() for f in facts[cond.parameter]]
            result = any(keyword.lower() in value for value in lowered for keyword in cond.keywords)
    else:  # pragma: no cover - guarded at load time
        raise RuleConfigError(f"Unknown predicate {cond.predicate!r}.")
    return (not result) if cond.negate else result


def _make_finding(rule: Rule, outcome: str, reason: str) -> RuleFinding:
    """Build a contract RuleFinding (the only pydantic-dependent step)."""

    from src.models import RuleFinding, SourceReference

    refs = [SourceReference(source_id=r.source_id, page=r.page) for r in rule.source_refs]
    return RuleFinding(rule_id=rule.rule_id, outcome=outcome, reason=reason, source_refs=refs)


def evaluate_rules(extraction: ExtractionResult) -> list[RuleFinding]:
    """Evaluate the loaded rule set against an extraction (``RuleEvaluator``).

    Matches :class:`src.contracts.RuleEvaluator` exactly:
    ``(extraction: ExtractionResult) -> list[RuleFinding]``.

    Per rule, in stable ``rule_id`` order:

    1. **Requires gate first.** If any ``requires`` parameter is missing from
       ``stated_facts`` (or is listed in ``unknowns`` / the optional T06
       ``conflicts``), emit ``outcome="unknown"`` - never a positive clearance.
    2. Otherwise evaluate the AND-combined ``when`` conditions on the raw quote
       text. A full match emits the rule's own outcome
       (``excluded``/``conditional``/``unknown``); no match contributes nothing.
    """

    rule_set = load_rule_set()
    facts = _facts_by_parameter(extraction)
    unknowns = set(getattr(extraction, "unknowns", []) or [])
    conflicted = _conflicted_parameters(extraction)

    findings: list[RuleFinding] = []
    for rule in rule_set.rules:
        missing = [
            param
            for param in rule.requires
            if param not in facts or param in unknowns or param in conflicted
        ]
        if missing:
            findings.append(
                _make_finding(
                    rule,
                    "unknown",
                    (
                        f"{rule.reason} [required parameter(s) not stated or disputed: "
                        f"{', '.join(sorted(missing))}; no clearance can be given.]"
                    ),
                )
            )
            continue

        if all(_condition_holds(cond, facts) for cond in rule.when):
            findings.append(_make_finding(rule, rule.outcome, rule.reason))

    return findings


__all__ = [
    "Outcome",
    "VALID_OUTCOMES",
    "Predicate",
    "VALID_PREDICATES",
    "RuleConfigError",
    "RuleCondition",
    "RuleSource",
    "Rule",
    "RulesMeta",
    "RuleSet",
    "DEFAULT_RULES_DIR",
    "parse_meta",
    "load_rule_set",
    "load_rules",
    "evaluate_rules",
]
