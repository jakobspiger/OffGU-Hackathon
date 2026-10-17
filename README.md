# OffGU-Hackathon

AFS Spectroscopy Design Assistant — see `materials/STRATEGIEPAPIER_AFS_TEAM.md`
and `materials/CODEX_AGENT_MASTERPROMPT.md` for the overall project spec.

## T02 — AFS source ingestion & knowledge index

T02 turns the supplied AFS material into verifiable, separately categorised
evidence records and a documented source catalogue. It is **ingestion + index +
catalogue only** — no retrieval (T04), no rule matrix (T03), no few-shot usage
(T05), no LLM logic or UI.

### Layout

```
src/knowledge/
  types.py     # Evidence + SourceCatalogEntry + SourceKind (contract-compatible)
  catalog.py   # static verified source catalogue + check_materials()
  ingest.py    # five ingest_* functions + INDEXABLE_SOURCES allowlist
data/source_notes/s02_notes.yaml   # hand-verified notes for image-heavy S02 slides
scripts/build_index.py             # CLI that writes the local index
tests/                             # test_ingest.py, test_catalog.py
```

### Evidence kinds (strictly separated)

| kind                  | source                                             |
|-----------------------|----------------------------------------------------|
| `pdf_text`            | S01, S03, S04, BRIEF — one record per 1-based page |
| `verified_note`       | S02 key slides (6, 13–16), hand-verified           |
| `table_transcription` | `AFS_method_comparison_table.xlsx` (S01 Table 1 p.6) |
| `business_context`    | S05 flyer, S06 lab link (`page=None`)              |
| `dev_reference`       | `AFS_Examples_and_Reference.docx` (D01–D08) — written to a **separate** file, never in the evidence index |

Citations render as `S01 p.10`, range `S01 p.14–15`, table `S01 Table 1 (p.6)`,
slide `S02 p.13`. Pages are **1-based**, counting the title page.

`customer_scenarios_for_final_evaluation.txt` (H01–H06) and the QA-schedule PDFs
are **never** indexed (enforced by the `INDEXABLE_SOURCES` allowlist and a test
that reads H signatures from the file at runtime).

### Where the AFS material comes from (local provisioning)

Redistribution rights for the AFS PDFs/papers are not assumed. The build reads
from a material folder you provide; nothing proprietary is committed:

* Keep the originals in `materials/` locally (already present in this repo for
  the team), or place them under `data/source/` — both are git-ignored for the
  raw-source path (`data/source/`).
* The index under `data/index/` is **reproducible** from those files and is
  git-ignored; rebuild it with the command below rather than committing it.

### Build the index

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt            # pymupdf, python-docx, openpyxl, pydantic
python scripts/build_index.py --materials materials --out data/index
```

This writes `evidence.jsonl`, `dev_reference.jsonl`, `catalog.json` and
`manifest.json` (UTC timestamp, source sizes + sha256 hashes, library versions,
record counts — no secrets). The script is idempotent and logs (not fatal) any
missing input.

### Tests

```bash
python -m pytest tests/ -v
```

The suite runs **without** PyMuPDF / python-docx / openpyxl / pydantic
installed: pure logic (chunk ids, YAML note parsing, business context,
allowlist, schema shape) is tested on fixtures, and the library-dependent paths
are guarded with `pytest.importorskip`.

### Known limitation (environment)

PyPI is blocked in the CI/authoring sandbox, so `pip install pymupdf/
python-docx/openpyxl/pydantic` fails there and the real index build must be run
locally. The S02 slide notes are a reviewed transcription from the official
source catalogue and carry a `needs_visual_check` TODO: do a final visual check
of the rendered slides 6 and 13–16 locally before relying on them.
