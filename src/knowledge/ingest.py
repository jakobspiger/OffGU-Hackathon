"""Ingestion of AFS material into the shared T01 contract.

Each public ``ingest_*`` function returns records built against ``src.models``:
primary PDF text, curated S02 notes, the spreadsheet transcription and business
context become :class:`Evidence`; the challenge brief (BRIEF) and the
development reference (DOCX) become :class:`ReferenceRecord` and are kept out of
the technical evidence index.

Every record is built through a small helper constructor so the field
combinations the T01 validators enforce cannot drift:

    * :func:`make_pdf_evidence`       - S01 (technical) / S03,S04 (research)
    * :func:`make_table_evidence`     - XLSX -> source_id=S01, page=6, origin=XLSX
    * :func:`make_note_evidence`      - S02 curated notes (pending_visual_check)
    * :func:`make_business_evidence`  - S05 flyer (curated_note) / S06 link (text)
    * :func:`make_reference_record`   - BRIEF / DOCX reference text

Stable evidence ids keep their historical values (``S01-p010``, ``XLSX-row03``,
``S02-note-p13``, ``S05-context``, ``S06-context``) under the contract field
name ``evidence_id``.

Production dependencies (PyMuPDF as ``fitz``, ``python-docx``, ``openpyxl``,
PyYAML, pydantic) are installed via ``pyproject.toml`` / ``uv.lock`` and
resolved with ``uv sync --locked``. PyMuPDF / python-docx / openpyxl are
imported lazily inside the functions that need them; the real index build runs
locally on the maintainer's machine.

Allowlist
---------
``INDEXABLE_SOURCES`` is the hard allowlist of source_ids that may enter the
technical evidence index. BRIEF is NOT in it anymore (it is a ReferenceRecord).
It deliberately EXCLUDES:
    * customer_scenarios_for_final_evaluation.txt (H01-H06, final batch input)
    * the QA-schedule PDFs (organisational, no technical evidence)
    * the development reference DOCX (stored separately as a ReferenceRecord)
"""

from __future__ import annotations

import os
import re
from typing import Any, Literal

from . import catalog
from .types import Evidence, ReferenceRecord

# ---------------------------------------------------------------------------
# Allowlist: which source_ids may enter data/index/evidence.jsonl.
# BRIEF and DOCX are ReferenceRecords and are intentionally NOT here.
# ---------------------------------------------------------------------------
INDEXABLE_SOURCES: frozenset[str] = frozenset({"S01", "S02", "S03", "S04", "S05", "S06", "XLSX"})

# PDF sources ingested page-by-page as plain text (kind="pdf").
# Keyed by source_id. S01 is primary-technical; S03/S04 are research.
PDF_TEXT_SOURCES: dict[str, str] = {
    "S01": "S01_Multispectral_Laboratory.pdf",
    "S03": "S03_LED_Kidney_Study_2017.pdf",
    "S04": "S04_Combi_MIR_Fluorescence_2021.pdf",
}

# The challenge brief: no longer evidence, kept as a ReferenceRecord.
BRIEF_FILENAME = "AI-based molecular media analysis by process-spectroscopy in-line.pdf"

# Which PDF purpose each page-text source carries (the validator rejects
# S03/S04 with purpose!="research").
PDF_PURPOSE: dict[str, Literal["technical", "research"]] = {
    "S01": "technical",
    "S03": "research",
    "S04": "research",
}

# Files that must NEVER be indexed, regardless of anything else.
EXCLUDED_FROM_INDEX: frozenset[str] = frozenset(
    {
        "customer_scenarios_for_final_evaluation.txt",
        "Spectroscopy_Assistant_QA_schedule_17_October.pdf",
        "Spectroscopy_Assistant_QA_schedule_17_October (1).pdf",
    }
)

S06_URL = "https://mirphotonics.com/laboratory/"
S02_NOTES_DEFAULT = os.path.join("data", "source_notes", "s02_notes.yaml")

# review_note convention (migration plan V-3): machine-readable enough for T10
# to pick up open visual checks later.
S02_REVIEW_NOTE = "pending visual check; reviewer=tbd; method=rendered-slide vs source-catalog"


# ---------------------------------------------------------------------------
# Stable evidence-id helpers (deterministic, no hashing needed).
# ---------------------------------------------------------------------------
def pdf_evidence_id(source_id: str, page: int) -> str:
    """e.g. ``S01-p010`` (1-based, zero-padded to 3 digits)."""

    return f"{source_id}-p{page:03d}"


def table_evidence_id(row_index: int) -> str:
    """e.g. ``XLSX-row03`` (1-based data-row index, zero-padded to 2 digits)."""

    return f"XLSX-row{row_index:02d}"


def table_note_evidence_id(sheet: str) -> str:
    """e.g. ``XLSX-notes-notes`` for the provenance ``notes`` sheet."""

    return f"XLSX-notes-{sheet}"


def s02_note_evidence_id(page: int) -> str:
    """e.g. ``S02-note-p13``."""

    return f"S02-note-p{page}"


def business_evidence_id(source_id: str) -> str:
    """e.g. ``S05-context`` / ``S06-context``."""

    return f"{source_id}-context"


def reference_record_id(source_id: str, index: int) -> str:
    """e.g. ``BRIEF-p01`` / ``DOCX-p0001`` (stable, zero-padded)."""

    width = 2 if source_id == "BRIEF" else 4
    return f"{source_id}-p{index:0{width}d}"


# ---------------------------------------------------------------------------
# Helper constructors: the single place that sets contract field combinations.
# ---------------------------------------------------------------------------
def make_pdf_evidence(source_id: str, page: int, text: str) -> Evidence:
    """Build a page-text Evidence (kind="pdf").

    S01 is ``purpose="technical"``; S03/S04 are ``purpose="research"`` (the
    T01 validator rejects S03/S04 that claim a technical scope). ``source_id``
    and ``origin_source_id`` are identical for page text.
    """

    purpose = PDF_PURPOSE.get(source_id, "technical")
    return Evidence(
        evidence_id=pdf_evidence_id(source_id, page),
        source_id=source_id,
        page=page,
        origin_source_id=source_id,
        text=text,
        kind="pdf",
        purpose=purpose,
        review_status="unreviewed",
    )


def make_table_evidence(evidence_id: str, text: str) -> Evidence:
    """Build an XLSX transcription Evidence with the three fields hard-set.

    The T01 validator requires exactly ``(source_id="S01", page=6,
    origin_source_id="XLSX")`` for ``kind="table_transcription"``; setting them
    in one place means the mapping cannot drift.
    """

    return Evidence(
        evidence_id=evidence_id,
        source_id="S01",
        page=6,
        origin_source_id="XLSX",
        text=text,
        kind="table_transcription",
        purpose="technical",
        review_status="unreviewed",
    )


def make_note_evidence(page: int, text: str) -> Evidence:
    """Build a curated S02 slide note (kind="curated_note", technical).

    Review status stays ``pending_visual_check`` with a documented
    ``review_note`` until the maintainer's local visual check of the rendered
    slide. The old name/text "verified" hack is gone: the status field is the
    only proof of review, never a text prefix.
    """

    return Evidence(
        evidence_id=s02_note_evidence_id(page),
        source_id="S02",
        page=page,
        origin_source_id="S02",
        text=text,
        kind="curated_note",
        purpose="technical",
        review_status="pending_visual_check",
        review_note=S02_REVIEW_NOTE,
    )


def make_business_evidence(source_id: str, text: str) -> Evidence:
    """Build S05 flyer / S06 link business-context Evidence.

    S05 is ``kind="curated_note"``, ``page=1`` (the validator forbids S05
    ``kind="text"`` and forbids S05 ``purpose="technical"``). S06 is
    ``kind="text"``, ``page=None`` (only S06 may use ``kind="text"``). Both are
    ``purpose="business_context"``.
    """

    if source_id == "S05":
        return Evidence(
            evidence_id=business_evidence_id("S05"),
            source_id="S05",
            page=1,
            origin_source_id="S05",
            text=text,
            kind="curated_note",
            purpose="business_context",
            review_status="unreviewed",
        )
    if source_id == "S06":
        return Evidence(
            evidence_id=business_evidence_id("S06"),
            source_id="S06",
            page=None,
            origin_source_id="S06",
            text=text,
            kind="text",
            purpose="business_context",
            review_status="unreviewed",
        )
    raise ValueError(f"business context is only defined for S05/S06, got {source_id!r}")


def make_reference_record(
    source_id: Literal["BRIEF", "DOCX"], index: int, text: str, page: int | None = None
) -> ReferenceRecord:
    """Build a BRIEF/DOCX ReferenceRecord (kept out of evidence.jsonl)."""

    return ReferenceRecord(
        record_id=reference_record_id(source_id, index),
        source_id=source_id,
        text=text,
        page=page,
    )


# ---------------------------------------------------------------------------
# AP3.1 - PDF page text (PyMuPDF). Used for S01, S03, S04.
# ---------------------------------------------------------------------------
def ingest_pdf_text(path: str | os.PathLike[str], source_id: str) -> list[Evidence]:
    """Ingest one evidence record per PDF page (1-based), kind="pdf".

    Requires PyMuPDF (imported as ``fitz``). Raises ``ModuleNotFoundError`` if
    the library is unavailable, so the caller can report the environment gap.
    """

    import fitz  # PyMuPDF; lazily imported (not installable in sandbox)

    records: list[Evidence] = []
    with fitz.open(os.fspath(path)) as doc:
        for zero_based, pymupdf_page in enumerate(doc):
            page = zero_based + 1  # 1-based, counting the title page
            text = pymupdf_page.get_text("text").strip()
            if not text:
                # Image-only page: keep a placeholder so the page still exists
                # in the index, but do not invent content.
                text = f"[no extractable text on {source_id} p.{page}]"
            records.append(make_pdf_evidence(source_id, page, text))
    return records


# ---------------------------------------------------------------------------
# AP3.2 - Curated S02 slide notes (hand-written YAML).
# ---------------------------------------------------------------------------
def _parse_s02_notes_yaml(raw: str) -> dict[str, Any]:
    """Minimal parser for the specific s02_notes.yaml structure.

    Production uses PyYAML (``yaml.safe_load``); this fallback understands only
    the subset of YAML the notes file uses: a ``meta`` mapping and a ``notes``
    list of ``page/title/text`` entries with folded (``>-``) scalars. It lets
    the tests run without PyYAML installed.
    """

    try:
        import yaml  # type: ignore

        return yaml.safe_load(raw) or {}
    except ModuleNotFoundError:
        pass

    data: dict[str, Any] = {"meta": {}, "notes": []}
    lines = raw.splitlines()
    i = 0
    n = len(lines)

    # --- meta block ---
    while i < n:
        line = lines[i]
        if line.strip().startswith("#") or not line.strip():
            i += 1
            continue
        if line.rstrip() == "meta:":
            i += 1
            while (
                i < n
                and (lines[i].startswith("  ") and ":" in lines[i])
                and not lines[i].lstrip().startswith("#")
            ):
                key, _, val = lines[i].strip().partition(":")
                val = val.strip().strip('"')
                if val in ("true", "false"):
                    data["meta"][key] = val == "true"
                else:
                    data["meta"][key] = val
                i += 1
            continue
        if line.rstrip() == "notes:":
            i += 1
            break
        i += 1

    # --- notes list ---
    current: dict[str, Any] | None = None
    while i < n:
        raw_line = lines[i]
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            i += 1
            continue
        m = re.match(r"^\s*-\s*page:\s*(\d+)\s*$", raw_line)
        if m:
            if current:
                data["notes"].append(current)
            current = {"page": int(m.group(1))}
            i += 1
            continue
        if current is not None:
            tm = re.match(r'^\s*title:\s*"?(.*?)"?\s*$', raw_line)
            if tm:
                current["title"] = tm.group(1)
                i += 1
                continue
            if re.match(r"^\s*text:\s*>-?\s*$", raw_line):
                # Folded scalar: gather deeper-indented lines.
                base_indent = len(raw_line) - len(raw_line.lstrip())
                i += 1
                parts: list[str] = []
                while i < n:
                    nxt = lines[i]
                    if not nxt.strip():
                        i += 1
                        continue
                    indent = len(nxt) - len(nxt.lstrip())
                    if indent <= base_indent:
                        break
                    parts.append(nxt.strip())
                    i += 1
                current["text"] = " ".join(parts)
                continue
        i += 1
    if current:
        data["notes"].append(current)
    return data


def ingest_curated_s02_notes(
    notes_path: str | os.PathLike[str] = S02_NOTES_DEFAULT,
) -> list[Evidence]:
    """Load curated S02 slide notes, kind="curated_note".

    Each note is ``review_status="pending_visual_check"`` with a documented
    ``review_note`` (set inside :func:`make_note_evidence`). Graceful on a
    missing file: returns an empty list.
    """

    notes_path = os.fspath(notes_path)
    if not os.path.isfile(notes_path):
        return []

    with open(notes_path, encoding="utf-8") as fh:
        data = _parse_s02_notes_yaml(fh.read())

    records: list[Evidence] = []
    for note in data.get("notes", []) or []:
        page = note.get("page")
        title = (note.get("title") or "").strip()
        body = (note.get("text") or "").strip()
        text = f"{title}. {body}" if title else body
        records.append(make_note_evidence(page, text))
    return records


# Backwards-compatible alias (the records are no longer "verified", they are
# pending_visual_check; the status field carries that, not the name).
ingest_verified_s02_notes = ingest_curated_s02_notes


# ---------------------------------------------------------------------------
# AP3.3 - Spreadsheet transcription (openpyxl). S01 Table 1 (p.6).
# ---------------------------------------------------------------------------
def _format_table_row(headers: list[str], values: list[Any]) -> str:
    pairs = []
    for h, v in zip(headers, values, strict=False):
        if v is None or str(v).strip() == "":
            continue
        pairs.append(f"{h}={v}")
    return "; ".join(pairs)


def ingest_table_xlsx(path: str | os.PathLike[str]) -> list[Evidence]:
    """Ingest the method-comparison spreadsheet, kind="table_transcription".

    Emits one record per data row of ``method_comparison`` plus records for the
    ``notes`` sheet. All records cite ``S01 Table 1 (p.6)`` (via
    :func:`make_table_evidence`) and flag the sensitivity/selectivity/cost
    ratings as qualitative, never as measured specifications. Requires openpyxl.
    """

    from openpyxl import load_workbook  # lazily imported (not in sandbox)

    QUALIFIER = (
        " [transcription of S01 Table 1 (p.6); sensitivity/selectivity/cost are "
        "qualitative ratings (low/average/high), not measured specifications]"
    )

    wb = load_workbook(os.fspath(path), read_only=True, data_only=True)
    records: list[Evidence] = []

    if "method_comparison" in wb.sheetnames:
        ws = wb["method_comparison"]
        rows = list(ws.iter_rows(values_only=True))
        if rows:
            headers = [str(h).strip() if h is not None else "" for h in rows[0]]
            data_index = 0
            for row in rows[1:]:
                if row is None or all(c is None for c in row):
                    continue
                data_index += 1
                text = _format_table_row(headers, list(row)) + QUALIFIER
                records.append(make_table_evidence(table_evidence_id(data_index), text))

    if "notes" in wb.sheetnames:
        ws = wb["notes"]
        note_lines = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                note_lines.append(" ".join(cells))
        if note_lines:
            text = " ".join(note_lines) + QUALIFIER
            records.append(make_table_evidence(table_note_evidence_id("notes"), text))

    wb.close()
    return records


# ---------------------------------------------------------------------------
# AP3.4 - Challenge brief + development reference -> ReferenceRecord.
# These are NOT scientific evidence and never enter evidence.jsonl.
# ---------------------------------------------------------------------------
def ingest_brief_reference(path: str | os.PathLike[str]) -> list[ReferenceRecord]:
    """Extract the challenge brief (BRIEF) PDF as ReferenceRecords (one/page).

    BRIEF is the authoritative task definition, not technical evidence, so it
    is stored as :class:`ReferenceRecord`. Requires PyMuPDF.
    """

    import fitz  # PyMuPDF; lazily imported (not installable in sandbox)

    records: list[ReferenceRecord] = []
    with fitz.open(os.fspath(path)) as doc:
        for zero_based, pymupdf_page in enumerate(doc):
            page = zero_based + 1
            text = pymupdf_page.get_text("text").strip()
            if not text:
                text = f"[no extractable text on BRIEF p.{page}]"
            records.append(make_reference_record("BRIEF", page, text, page=page))
    return records


def ingest_dev_reference_docx(path: str | os.PathLike[str]) -> list[ReferenceRecord]:
    """Extract the development reference DOCX as ReferenceRecords.

    Returns paragraph-level records (source_id="DOCX") so later tickets (T05
    few-shot) can use them. Kept out of the technical evidence index. Requires
    python-docx.
    """

    import docx  # python-docx; lazily imported (not installable in sandbox)

    document = docx.Document(os.fspath(path))
    records: list[ReferenceRecord] = []
    index = 0
    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        index += 1
        records.append(make_reference_record("DOCX", index, text))
    return records


# ---------------------------------------------------------------------------
# AP3.5 - Business context: S05 flyer + S06 link.
# ---------------------------------------------------------------------------
def ingest_business_context(
    materials_dir: str | os.PathLike[str],
) -> list[Evidence]:
    """Ingest S05 (flyer) and S06 (link) as business context.

    S06 is a URL, not a PDF page, so its evidence has ``page=None`` and
    ``kind="text"``. S05 is an image-heavy flyer: only its catalog description
    is recorded (``kind="curated_note"``), no invented content. Graceful on
    missing files.
    """

    materials_dir = os.fspath(materials_dir)
    records: list[Evidence] = []

    # S05 - flyer (image-heavy). Use the verified catalog description only.
    s05 = catalog.get_entry("S05")
    s05_path = os.path.join(materials_dir, s05.filename) if s05 else None
    if s05 and s05_path and os.path.isfile(s05_path):
        records.append(
            make_business_evidence(
                "S05",
                (
                    f"{s05.description} [business context only; image-heavy flyer, "
                    "not evidence of technical performance]"
                ),
            )
        )

    # S06 - laboratory link (URL only, not a PDF page => page=None).
    s06 = catalog.get_entry("S06")
    s06_path = os.path.join(materials_dir, s06.filename) if s06 else None
    url = S06_URL
    if s06_path and os.path.isfile(s06_path):
        try:
            with open(s06_path, encoding="utf-8") as fh:
                content = fh.read().strip()
            if content:
                url = content.splitlines()[0].strip()
        except OSError:
            pass
    if s06:
        records.append(
            make_business_evidence("S06", f"AFS laboratory website: {url} [business context only]")
        )

    return records


__all__ = [
    "INDEXABLE_SOURCES",
    "PDF_TEXT_SOURCES",
    "PDF_PURPOSE",
    "BRIEF_FILENAME",
    "EXCLUDED_FROM_INDEX",
    "S06_URL",
    "S02_REVIEW_NOTE",
    "pdf_evidence_id",
    "table_evidence_id",
    "table_note_evidence_id",
    "s02_note_evidence_id",
    "business_evidence_id",
    "reference_record_id",
    "make_pdf_evidence",
    "make_table_evidence",
    "make_note_evidence",
    "make_business_evidence",
    "make_reference_record",
    "ingest_pdf_text",
    "ingest_curated_s02_notes",
    "ingest_verified_s02_notes",
    "ingest_table_xlsx",
    "ingest_brief_reference",
    "ingest_dev_reference_docx",
    "ingest_business_context",
]
