#!/usr/bin/env python3
"""Build the local AFS knowledge index from the material folder.

Usage::

    python scripts/build_index.py --materials materials --out data/index

Writes four artifacts into ``--out``:
    * evidence.jsonl       - technical evidence (S01-S04 text, S02 notes, XLSX,
                             S05/S06 business context). One JSON object per line.
    * dev_reference.jsonl  - D01-D08 + worked answers (kind=dev_reference),
                             kept SEPARATE from the evidence index.
    * catalog.json         - the source catalogue, present and missing files.
    * manifest.json        - UTC timestamp, source files with sizes + sha256
                             hashes, library versions, record counts. No secrets.

The script is idempotent (re-running overwrites the artifacts deterministically)
and graceful on missing inputs: a missing file is logged and skipped, not fatal.

NOTE: PyMuPDF / python-docx / openpyxl are required for the real build and are
pinned in requirements.txt. In the authoring sandbox PyPI is blocked, so this
script must be run locally by the maintainer:

    pip install -r requirements.txt
    python scripts/build_index.py --materials materials --out data/index
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys

# Make the project root importable when run as a script.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.knowledge import catalog, ingest  # noqa: E402
from src.knowledge.types import to_dict  # noqa: E402


def _log(msg: str) -> None:
    print(f"[build_index] {msg}")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _lib_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for mod_name, dist in (("fitz", "pymupdf"), ("docx", "python-docx"), ("openpyxl", "openpyxl")):
        try:
            mod = __import__(mod_name)
            versions[dist] = getattr(mod, "__version__", "unknown")
        except Exception:  # noqa: BLE001 - record availability, do not fail
            versions[dist] = "not-installed"
    return versions


def _write_jsonl(path: str, records: list) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(to_dict(rec), ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def build(materials_dir: str, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)

    # 1. Catalogue (present vs. missing).
    entries = catalog.check_materials(materials_dir)
    present_ids = {e.source_id for e in entries if e.present}
    for e in entries:
        state = "present" if e.present else "MISSING"
        _log(f"catalog {e.source_id:5s} {state:8s} {e.filename}")

    evidence: list = []

    # 2. PDF text sources (S01, S03, S04, BRIEF).
    for source_id, filename in ingest.PDF_TEXT_SOURCES.items():
        if source_id not in ingest.INDEXABLE_SOURCES or source_id not in present_ids:
            if source_id not in present_ids:
                _log(f"skip {source_id}: file not present")
            continue
        path = os.path.join(materials_dir, filename)
        try:
            recs = ingest.ingest_pdf_text(path, source_id)
            evidence.extend(recs)
            _log(f"ingested {source_id}: {len(recs)} page(s)")
        except ModuleNotFoundError as exc:
            _log(f"ERROR {source_id}: {exc}. Install requirements.txt and re-run.")
            raise

    # 3. Verified S02 notes.
    s02_recs = ingest.ingest_verified_s02_notes()
    evidence.extend(s02_recs)
    _log(f"ingested S02 verified notes: {len(s02_recs)} note(s)")

    # 4. XLSX transcription.
    xlsx = catalog.get_entry("XLSX")
    if xlsx and "XLSX" in present_ids:
        try:
            recs = ingest.ingest_table_xlsx(os.path.join(materials_dir, xlsx.filename))
            evidence.extend(recs)
            _log(f"ingested XLSX: {len(recs)} row/note record(s)")
        except ModuleNotFoundError as exc:
            _log(f"ERROR XLSX: {exc}. Install requirements.txt and re-run.")
            raise
    else:
        _log("skip XLSX: file not present")

    # 5. Business context (S05, S06).
    ctx = ingest.ingest_business_context(materials_dir)
    evidence.extend(ctx)
    _log(f"ingested business context: {len(ctx)} record(s)")

    # 6. Development reference DOCX (SEPARATE index).
    dev_records: list = []
    docx_entry = catalog.get_entry("DOCX")
    if docx_entry and os.path.isfile(os.path.join(materials_dir, docx_entry.filename)):
        try:
            dev_records = ingest.ingest_dev_reference_docx(
                os.path.join(materials_dir, docx_entry.filename)
            )
            _log(f"ingested dev reference DOCX: {len(dev_records)} paragraph(s)")
        except ModuleNotFoundError as exc:
            _log(f"ERROR DOCX: {exc}. Install requirements.txt and re-run.")
            raise
    else:
        _log("skip DOCX: file not present")

    # --- Write artifacts (deterministic order). ---
    evidence.sort(key=lambda r: r.chunk_id)
    evidence_path = os.path.join(out_dir, "evidence.jsonl")
    dev_path = os.path.join(out_dir, "dev_reference.jsonl")
    catalog_path = os.path.join(out_dir, "catalog.json")
    manifest_path = os.path.join(out_dir, "manifest.json")

    _write_jsonl(evidence_path, evidence)
    _write_jsonl(dev_path, dev_records)

    with open(catalog_path, "w", encoding="utf-8") as fh:
        json.dump(
            [to_dict(e) for e in entries],
            fh,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    # Source-file provenance (sizes + hashes). No secrets, no file contents.
    source_files = []
    for e in sorted(entries, key=lambda x: x.source_id):
        path = os.path.join(materials_dir, e.filename)
        if os.path.isfile(path):
            source_files.append(
                {
                    "source_id": e.source_id,
                    "filename": e.filename,
                    "size_bytes": os.path.getsize(path),
                    "sha256": _sha256(path),
                }
            )

    manifest = {
        "built_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "materials_dir": materials_dir,
        "out_dir": out_dir,
        "library_versions": _lib_versions(),
        "counts": {
            "evidence": len(evidence),
            "dev_reference": len(dev_records),
            "catalog_entries": len(entries),
            "present_sources": len(present_ids),
            "missing_sources": len(entries) - len(present_ids),
        },
        "source_files": source_files,
    }
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)

    _log(
        f"done: {len(evidence)} evidence, {len(dev_records)} dev_reference, "
        f"{len(entries)} catalog entries -> {out_dir}"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the AFS knowledge index.")
    parser.add_argument("--materials", default="materials", help="input material folder")
    parser.add_argument("--out", default="data/index", help="output index folder")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.materials):
        _log(f"ERROR: materials dir not found: {args.materials}")
        return 2

    build(args.materials, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
