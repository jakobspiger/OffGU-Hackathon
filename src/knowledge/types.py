"""Data types for AFS evidence and the source catalog.

T01 interface note
------------------
T01 (project foundations) will later centralise the ``Evidence`` type in
``src/models.py``. This module is intentionally additive and kept compatible
with the master-prompt contract::

    class Evidence(BaseModel):
        source_id: str
        page: int | None = None
        text: str
        score: float | None = None

We add two non-breaking fields, ``kind`` and ``chunk_id``, which T01/T04 can
either adopt or ignore. When T01 lands, ``Evidence`` here should be replaced by
an import from ``src.models`` and the extra fields folded into that definition.

Pydantic is the production dependency (see requirements.txt). In environments
where pydantic is not installed (e.g. the offline sandbox used to author this
ticket), the module degrades to a small stdlib dataclass implementation that
exposes the same construction signature and a ``model_dump()`` method, so the
ingestion logic and tests run without the heavyweight dependency.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class SourceKind(str, Enum):
    """How a piece of evidence relates to the primary AFS material.

    Keeping these separated is a hard requirement of the ticket: primary PDF
    text, hand-verified slide notes, the spreadsheet transcription, the
    development reference (D01-D08) and business context must never be conflated.
    """

    pdf_text = "pdf_text"
    verified_note = "verified_note"
    table_transcription = "table_transcription"
    dev_reference = "dev_reference"
    business_context = "business_context"


try:  # Production path: pydantic is pinned in requirements.txt.
    from pydantic import BaseModel, Field

    _HAVE_PYDANTIC = True

    class Evidence(BaseModel):
        """A single, citable evidence record.

        Contract fields (``source_id``, ``page``, ``text``, ``score``) match the
        master prompt. ``kind`` and ``chunk_id`` are additive.
        """

        source_id: str
        page: Optional[int] = None
        text: str
        kind: SourceKind
        chunk_id: str
        score: Optional[float] = None

    class SourceCatalogEntry(BaseModel):
        """A verified catalog entry describing one input material."""

        source_id: str
        filename: str
        present: bool
        kind: SourceKind
        rank: str
        pages: Optional[str] = None
        description: str = ""
        citation_hint: str = ""

except ImportError:  # pragma: no cover - exercised only without pydantic
    _HAVE_PYDANTIC = False

    from dataclasses import asdict, dataclass, field

    def Field(default=None, **_kwargs):  # type: ignore[no-redef]
        return default

    def _coerce_kind(value: Any) -> SourceKind:
        return value if isinstance(value, SourceKind) else SourceKind(value)

    @dataclass
    class Evidence:  # type: ignore[no-redef]
        """stdlib fallback mirroring the pydantic ``Evidence`` model."""

        source_id: str
        text: str
        kind: SourceKind
        chunk_id: str
        page: Optional[int] = None
        score: Optional[float] = None

        def __post_init__(self) -> None:
            self.kind = _coerce_kind(self.kind)

        def model_dump(self) -> dict[str, Any]:
            data = asdict(self)
            data["kind"] = self.kind.value
            return data

    @dataclass
    class SourceCatalogEntry:  # type: ignore[no-redef]
        """stdlib fallback mirroring the pydantic ``SourceCatalogEntry`` model."""

        source_id: str
        filename: str
        present: bool
        kind: SourceKind
        rank: str
        pages: Optional[str] = None
        description: str = ""
        citation_hint: str = ""

        def __post_init__(self) -> None:
            self.kind = _coerce_kind(self.kind)

        def model_dump(self) -> dict[str, Any]:
            data = asdict(self)
            data["kind"] = self.kind.value
            return data


def to_dict(model: Any) -> dict[str, Any]:
    """Return a plain JSON-serialisable dict for an Evidence/catalog model.

    Works with both the pydantic models and the dataclass fallback.
    """

    return model.model_dump()


__all__ = [
    "SourceKind",
    "Evidence",
    "SourceCatalogEntry",
    "to_dict",
]
