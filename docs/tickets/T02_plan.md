# T02 — AFS-Quellen aufbereiten · Umsetzungsplan

> Basiert auf `T02_analysis.md`. Reihenfolge = Implementierungsreihenfolge.
> Ziel: AFS-Material → überprüfbare, getrennt kategorisierte Evidenzsätze als lokaler
> JSONL-Index, mit dokumentiertem Quellenkatalog. **Kein Retrieval** (das ist T04).

## Zerlegung in Einzelteile

T02 zerfällt in **7 Arbeitspakete (AP)**:

### AP0 — Projekt-Mini-Skelett (nur so viel wie T02 braucht)
- `requirements.txt` mit den T02-Abhängigkeiten (`pymupdf`, `python-docx`, `openpyxl`, `pydantic`) — pinned.
- `.gitignore` (venv, `__pycache__`, `.env`, gebaute Index-Artefakte unter `data/index/`).
- `.env.example` (nur Platzhalter, keine Secrets).
- `src/__init__.py`, `src/knowledge/__init__.py`.
- **Grund:** T01 fehlt noch; wir legen nur das Minimum an und überschreiben nichts, was T01 besitzen wird (`src/models.py` bleibt unangetastet).

### AP1 — Datentypen für Evidenz & Katalog (`src/knowledge/types.py`)
- Pydantic-Modelle, kompatibel zum Interface-Vertrag:
  - `Evidence` {`source_id`, `page: int|None`, `text`, `kind`, `chunk_id`(stabil), optional `score`}.
  - `SourceKind` Enum: `pdf_text`, `verified_note`, `table_transcription`, `dev_reference`, `business_context`.
  - `SourceCatalogEntry` {`source_id`, `filename`, `present: bool`, `kind`, `rank`, `pages`, `description`, `citation_hint`}.
- **Grund:** eigenes, kleines Typmodul, damit T01 später `Evidence` in `src/models.py` zentralisieren kann, ohne dass T02 blockiert ist. Ein Kommentar markiert die Stelle als „T01 übernimmt das später".

### AP2 — Quellenkatalog (`src/knowledge/catalog.py`)
- Statischer, geprüfter Katalog S01–S06 + BRIEF + XLSX + DOCX, **wörtlich abgeleitet aus DOCX-Abschnitt 4** (Inhalt, Seiten, Zitierregeln, Quellenrang).
- Funktion `check_materials(materials_dir) -> list[SourceCatalogEntry]`: markiert vorhandene vs. fehlende Dateien (Basenames), **erfindet keinen Inhalt fehlender Dateien**.
- Enthält die Zitier-Metadaten (`S01 p.X`, `S01 Table 1 (p.6)`, `S02 p.13`).

### AP3 — Ingestion-Kern (`src/knowledge/ingest.py`)
Fünf getrennte, testbare Funktionen — je Quelle eine klare Strategie:
- `ingest_pdf_text(path, source_id)` → PyMuPDF, 1 Evidenzsatz **pro Seite**, 1-basiert, `kind=pdf_text`. Für **S01, S03, S04, BRIEF**.
- `ingest_verified_s02_notes()` → lädt **manuell geprüfte** Slide-Notizen aus `data/source_notes/s02_notes.yaml`, `kind=verified_note`, Seiten 6/13/14/15/16 (+ generelle Seiten soweit belegt). Jede Note trägt `provenance: "visually reviewed against S02; cross-checked with AFS source catalog"`.
- `ingest_table_xlsx(path)` → openpyxl, beide Sheets; `method_comparison`-Zeilen als strukturierter Text, `kind=table_transcription`, Zitat `S01 Table 1 (p.6)`; Ratings explizit als „qualitative" gekennzeichnet.
- `ingest_dev_reference_docx(path)` → python-docx; **nur** als `kind=dev_reference` markiert (D01–D08 + Musterantworten) — **getrennt** gespeichert, NICHT in den Fach-Evidenzindex (T05 nutzt das später). In T02 nur extrahieren + separat ablegen.
- `ingest_business_context()` → S05 (Flyer, bildlastig → Titel/Metadaten + `verified_note`), S06 (`page=None`, URL-Text), `kind=business_context`.
- **Harte Allowlist:** eine Konstante `INDEXABLE_SOURCES` steuert, was in den Fachindex darf. `customer_scenarios_for_final_evaluation.txt` und die QA-Schedule-PDFs sind **nicht** enthalten.

### AP4 — S02-Notizdatei (`data/source_notes/s02_notes.yaml`)
- Von Hand gepflegte, als geprüft markierte Notizen für die Schlüssel-Slides, Inhalt **nur** aus dem offiziellen DOCX-Quellenkatalog abgeleitet:
  - p.6–10 Fasertypen & Transmissionsbereiche, p.13 Wasser in Petroleum, p.14 API in Polymerextrusion, p.15–16 Kombiproben.
- Klar als Transkription/Review-Notiz gekennzeichnet; **kein** erfundener Messwert.
- **Offene Grenze dokumentiert:** da PyMuPDF hier in der Sandbox nicht lauffähig ist, ist eine finale *visuelle* Gegenprüfung der gerenderten Slides durch Kevin lokal vorgesehen (als TODO im File vermerkt).

### AP5 — Build-Skript (`scripts/build_index.py`)
- CLI: `python scripts/build_index.py --materials materials --out data/index`.
- Ruft Katalogprüfung + alle Ingestion-Funktionen auf, schreibt:
  - `data/index/evidence.jsonl` (Fach-Evidenz: S01–S04 Text, S02 Notes, XLSX, S05/S06 Kontext).
  - `data/index/dev_reference.jsonl` (D01–D08 / Musterantworten, **separat**).
  - `data/index/catalog.json` (Quellenkatalog inkl. fehlender Dateien).
  - `data/index/manifest.json` (Zeitstempel UTC, Quelldateien + Größen/Hashes, Lib-Versionen, Anzahl Sätze) — Reproduzierbarkeit, keine Secrets.
- Deterministische `chunk_id` (z. B. `S01-p010` / `XLSX-row03` / `S02-note-p13`).
- Idempotent; klare Fehlermeldung bei fehlender Datei (bricht nicht hart ab, protokolliert).

### AP6 — Tests (`tests/test_ingest.py`, `tests/test_catalog.py`)
- `test_catalog_reports_missing_and_present` — Allowlist & present/missing korrekt.
- `test_no_h_scenarios_in_index` — **kritisch**: charakteristische H01–H06-Phrasen dürfen in `evidence.jsonl` nicht vorkommen (liest H-Textsignaturen zur Laufzeit aus der Datei, hardcodet keine Szenariologik).
- `test_pages_are_1_based_and_have_source_id` — Schema-Form jeder Evidenz.
- `test_kinds_are_separated` — Primärevidenz ≠ Transkription ≠ dev_reference; dev_reference nicht in `evidence.jsonl`.
- `test_s06_has_no_page` — `page is None`, `kind=business_context`.
- `test_table_ratings_marked_qualitative`.
- Tests laufen auf **Fixture-Daten**, wo PyMuPDF nötig wäre, damit sie auch ohne installierte Lib grün werden können; Ingestion-Funktionen werden mit kleinen Mini-Inputs getestet.

## Interface-Verträglichkeit (damit T01/T04 andocken können)

- `Evidence` hält exakt die Felder des Masterprompt-Vertrags (`source_id, page, text, score`) + additive Felder (`kind`, `chunk_id`), die T04/T01 ignorieren oder übernehmen können.
- Output-Format `evidence.jsonl` = eine JSON-Zeile pro Evidenzsatz → genau das, was T04 (`retrieve`) als Korpus einliest.
- Keine Funktionsnamen aus dem Vertrag (`analyze`, `retrieve`) werden hier belegt/überschrieben.

## Was T02 bewusst NICHT tut (Scope-Grenze)

- **Kein** Retrieval/kein Vektor-Index (→ T04).
- **Keine** Regel-Matrix (→ T03).
- **Keine** Few-Shot-Nutzung der D01/D02-Antworten als Fachwissen (→ T05).
- **Keine** LLM-Logik, UI, Orchestrierung.

## Definition of Done für T02

- `python scripts/build_index.py` erzeugt `evidence.jsonl`, `dev_reference.jsonl`, `catalog.json`, `manifest.json` (lokal bei Kevin, wo PyMuPDF installierbar ist).
- `pytest tests/test_ingest.py tests/test_catalog.py` grün.
- Quellenkatalog listet vorhandene **und** fehlende Dateien.
- S02-Schlüsselnotizen vorhanden und als geprüft markiert.
- Nachweislich **keine** H01–H06-Inhalte im Fachindex.
- README-Notiz / Docstring zu Materialbezug & lokalem Bereitstellungsweg.

## Risiken & offene Punkte

| Punkt | Umgang |
|---|---|
| PyMuPDF in Sandbox nicht installierbar | Code wird vollständig geschrieben + per Fixtures getestet; realer Indexbau durch Kevin lokal (`pip install -r requirements.txt && python scripts/build_index.py`). Als offene Grenze im PR dokumentiert. |
| S02-Notizen nicht final visuell geprüft | TODO im YAML + PR-Hinweis; Inhalt konservativ aus dem offiziellen Katalog, kein erfundener Messwert. |
| Weitergaberecht AFS-PDFs | Index nachbaubar, Setup dokumentiert lokalen Ablageweg; keine Rechteannahme. |
| T01 kommt später und zentralisiert `Evidence` | `types.py` additiv & kompatibel gehalten; Migrationshinweis im Code. |
