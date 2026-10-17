#!/usr/bin/env python3
"""T10 citation/physics gate CLI for D-/H-batch QA and reproduction.

Usage::

    python scripts/check_citations.py --result <result.json> [--index data/index]

Loads a saved :class:`~src.models.AnalysisResult` from ``--result`` and the
retrieved :class:`~src.models.Evidence` from ``<index>/evidence.jsonl``, runs
the SAME gate as the pipeline via :func:`src.engine.validators.validate_result`
(no rule duplication), prints every finding and exits with a non-zero status
when any ``error`` finding is present. Rules are not reconstructed here (they
are produced upstream by T03), so the CLI runs the citation/physics/evidence
checks with an empty rule list.

This needs the production environment (pydantic) to build the contract objects;
it is a QA/repro tool, not a sandbox pure-logic path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engine.validators import validate_result  # noqa: E402


def _load_result(path: str):
    from src.models import AnalysisResult

    with open(path, encoding="utf-8") as fh:
        return AnalysisResult.model_validate_json(fh.read())


def _load_evidence(index_dir: str) -> list:
    from src.models import Evidence

    evidence_path = os.path.join(index_dir, "evidence.jsonl")
    if not os.path.isfile(evidence_path):
        raise FileNotFoundError(
            f"Evidence index not found: {evidence_path!r}. "
            "Build it with `python scripts/build_index.py`."
        )
    records: list = []
    with open(evidence_path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                records.append(Evidence.model_validate_json(line))
            except Exception as exc:  # noqa: BLE001 - surface with context
                raise ValueError(
                    f"evidence.jsonl line {lineno} is not valid Evidence: {exc}"
                ) from exc
    return records


def _print_findings(report) -> int:
    findings = list(report.findings)
    if not findings:
        print("No findings: citations, pages, evidence_ids and units all check out.")
        return 0

    counts = {"error": 0, "warning": 0, "not_checked": 0}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
        print(
            f"[{finding.severity.upper():11s}] {finding.code} @ {finding.field_path}\n"
            f"    {finding.message}"
        )
        if finding.evidence_ids:
            print(f"    evidence_ids: {', '.join(finding.evidence_ids)}")

    print(
        f"\nSummary: {counts['error']} error(s), {counts['warning']} warning(s), "
        f"{counts['not_checked']} not_checked."
    )
    return 1 if report.has_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the T10 citation/physics gate over a saved AnalysisResult."
    )
    parser.add_argument("--result", required=True, help="path to an AnalysisResult JSON file")
    parser.add_argument(
        "--index",
        default=os.path.join("data", "index"),
        help="index directory containing evidence.jsonl (default: data/index)",
    )
    args = parser.parse_args(argv)

    try:
        result = _load_result(args.result)
        evidence = _load_evidence(args.index)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"check_citations: could not load inputs: {exc}", file=sys.stderr)
        return 2

    report = validate_result(result, evidence, [])
    return _print_findings(report)


if __name__ == "__main__":
    raise SystemExit(main())
