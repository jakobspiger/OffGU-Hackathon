"""T10 B7 - deterministic citation and physics gate.

A **stateless, pure** validator: :func:`validate_result` takes a synthesised
:class:`~src.models.AnalysisResult`, the retrieved ``evidence`` and the
:class:`~src.models.RuleFinding` list and returns a FRESH
:class:`~src.models.ValidationReport` on every call. It matches the
:class:`src.contracts.ResultValidator` protocol exactly::

    def __call__(self, result: AnalysisResult,
                 evidence: list[Evidence],
                 rules: list[RuleFinding]) -> ValidationReport: ...

What this gate checks (and what it deliberately does NOT)
---------------------------------------------------------
The gate checks the **existence, scope and format** of sources, pages,
evidence_ids and spectral units against the static source catalog and the
contract. It is NOT a semantic correctness proof: a cited page **existing** is
NOT the same as that page **supporting** the claim. Such unverifiable
claim <-> page relationships are reported as ``not_checked`` findings (code
``SEMANTIC_SUPPORT_NOT_CHECKED``), never silently passed as if verified. This
limit is the documented boundary of the automatic check (acceptance criterion
5): no LLM, no semantic matching, deterministic and reproducible only.

Separation of concerns with gate_node (T11)
-------------------------------------------
Missing evidence or critical rule violations must PREVENT an unjustified
clearance, but this validator expresses that consequence **only** via ``error``
findings (so :attr:`ValidationReport.has_errors` becomes ``True``). It NEVER
sets or returns ``decision_status`` and NEVER mutates ``result``. The pipeline
gate (``src.engine.graph.gate_node``) is the single place that turns
``has_errors`` into ``decision_status="insufficient_information"``. Keeping that
split avoids double-punishing and keeps this validator a drop-in,
side-effect-free seam for the correction loop.

Sandbox note
------------
The pure checks (:func:`_check_citations`, :func:`_check_physics`,
:func:`_check_rules` and their helpers) read their inputs via light attribute
access and emit plain :class:`_FindingSpec` dicts, so they run on the standard
library alone with duck-typed stubs. Only :func:`validate_result` turns the
collected specs into contract :class:`~src.models.ValidationFinding` /
:class:`~src.models.ValidationReport` objects, so that single assembly step is
the only part that needs pydantic (via ``src.models``). The catalog page-range
lookup is lazy with a static S0x fallback (mirroring
``src.knowledge.rules._known_source_ids``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a hard pydantic import
    from src.models import AnalysisResult, Evidence, RuleFinding, ValidationReport

# ---------------------------------------------------------------------------
# Severity constants (mirror src.models.ValidationFinding.severity exactly).
# ---------------------------------------------------------------------------
ERROR = "error"
WARNING = "warning"
NOT_CHECKED = "not_checked"

# ---------------------------------------------------------------------------
# Stable finding-code catalog. These strings are part of the gate's public
# surface (gate_node / CLI / tests key off them); do not rename lightly.
# ---------------------------------------------------------------------------
CITATION_SOURCE_UNKNOWN = "CITATION_SOURCE_UNKNOWN"
CITATION_PAGE_OUT_OF_RANGE = "CITATION_PAGE_OUT_OF_RANGE"
EVIDENCE_ID_MISSING = "EVIDENCE_ID_MISSING"
EVIDENCE_SCOPE_BUSINESS_CONTEXT = "EVIDENCE_SCOPE_BUSINESS_CONTEXT"
EVIDENCE_SCOPE_RESEARCH = "EVIDENCE_SCOPE_RESEARCH"
SEMANTIC_SUPPORT_NOT_CHECKED = "SEMANTIC_SUPPORT_NOT_CHECKED"
SPECTRAL_VERIFIED_WITHOUT_EVIDENCE = "SPECTRAL_VERIFIED_WITHOUT_EVIDENCE"
SPECTRAL_RANGE_IMPLAUSIBLE = "SPECTRAL_RANGE_IMPLAUSIBLE"
RULE_EXCLUDED_CONTRADICTION = "RULE_EXCLUDED_CONTRADICTION"
RULE_UNKNOWN_UNRESOLVED = "RULE_UNKNOWN_UNRESOLVED"

# The S0x evidence sources the contract knows (mirrors src.models.SourceID).
_KNOWN_SOURCE_IDS: frozenset[str] = frozenset({"S01", "S02", "S03", "S04", "S05", "S06"})

# Static 1-based inclusive page spans per source, derived verbatim from the
# verified catalog (src.knowledge.catalog). S03/S04/S06 carry no fixed page
# span in the catalog (research PDFs / text link), so they are not range-checked
# beyond the S06 "no page" rule. Used as a fallback so the page check runs
# without importing the catalog (which pulls pydantic transitively).
_STATIC_PAGE_SPANS: dict[str, tuple[int, int]] = {
    "S01": (1, 19),
    "S02": (1, 20),
    "S05": (1, 2),
}

# business_context evidence (S05/S06) is never a performance proof; research
# evidence (S03/S04) must not be overreached into a clearance. Mapped by the
# evidence ``purpose`` field (contract: technical | research | business_context).
_BUSINESS_CONTEXT_PURPOSE = "business_context"
_RESEARCH_PURPOSE = "research"

# Known nominal method ranges (plausibility only, not a hard schema bound).
# NIR wavelengths ~780-2500 nm; MIR wavenumbers ~400-4000 cm^-1. A span whose
# endpoints fall far outside the matching nominal band, without a verified
# scope, is flagged as a (soft) warning. Generous margins avoid false alarms.
_NOMINAL_NM = (700.0, 2600.0)
_NOMINAL_CM = (350.0, 4200.0)


class _FindingSpec:
    """Plain, pydantic-free description of one finding.

    Collected by the sub-gates and turned into a contract
    :class:`~src.models.ValidationFinding` only in :func:`validate_result`.
    Keeping this a stdlib object lets the pure-logic checks run and be asserted
    without importing pydantic.
    """

    __slots__ = ("code", "severity", "message", "field_path", "evidence_ids")

    def __init__(
        self,
        code: str,
        severity: str,
        message: str,
        field_path: str,
        evidence_ids: list[str] | None = None,
    ) -> None:
        self.code = code
        self.severity = severity
        self.message = message
        self.field_path = field_path
        self.evidence_ids = list(evidence_ids or [])

    def sort_key(self) -> tuple[str, str]:
        """Deterministic order: by ``field_path`` then ``code``."""

        return (self.field_path, self.code)


# ---------------------------------------------------------------------------
# Small duck-typed accessors (work on contract objects and on test stubs).
# ---------------------------------------------------------------------------
def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _known_page_spans() -> dict[str, tuple[int, int]]:
    """Catalog page spans if importable, else the static S0x fallback.

    The catalog import pulls pydantic transitively (via ``src.knowledge.types``
    -> ``src.models``). When that is unavailable (sandbox) the static spans are
    used, so the page-range check stays testable on stdlib alone. Only the three
    sources with a fixed numeric span (S01/S02/S05) are range-checked.
    """

    try:  # pragma: no cover - environment dependent
        from src.knowledge import catalog

        spans: dict[str, tuple[int, int]] = {}
        for entry in catalog.source_catalog():
            source_id = entry.source_id
            if source_id not in _KNOWN_SOURCE_IDS:
                continue
            span = _parse_span(getattr(entry, "pages", None))
            if span is not None:
                spans[source_id] = span
        return spans or dict(_STATIC_PAGE_SPANS)
    except Exception:  # pragma: no cover - environment dependent
        return dict(_STATIC_PAGE_SPANS)


def _parse_span(pages: Any) -> tuple[int, int] | None:
    """Parse a catalog ``pages`` string like ``"1-19"`` or ``"6"`` to a span."""

    if not isinstance(pages, str) or not pages.strip():
        return None
    text = pages.strip()
    if "-" in text:
        lo, _, hi = text.partition("-")
        try:
            return (int(lo), int(hi))
        except ValueError:
            return None
    try:
        page = int(text)
    except ValueError:
        return None
    return (page, page)


# ---------------------------------------------------------------------------
# Pure page-range check (used by the citation gate and the CLI).
# ---------------------------------------------------------------------------
def page_in_range(source_id: str, page: int | None, spans: dict[str, tuple[int, int]]) -> bool:
    """Is ``page`` a valid 1-based page for ``source_id``?

    S06 is a text link: it must carry no page. S0x require a 1-based page; if a
    numeric span is known for the source, the page must fall inside it. Sources
    without a fixed span (e.g. research PDFs S03/S04) only require a positive
    page. Unknown source ids are rejected.
    """

    if source_id not in _KNOWN_SOURCE_IDS:
        return False
    if source_id == "S06":
        return page is None
    if not isinstance(page, int) or page < 1:
        return False
    span = spans.get(source_id)
    if span is None:
        return True
    lo, hi = span
    return lo <= page <= hi


# ---------------------------------------------------------------------------
# AP1 - citation gate.
# ---------------------------------------------------------------------------
def _check_citations(
    result: Any,
    evidence: list[Any],
    spans: dict[str, tuple[int, int]] | None = None,
) -> list[_FindingSpec]:
    """Check sources, pages, evidence_ids and evidence scope against the catalog.

    Emits, deterministically:

    * ``CITATION_SOURCE_UNKNOWN`` (error) - a ``source_id`` outside S01-S06.
    * ``CITATION_PAGE_OUT_OF_RANGE`` (error) - a page absent from / outside the
      catalog span (or a page on S06, which is a text link).
    * ``EVIDENCE_ID_MISSING`` (error) - a recommendation ``evidence_id`` that is
      not present in the supplied ``evidence`` list.
    * ``EVIDENCE_SCOPE_BUSINESS_CONTEXT`` (error) - a technical recommendation
      cites business-context evidence (S05/S06) as its proof.
    * ``EVIDENCE_SCOPE_RESEARCH`` (warning) - a recommendation leans on research
      evidence (S03/S04); the scope must not be overreached.
    * ``SEMANTIC_SUPPORT_NOT_CHECKED`` (not_checked) - exactly one per
      recommendation: the gate cannot verify that an existing page actually
      supports the claim (documented limit).
    """

    if spans is None:
        spans = _known_page_spans()

    findings: list[_FindingSpec] = []
    evidence_by_id = {_attr(ev, "evidence_id"): ev for ev in evidence}

    # overall_sources: existence/format only (no evidence_ids attached there).
    for idx, ref in enumerate(_attr(result, "overall_sources", []) or []):
        findings.extend(_check_source_ref(ref, f"overall_sources[{idx}]", spans))

    for r_idx, rec in enumerate(_attr(result, "recommendations", []) or []):
        base = f"recommendations[{r_idx}]"

        for s_idx, ref in enumerate(_attr(rec, "source_refs", []) or []):
            findings.extend(_check_source_ref(ref, f"{base}.source_refs[{s_idx}]", spans))

        rec_evidence_ids = list(_attr(rec, "evidence_ids", []) or [])
        cited_evidence: list[Any] = []
        for e_idx, ev_id in enumerate(rec_evidence_ids):
            if ev_id not in evidence_by_id:
                findings.append(
                    _FindingSpec(
                        EVIDENCE_ID_MISSING,
                        ERROR,
                        (
                            f"Recommendation cites evidence_id {ev_id!r}, which is not "
                            "present in the supplied evidence; a claim cannot rest on "
                            "evidence that was never retrieved."
                        ),
                        f"{base}.evidence_ids[{e_idx}]",
                        evidence_ids=[ev_id],
                    )
                )
            else:
                cited_evidence.append(evidence_by_id[ev_id])

        findings.extend(_check_evidence_scope(cited_evidence, base))

        # Documented limit: existing page != semantic support. Exactly ONE
        # not_checked finding per recommendation, naming the cited refs.
        ref_labels = _source_ref_labels(_attr(rec, "source_refs", []) or [])
        cited_ids = [eid for eid in rec_evidence_ids if eid in evidence_by_id]
        findings.append(
            _FindingSpec(
                SEMANTIC_SUPPORT_NOT_CHECKED,
                NOT_CHECKED,
                (
                    "Cited pages/evidence exist but the gate cannot automatically "
                    "verify that they semantically support this recommendation "
                    f"(cited refs: {', '.join(ref_labels) or 'none'}). "
                    "A human must confirm the claim against the source."
                ),
                base,
                evidence_ids=cited_ids,
            )
        )

    return findings


def _check_source_ref(
    ref: Any, field_path: str, spans: dict[str, tuple[int, int]]
) -> list[_FindingSpec]:
    """Existence/format of a single SourceReference-like object."""

    findings: list[_FindingSpec] = []
    source_id = _attr(ref, "source_id")
    page = _attr(ref, "page")

    if source_id not in _KNOWN_SOURCE_IDS:
        findings.append(
            _FindingSpec(
                CITATION_SOURCE_UNKNOWN,
                ERROR,
                (
                    f"Citation references unknown source {source_id!r}; only the "
                    "catalogued sources S01-S06 may be cited (no invented sources)."
                ),
                field_path,
            )
        )
        return findings

    if not page_in_range(source_id, page, spans):
        findings.append(
            _FindingSpec(
                CITATION_PAGE_OUT_OF_RANGE,
                ERROR,
                (
                    f"Citation {source_id} page {page!r} is not a valid page for that "
                    "source per the catalog (S06 is a text link with no page; S0x "
                    "pages must fall inside the catalogued span). No invented pages."
                ),
                field_path,
            )
        )
    return findings


def _check_evidence_scope(cited_evidence: list[Any], base_field: str) -> list[_FindingSpec]:
    """Scope check on the evidence a recommendation actually cites.

    business_context evidence (S05/S06) used as a technical proof -> error;
    research evidence (S03/S04) leaned on -> warning (scope not overreached).
    """

    findings: list[_FindingSpec] = []
    business_ids: list[str] = []
    research_ids: list[str] = []
    for ev in cited_evidence:
        purpose = _attr(ev, "purpose")
        ev_id = _attr(ev, "evidence_id")
        if purpose == _BUSINESS_CONTEXT_PURPOSE:
            business_ids.append(ev_id)
        elif purpose == _RESEARCH_PURPOSE:
            research_ids.append(ev_id)

    if business_ids:
        findings.append(
            _FindingSpec(
                EVIDENCE_SCOPE_BUSINESS_CONTEXT,
                ERROR,
                (
                    "Recommendation uses business-context evidence (S05/S06) as a "
                    "performance proof; company/product context is not technical "
                    f"evidence (evidence_ids: {', '.join(sorted(business_ids))})."
                ),
                f"{base_field}.evidence_ids",
                evidence_ids=sorted(business_ids),
            )
        )

    if research_ids:
        findings.append(
            _FindingSpec(
                EVIDENCE_SCOPE_RESEARCH,
                WARNING,
                (
                    "Recommendation leans on research proof-of-concept evidence "
                    "(S03/S04); keep the research scope and do not overreach it into "
                    f"a process/clinical clearance (evidence_ids: "
                    f"{', '.join(sorted(research_ids))})."
                ),
                f"{base_field}.evidence_ids",
                evidence_ids=sorted(research_ids),
            )
        )

    return findings


def _source_ref_labels(refs: list[Any]) -> list[str]:
    labels: list[str] = []
    for ref in refs:
        source_id = _attr(ref, "source_id")
        page = _attr(ref, "page")
        labels.append(f"{source_id} p.{page}" if page is not None else f"{source_id}")
    return labels


# ---------------------------------------------------------------------------
# AP2 - physics / units gate.
# ---------------------------------------------------------------------------
def _check_physics(result: Any) -> list[_FindingSpec]:
    """Check each recommendation's spectral range for belegable extras.

    The contract already enforces ascending endpoints and unit<->quantity
    consistency, so this gate only adds checks that the schema does NOT cover:

    * ``SPECTRAL_VERIFIED_WITHOUT_EVIDENCE`` (error) - a range flagged
      ``scope="verified_instrument"`` while the recommendation cites no evidence
      (nominal method ranges are not an instrument clearance).
    * ``SPECTRAL_RANGE_IMPLAUSIBLE`` (warning) - a span whose endpoints fall far
      outside the known nominal band for its unit.
    """

    findings: list[_FindingSpec] = []
    for r_idx, rec in enumerate(_attr(result, "recommendations", []) or []):
        spectral = _attr(rec, "spectral_range")
        if spectral is None:
            continue
        field_path = f"recommendations[{r_idx}].spectral_range"

        scope = _attr(spectral, "scope")
        evidence_ids = list(_attr(rec, "evidence_ids", []) or [])
        if scope == "verified_instrument" and not evidence_ids:
            findings.append(
                _FindingSpec(
                    SPECTRAL_VERIFIED_WITHOUT_EVIDENCE,
                    ERROR,
                    (
                        "Spectral range is marked scope=verified_instrument but the "
                        "recommendation cites no evidence; a verified hardware range "
                        "needs a supporting source (a nominal method range is not an "
                        "instrument clearance)."
                    ),
                    field_path,
                    evidence_ids=evidence_ids,
                )
            )

        if _range_implausible(spectral):
            findings.append(
                _FindingSpec(
                    SPECTRAL_RANGE_IMPLAUSIBLE,
                    WARNING,
                    (
                        "Spectral range lies far outside the known nominal band for "
                        "its unit (NIR ~780-2500 nm; MIR ~400-4000 cm^-1); confirm "
                        "the endpoints against a source."
                    ),
                    field_path,
                )
            )

    return findings


def _range_implausible(spectral: Any) -> bool:
    """True if the span endpoints fall far outside the nominal band for the unit."""

    unit = _attr(spectral, "unit")
    lower = _attr(spectral, "lower")
    upper = _attr(spectral, "upper")
    if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
        return False
    if unit == "nm":
        band = _NOMINAL_NM
    elif unit == "cm^-1":
        band = _NOMINAL_CM
    else:
        return False
    lo, hi = band
    return lower < lo or upper > hi


# ---------------------------------------------------------------------------
# AP3 - rule gate.
# ---------------------------------------------------------------------------
def _check_rules(result: Any, rules: list[Any]) -> list[_FindingSpec]:
    """Evaluate critical RuleFindings against the result's decision status.

    Generic over rule outcomes only (no scenario-id branching):

    * ``RULE_EXCLUDED_CONTRADICTION`` (error) - an ``outcome="excluded"`` rule
      while the result still carries recommendations / a ``provisional`` status;
      a documented exclusion contradicts an unconditional go.
    * ``RULE_UNKNOWN_UNRESOLVED`` (warning) - an ``outcome="unknown"`` blocking
      gap while the result is ``provisional``. The hard no-clearance consequence
      is gate_node's job; the validator only warns (no double punishment).
    """

    findings: list[_FindingSpec] = []
    decision_status = _attr(result, "decision_status")
    has_recommendations = bool(_attr(result, "recommendations", []) or [])
    is_provisional = decision_status == "provisional"

    for idx, rule in enumerate(rules):
        outcome = _attr(rule, "outcome")
        rule_id = _attr(rule, "rule_id")
        field_path = f"rules[{idx}]"

        if outcome == "excluded" and (is_provisional or has_recommendations):
            findings.append(
                _FindingSpec(
                    RULE_EXCLUDED_CONTRADICTION,
                    ERROR,
                    (
                        f"Rule {rule_id!r} excludes this configuration, yet the result "
                        "still presents recommendations / a provisional go; the "
                        "documented exclusion contradicts the clearance."
                    ),
                    field_path,
                )
            )
        elif outcome == "unknown" and is_provisional:
            findings.append(
                _FindingSpec(
                    RULE_UNKNOWN_UNRESOLVED,
                    WARNING,
                    (
                        f"Rule {rule_id!r} reports an unresolved blocking gap "
                        "(outcome=unknown) while the result is provisional; the open "
                        "gap should be resolved before a clearance."
                    ),
                    field_path,
                )
            )

    return findings


# ---------------------------------------------------------------------------
# AP4 - public validator (matches src.contracts.ResultValidator exactly).
# ---------------------------------------------------------------------------
def validate_result(
    result: AnalysisResult,
    evidence: list[Evidence],
    rules: list[RuleFinding],
) -> ValidationReport:
    """Validate ``result`` and return a FRESH :class:`ValidationReport`.

    Stateless and pure: gathers findings from the three sub-gates, sorts them
    deterministically (by ``field_path`` then ``code``) and builds a brand new
    report on every call. It NEVER mutates ``result`` and NEVER sets
    ``decision_status`` - the pipeline gate owns that consequence.
    """

    from src.models import ValidationFinding, ValidationReport

    specs: list[_FindingSpec] = []
    specs.extend(_check_citations(result, evidence))
    specs.extend(_check_physics(result))
    specs.extend(_check_rules(result, rules))

    specs.sort(key=lambda spec: spec.sort_key())

    findings = [
        ValidationFinding(
            code=spec.code,
            severity=spec.severity,
            message=spec.message,
            field_path=spec.field_path,
            evidence_ids=list(spec.evidence_ids),
        )
        for spec in specs
    ]
    return ValidationReport(findings=findings)


__all__ = [
    "validate_result",
    "page_in_range",
    "ERROR",
    "WARNING",
    "NOT_CHECKED",
    "CITATION_SOURCE_UNKNOWN",
    "CITATION_PAGE_OUT_OF_RANGE",
    "EVIDENCE_ID_MISSING",
    "EVIDENCE_SCOPE_BUSINESS_CONTEXT",
    "EVIDENCE_SCOPE_RESEARCH",
    "SEMANTIC_SUPPORT_NOT_CHECKED",
    "SPECTRAL_VERIFIED_WITHOUT_EVIDENCE",
    "SPECTRAL_RANGE_IMPLAUSIBLE",
    "RULE_EXCLUDED_CONTRADICTION",
    "RULE_UNKNOWN_UNRESOLVED",
]
