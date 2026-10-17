"""Static, verified source catalog for the AFS material.

The catalog content is derived verbatim from section 4 ("AFS sources and
citations") of ``AFS_Examples_and_Reference.docx`` (the official source guide),
cross-checked with section 5 (method overview). Nothing here is invented: the
descriptions, page spans and citation rules all come from that document.

Citation rules (DOCX section 4, "How to cite"):
    * ``S01 p.10`` - 1-based PDF page, counting the title page.
    * ``S02 p.13`` - slide 13.
    * ``S01 Table 1 (p.6)`` - the comparison table.

``check_materials`` reports which expected inputs are present on disk (matched
by basename) and which are missing. It never invents content for a missing
file; a missing entry simply carries ``present=False`` with the verified,
static metadata so downstream code can report the gap.
"""

from __future__ import annotations

import os
from typing import Optional

from .types import SourceCatalogEntry, SourceKind

# ---------------------------------------------------------------------------
# Verified catalog metadata (DOCX section 4 + section 5). Keyed by source_id.
# Each tuple: (filename, kind, rank, pages, description, citation_hint)
# ---------------------------------------------------------------------------
_CATALOG: list[SourceCatalogEntry] = [
    SourceCatalogEntry(
        source_id="BRIEF",
        filename="AI-based molecular media analysis by process-spectroscopy in-line.pdf",
        present=False,
        kind=SourceKind.pdf_text,
        rank="task_definition",
        pages="1-2",
        description=(
            "Challenge brief: task definition, minimum requirements, evaluation "
            "criteria and deliverables (pp.1-2). Authoritative rules, not "
            "technical evidence."
        ),
        citation_hint="BRIEF p.1",
    ),
    SourceCatalogEntry(
        source_id="S01",
        filename="S01_Multispectral_Laboratory.pdf",
        present=False,
        kind=SourceKind.pdf_text,
        rank="primary_technical",
        pages="1-19",
        description=(
            "Overview of optical analysis methods and application examples. Main "
            "technical source. Methods p.2-6 (comparison table p.6), combining "
            "methods p.7-9, measurement kits and probes p.10-12, application cases "
            "p.13-18 (medical, pharmaceutical, bioprocess, dairy)."
        ),
        citation_hint="S01 p.10",
    ),
    SourceCatalogEntry(
        source_id="S02",
        filename="S02_AFS_Process_Control_Slides.pdf",
        present=False,
        kind=SourceKind.verified_note,
        rank="application_hardware_context",
        pages="1-20",
        description=(
            "AFS slides on process control: fiber types and transmission ranges "
            "(p.6-10), probes, application slides (water in petroleum p.13, API in "
            "polymer extrusion p.14), combined probes (p.15-16). Mostly images: "
            "PDF text extraction returns little, so the key slides are captured as "
            "hand-verified notes (see data/source_notes/s02_notes.yaml)."
        ),
        citation_hint="S02 p.13",
    ),
    SourceCatalogEntry(
        source_id="S03",
        filename="S03_LED_Kidney_Study_2017.pdf",
        present=False,
        kind=SourceKind.pdf_text,
        rank="research_proof_of_concept",
        pages=None,
        description=(
            "Research paper: LED-based NIR sensor for kidney tumour diagnostics, "
            "tested on 14 in vitro samples from 7 patients. A proof of concept; "
            "not evidence of surgical readiness."
        ),
        citation_hint="S03 p.1",
    ),
    SourceCatalogEntry(
        source_id="S04",
        filename="S04_Combi_MIR_Fluorescence_2021.pdf",
        present=False,
        kind=SourceKind.pdf_text,
        rank="research_proof_of_concept",
        pages=None,
        description=(
            "Research paper: fiber probe for simultaneous MIR (ATR) and "
            "fluorescence measurement, demonstrated on model biological tissues."
        ),
        citation_hint="S04 p.1",
    ),
    SourceCatalogEntry(
        source_id="S05",
        filename="S05_AFS_Flyer.pdf",
        present=False,
        kind=SourceKind.business_context,
        rank="business_context",
        pages="1-2",
        description=(
            "Company and product overview. Business context, not evidence of "
            "technical performance. Image-heavy flyer."
        ),
        citation_hint="S05 p.1",
    ),
    SourceCatalogEntry(
        source_id="S06",
        filename="S06_Laboratory_Link.txt",
        present=False,
        kind=SourceKind.business_context,
        rank="business_context",
        pages=None,
        description=(
            "Link to the laboratory website "
            "(https://mirphotonics.com/laboratory/). Business context. Not a PDF "
            "page, so evidence from this source has page=None."
        ),
        citation_hint="S06",
    ),
    SourceCatalogEntry(
        source_id="XLSX",
        filename="AFS_method_comparison_table.xlsx",
        present=False,
        kind=SourceKind.table_transcription,
        rank="primary_technical",
        pages="6",
        description=(
            "Machine-readable transcription of S01 Table 1 (p.6): method, "
            "measurement technique, physical phenomenon, sample type, optical "
            "path, qualitative sensitivity, selectivity and cost. The "
            "sensitivity/selectivity/cost ratings are qualitative "
            "(low/average/high), not measured specifications."
        ),
        citation_hint="S01 Table 1 (p.6)",
    ),
    SourceCatalogEntry(
        source_id="DOCX",
        filename="AFS_Examples_and_Reference.docx",
        present=False,
        kind=SourceKind.dev_reference,
        rank="development_reference",
        pages=None,
        description=(
            "Development reference: scenarios D01-D08, worked example answers for "
            "D01 and D02, quality rules and the official source catalogue. Stored "
            "SEPARATELY from technical evidence and used only by later tickets "
            "(T05 few-shot); never part of the primary evidence index."
        ),
        citation_hint="D01",
    ),
]

# Expected input basenames (master prompt "mandatory repo inspection" list),
# mapped to the catalog source_id. Used by check_materials and the allowlist.
EXPECTED_MATERIALS: dict[str, str] = {entry.filename: entry.source_id for entry in _CATALOG}


def source_catalog() -> list[SourceCatalogEntry]:
    """Return a fresh copy of the static, verified catalog (present=False)."""

    return [
        SourceCatalogEntry(
            source_id=e.source_id,
            filename=e.filename,
            present=e.present,
            kind=e.kind,
            rank=e.rank,
            pages=e.pages,
            description=e.description,
            citation_hint=e.citation_hint,
        )
        for e in _CATALOG
    ]


def get_entry(source_id: str) -> Optional[SourceCatalogEntry]:
    """Look up a single catalog entry by source_id, or None."""

    for entry in _CATALOG:
        if entry.source_id == source_id:
            return entry
    return None


def check_materials(materials_dir: str | os.PathLike[str]) -> list[SourceCatalogEntry]:
    """Report present vs. missing expected inputs by basename.

    Returns the verified catalog with the ``present`` flag set according to
    what is actually on disk in ``materials_dir``. Missing files keep their
    static metadata but ``present=False`` and no invented content.
    """

    materials_dir = os.fspath(materials_dir)
    entries = source_catalog()
    for entry in entries:
        candidate = os.path.join(materials_dir, entry.filename)
        entry.present = os.path.isfile(candidate)
    return entries


__all__ = [
    "source_catalog",
    "get_entry",
    "check_materials",
    "EXPECTED_MATERIALS",
]
