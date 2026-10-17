"""Shared contract types for AFS ingestion (re-export from ``src.models``).

T01 interface note
------------------
T01 (project foundations) centralises the data contract in ``src/models.py``.
Per the binding handover (``docs/t02-handover.md``) this module must NOT define
a second ``Evidence`` model or a stdlib dataclass fallback: it only re-exports
the shared contract types. Pydantic is an installed production dependency
(``pyproject.toml`` / ``uv.lock``).

The old T02 ``SourceKind`` enum may survive INTERNALLY as a migration aid, but
it never leaves this package untranslated: :data:`KIND_PURPOSE_BY_SOURCE_KIND`
maps every historical kind to the shared contract ``(kind, purpose)`` values
before any record is constructed. Output always carries the contract values
(``pdf`` / ``curated_note`` / ``text`` / ``table_transcription`` and
``technical`` / ``research`` / ``business_context``).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from src.models import (
    Evidence,
    ReferenceRecord,
    SourceCatalogEntry,
    SourceReference,
)


class SourceKind(str, Enum):
    """Historical T02 kinds, kept as an internal migration aid only.

    These values never appear in output. They are translated to the shared
    contract ``(kind, purpose)`` via :data:`KIND_PURPOSE_BY_SOURCE_KIND` before
    any :class:`Evidence` / :class:`ReferenceRecord` is built.
    """

    pdf_text = "pdf_text"
    verified_note = "verified_note"
    table_transcription = "table_transcription"
    dev_reference = "dev_reference"
    business_context = "business_context"


# Internal mapping: historical kind -> shared contract (kind, purpose).
# ``purpose`` is intentionally ``None`` where it depends on the concrete source
# (e.g. S01 technical vs. S03/S04 research); callers resolve it explicitly.
KIND_PURPOSE_BY_SOURCE_KIND: dict[SourceKind, tuple[str, str | None]] = {
    SourceKind.pdf_text: ("pdf", None),
    SourceKind.verified_note: ("curated_note", None),
    SourceKind.table_transcription: ("table_transcription", "technical"),
    SourceKind.business_context: ("curated_note", "business_context"),
    # dev_reference no longer maps to Evidence at all: BRIEF/DOCX become
    # ReferenceRecord. Kept here only so the enum stays exhaustive.
    SourceKind.dev_reference: ("reference", None),
}


def to_dict(model: Any) -> dict[str, Any]:
    """Return a plain JSON-serialisable dict for a contract model."""

    return model.model_dump()


__all__ = [
    "Evidence",
    "SourceReference",
    "ReferenceRecord",
    "SourceCatalogEntry",
    "SourceKind",
    "KIND_PURPOSE_BY_SOURCE_KIND",
    "to_dict",
]
