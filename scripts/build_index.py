#!/usr/bin/env python3
"""Build the local AFS knowledge index from the material folder.

Usage::

    uv run python scripts/build_index.py
    uv run python scripts/build_index.py --materials materials --out data/index

Defaults come from ``Settings()`` (``afs_source_dir`` / ``afs_index_dir``);
explicit CLI arguments override them. The S02 notes path is resolved relative
to ``src.config.PROJECT_ROOT``.

Writes into ``--out``:
    * evidence.jsonl          - technical/business evidence (S01-S04 text, S02
                                notes, XLSX, S05/S06). One JSON object per line.
    * reference_records.jsonl - BRIEF + DOCX as ReferenceRecord, kept SEPARATE
                                from the evidence index (replaces the old
                                dev_reference.jsonl).
    * catalog.json            - the source catalogue, present and missing files.
    * manifest.json           - UTC timestamp, source files with sizes + sha256
                                hashes, library versions, record counts,
                                retrieval mode + embedding model name. No secrets.
    * embedding_meta.json      - retrieval mode and (vector mode only) embedding
                                model + vector dimension + UTC timestamp. No
                                secrets, no key.
    * embeddings.jsonl         - ONLY in vector mode: one ``{evidence_id,
                                vector}`` line per Evidence, embedded via the
                                configured OpenAI-compatible /embeddings endpoint.

T04 retrieval mode (auto-switch, no silent fallback)
----------------------------------------------------
The build is **lexical** by default. It becomes **vector** only when
``Settings().afs_embedding_model`` is set (non-empty): then each Evidence text
is embedded once and ``embeddings.jsonl`` is written. With no embedding model
configured the embedding step is skipped entirely (no API call) and
``embedding_meta.json`` records ``mode="lexical"``. The T02 artifacts above are
unchanged in either mode; the embedding outputs are a pure addition.

Every evidence line is self-validated via ``Evidence.model_validate_json``; a
single failure aborts the build. The script is idempotent (re-running
overwrites the artifacts deterministically) and graceful on missing inputs: a
missing file is logged and skipped, not fatal.

PyMuPDF / python-docx / openpyxl / PyYAML / pydantic are installed via
``pyproject.toml`` / ``uv.lock``. Run locally with ``uv``:

    uv sync --locked
    uv run python scripts/build_index.py
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

from src.config import PROJECT_ROOT, Settings  # noqa: E402
from src.knowledge import catalog, ingest  # noqa: E402
from src.knowledge.types import Evidence, to_dict  # noqa: E402


def _retrieval_mode(settings: Settings) -> str:
    """vector when an embedding model is configured, else lexical.

    No silent fallback to an invented model: an empty AFS_EMBEDDING_MODEL keeps
    the build lexical and skips every embedding API call.
    """

    return "vector" if settings.afs_embedding_model else "lexical"

S02_NOTES_PATH = PROJECT_ROOT / "data" / "source_notes" / "s02_notes.yaml"


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


def _validate_evidence_file(path: str) -> int:
    """Re-read every evidence line and validate it against the contract.

    Returns the number of validated lines. Raises if any line is not a valid
    :class:`Evidence`, aborting the build.
    """

    count = 0
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                Evidence.model_validate_json(line)
            except Exception as exc:  # noqa: BLE001 - re-raise with context
                raise ValueError(
                    f"evidence.jsonl line {lineno} failed contract validation: {exc}"
                ) from exc
            count += 1
    return count


def _build_embeddings(
    evidence: list, out_dir: str, settings: Settings
) -> dict:
    """Vector mode only: embed each Evidence text and persist the vectors.

    Writes ``embeddings.jsonl`` (one ``{evidence_id, vector}`` line per record)
    and returns embedding metadata (model, dim) for ``embedding_meta.json`` /
    ``manifest.json``. Never writes the API key. Called only when the retrieval
    mode is ``vector``.
    """

    from src.knowledge.embedding import embed_texts

    texts = [rec.text for rec in evidence]
    # Pages are embedded as plain text. Eight at a time stays inside the
    # request timeout for qwen3-embedding-4b; the query prefix is not applied.
    vectors = embed_texts(texts, settings, batch_size=8) if texts else []
    embeddings_path = os.path.join(out_dir, "embeddings.jsonl")
    with open(embeddings_path, "w", encoding="utf-8") as fh:
        for rec, vector in zip(evidence, vectors):
            fh.write(
                json.dumps(
                    {"evidence_id": rec.evidence_id, "vector": vector},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            fh.write("\n")
    dim = len(vectors[0]) if vectors else 0
    _log(f"embedded {len(vectors)} evidence text(s), dim={dim} -> embeddings.jsonl")
    return {"model": settings.afs_embedding_model, "dim": dim}


def build(materials_dir: str, out_dir: str, settings: Settings | None = None) -> dict:
    if settings is None:
        settings = Settings()
    os.makedirs(out_dir, exist_ok=True)

    # 1. Catalogue (present vs. missing).
    entries = catalog.check_materials(materials_dir)
    present_ids = {e.source_id for e in entries if e.present}
    for e in entries:
        state = "present" if e.present else "MISSING"
        _log(f"catalog {e.source_id:5s} {state:8s} {e.filename}")

    evidence: list = []
    references: list = []

    # 2. PDF text sources (S01, S03, S04) -> Evidence.
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
            _log(f"ERROR {source_id}: {exc}. Run `uv sync --locked` and re-run.")
            raise

    # 3. Curated S02 notes (pending_visual_check) -> Evidence.
    s02_recs = ingest.ingest_curated_s02_notes(S02_NOTES_PATH)
    evidence.extend(s02_recs)
    _log(f"ingested S02 curated notes: {len(s02_recs)} note(s)")

    # 4. XLSX transcription -> Evidence.
    xlsx = catalog.get_entry("XLSX")
    if xlsx and "XLSX" in present_ids:
        try:
            recs = ingest.ingest_table_xlsx(os.path.join(materials_dir, xlsx.filename))
            evidence.extend(recs)
            _log(f"ingested XLSX: {len(recs)} row/note record(s)")
        except ModuleNotFoundError as exc:
            _log(f"ERROR XLSX: {exc}. Run `uv sync --locked` and re-run.")
            raise
    else:
        _log("skip XLSX: file not present")

    # 5. Business context (S05, S06) -> Evidence.
    ctx = ingest.ingest_business_context(materials_dir)
    evidence.extend(ctx)
    _log(f"ingested business context: {len(ctx)} record(s)")

    # 6. Challenge brief (BRIEF) -> ReferenceRecord (NOT evidence).
    brief_path = os.path.join(materials_dir, ingest.BRIEF_FILENAME)
    if os.path.isfile(brief_path):
        try:
            brief_recs = ingest.ingest_brief_reference(brief_path)
            references.extend(brief_recs)
            _log(f"ingested BRIEF reference: {len(brief_recs)} page(s)")
        except ModuleNotFoundError as exc:
            _log(f"ERROR BRIEF: {exc}. Run `uv sync --locked` and re-run.")
            raise
    else:
        _log("skip BRIEF: file not present")

    # 7. Development reference DOCX -> ReferenceRecord (NOT evidence).
    docx_entry = catalog.get_entry("DOCX")
    if docx_entry and os.path.isfile(os.path.join(materials_dir, docx_entry.filename)):
        try:
            dev_recs = ingest.ingest_dev_reference_docx(
                os.path.join(materials_dir, docx_entry.filename)
            )
            references.extend(dev_recs)
            _log(f"ingested dev reference DOCX: {len(dev_recs)} paragraph(s)")
        except ModuleNotFoundError as exc:
            _log(f"ERROR DOCX: {exc}. Run `uv sync --locked` and re-run.")
            raise
    else:
        _log("skip DOCX: file not present")

    # --- Write artifacts (deterministic order). ---
    evidence.sort(key=lambda r: r.evidence_id)
    references.sort(key=lambda r: r.record_id)
    evidence_path = os.path.join(out_dir, "evidence.jsonl")
    references_path = os.path.join(out_dir, "reference_records.jsonl")
    catalog_path = os.path.join(out_dir, "catalog.json")
    manifest_path = os.path.join(out_dir, "manifest.json")

    _write_jsonl(evidence_path, evidence)
    _write_jsonl(references_path, references)

    # Self-validation: every written evidence line must be a valid Evidence.
    validated = _validate_evidence_file(evidence_path)
    _log(f"self-validated {validated} evidence line(s) against the contract")

    # --- T04 embedding index (additive; pure lexical unless a model is set). ---
    mode = _retrieval_mode(settings)
    embedding_info: dict = {"model": settings.afs_embedding_model, "dim": 0}
    if mode == "vector":
        embedding_info = _build_embeddings(evidence, out_dir, settings)
    else:
        _log("retrieval mode lexical: no embedding model set, skipping embeddings.jsonl")
    embedding_meta = {
        "mode": mode,
        "model": embedding_info["model"],
        "dim": embedding_info["dim"],
        "built_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    with open(os.path.join(out_dir, "embedding_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(embedding_meta, fh, ensure_ascii=False, indent=2, sort_keys=True)

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
        "retrieval_mode": mode,
        "embedding_model": settings.afs_embedding_model,
        "library_versions": _lib_versions(),
        "counts": {
            "evidence": len(evidence),
            "reference_records": len(references),
            "catalog_entries": len(entries),
            "present_sources": len(present_ids),
            "missing_sources": len(entries) - len(present_ids),
        },
        "source_files": source_files,
    }
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)

    _log(
        f"done: {len(evidence)} evidence, {len(references)} reference_records, "
        f"{len(entries)} catalog entries -> {out_dir}"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Build the AFS knowledge index.")
    parser.add_argument(
        "--materials",
        default=str(settings.afs_source_dir),
        help="input material folder (default: Settings().afs_source_dir)",
    )
    parser.add_argument(
        "--out",
        default=str(settings.afs_index_dir),
        help="output index folder (default: Settings().afs_index_dir)",
    )
    args = parser.parse_args(argv)

    if not os.path.isdir(args.materials):
        _log(f"ERROR: materials dir not found: {args.materials}")
        return 2

    build(args.materials, args.out, settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
