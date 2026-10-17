# T02 → T01-Vertrag · Migrationsplan (nach Kevins Freigabe)

> Kevin hat die Fixes freigegeben: beste Lösungen umsetzen, erst Plan, dann Code,
> am Ende `main` in den Branch mergen.
> Basis: `main` @ `67ff75a` (T01) + Handover `docs/t02-handover.md` +
> Contract-Test `tests/test_ingestion_contract.py` + die T01-Foundation-Tests.
> Dieser Plan ist die Entscheidung **zu jedem der 12 I-Punkte und 4 V-Punkte**
> aus `T02_T01_schnittstellen_review.md`.

## A. Entscheidungen zu den kritischen V-Rückfragen (recherchiert)

Die T01-Validatoren beantworten drei der vier Punkte eindeutig — ich habe sie
gegen die realen `@model_validator`-Regeln und Tests geprüft:

### [V-1] XLSX → `source_id="S01", page=6, origin_source_id="XLSX"`
**Entscheidung: T01-Vertrag übernehmen, mit Helper absichern.**
`Evidence.check_source_scope` erzwingt für `kind="table_transcription"` exakt
`(S01, 6, XLSX)` — jede Abweichung wirft `ValueError`. Das ist die beste Lösung
(zitiert wird faktisch S01 p.6, Herkunft bleibt nachvollziehbar). Fehlerrisiko
wird durch einen einzigen Konstruktor-Helper `make_table_evidence(row_index, text)`
eliminiert, der die drei Felder hart setzt. Jakobs `test_table_cannot_claim_
another_page` bleibt grün.

### [V-4] `curated_note` + `purpose` als Trenner für S02-Notiz vs. S05-Flyer
**Entscheidung: T01-Vertrag übernehmen; Validator erzwingt die Trennung bereits.**
`test_business_context_cannot_claim_technical_evidence` lehnt S05 mit
`purpose="technical"` ab; `(S06)!=(kind text)` verbietet S05 `kind="text"`.
→ S05 wird `kind="curated_note", purpose="business_context"`, S02-Notes
`kind="curated_note", purpose="technical"`. Ich sichere zusätzlich per eigenem
Test ab, dass S05 nie `purpose="technical"` erhält. Kein Vertragsänderungsbedarf.

### [V-3] `review_note`-Format
**Entscheidung: leichte, dokumentierte Konvention einführen (kein Vertragszwang).**
Modell verlangt nur „nicht leer". Ich schreibe die review_note der S02-Notes im
Format `pending visual check; reviewer=<tbd>; method=rendered-slide vs source-catalog`
und dokumentiere die Konvention in der README/Docstring, damit T10 sie später
maschinell lesen kann. Keine Modelländerung — das bleibt Jakobs Hoheit; ich
schlage die Konvention nur vor und wende sie an.

### [V-2] `ExtractedFact.verify_quotes` exakter Substring-Match
**Entscheidung: NICHT in T02 anfassen — als Team-Punkt an Jakob dokumentieren.**
Das betrifft T06 (Extraktor), nicht die Ingestion. Eine Vertragsänderung an
`src/models.py` wäre Jakobs Zuständigkeit und würde seine Foundation-Tests
berühren. Ich öffne dafür einen separaten Notizpunkt in der PR-Beschreibung
(„Empfehlung an T06: definierte Normalisierung vor Substring-Prüfung erwägen")
und ändere hier nichts. So bleibt die Schnittstelle sauber getrennt.

## B. Overlap-Auflösung (I11/I12) — welche Datei gewinnt

| Datei | Entscheidung |
|---|---|
| `.env.example` | **T01 behalten** (hat `AFS_*`-Settings, wird von `test_example_env_is_valid_and_offline` getestet). Meine Version löschen. |
| `.gitignore` | **vereinen**: T01-Basis + meine zusätzlichen Ausschlüsse sind bereits enthalten (`data/index/`, `.env`); nichts hinzuzufügen außer evtl. `data/reference/`. |
| `src/__init__.py`, `src/knowledge/__init__.py` | **T01-Fassung** (hat Docstrings) übernehmen; meine leeren überschreiben lassen. |
| `requirements.txt` | **löschen** (I9) — `pyproject.toml` + `uv.lock` sind die einzige Quelle. |
| `README.md` | **vereinen**: T01-Projektübersicht + Setup behalten, meine T02-Indexbau-Doku anfügen, falsche `materials/`-Ignoriert-Aussage streichen (I12). |
| `.python-version` | T01 (3.12). |

## C. Datenmodell-Mapping (I1–I8) — exakt nach Handover-Tabelle

`src/knowledge/types.py` → nur noch **Re-Export** aus `src.models`:
```python
from src.models import Evidence, SourceReference, ReferenceRecord, SourceCatalogEntry
```
Kein eigenes Modell, kein Dataclass-Fallback, kein `SourceKind`-Enum als
Ausgabetyp. (Ein privates internes Mapping-Dict ist erlaubt, muss aber in
Vertragswerte übersetzen.)

Konstruktor-Mapping in `ingest.py` (Helper-Funktionen):

| Quelle | evidence_id | source_id | page | origin_source_id | kind | purpose | review_status |
|---|---|---|---|---|---|---|---|
| S01 Seite | `S01-p0NN` | S01 | N | S01 | pdf | technical | unreviewed |
| S03/S04 Seite | `S0x-p0NN` | S0x | N | S0x | pdf | **research** | unreviewed |
| S02 Notiz | `S02-note-pNN` | S02 | N | S02 | curated_note | technical | **pending_visual_check** (+review_note) |
| XLSX Zeile | `XLSX-rowNN` | **S01** | **6** | **XLSX** | table_transcription | technical | unreviewed |
| S05 Flyer | `S05-context` | S05 | 1 | S05 | curated_note | **business_context** | unreviewed |
| S06 Link | `S06-context` | S06 | **None** | S06 | **text** | business_context | unreviewed |
| BRIEF | `BRIEF-pNN` | — | — | — | **ReferenceRecord** (record_id, source_id=BRIEF) | — | — |
| DOCX | `DOCX-pNNNN` | — | — | — | **ReferenceRecord** (record_id, source_id=DOCX) | — | — |

- **BRIEF raus aus Evidenz** (I8): nicht mehr in `INDEXABLE_SOURCES`; wird
  `ReferenceRecord`. `INDEXABLE_SOURCES` = {S01,S02,S03,S04,S05,S06,XLSX}.
- DOCX bleibt getrennt, jetzt als `ReferenceRecord` statt `Evidence`.
- Katalog (`SourceCatalogEntry`) darf BRIEF/XLSX/DOCX weiter inventarisieren.

## D. Build-Skript (I10)

- Defaults aus `Settings()`: `--materials` default `Settings().afs_source_dir`,
  `--out` default `Settings().afs_index_dir`; explizite CLI-Args überschreiben.
- S02-Notizpfad relativ zur Projektwurzel (`src.config.PROJECT_ROOT`).
- Ausgaben:
  - `evidence.jsonl` — nur echte `Evidence` (S01–S04 Text, S02 Notes, XLSX, S05/S06).
  - `reference_records.jsonl` — BRIEF + DOCX als `ReferenceRecord` (ersetzt `dev_reference.jsonl`).
  - `catalog.json`, `manifest.json` (wie gehabt, UTC/Hashes/counts, keine Secrets).
- Sortierung nach `evidence_id`.
- **Selbst-Validierung:** jede geschriebene Evidence-Zeile via
  `Evidence.model_validate_json` gegenprüfen; Fehlschlag bricht den Build ab.

## E. Tests

- `tests/test_ingest.py` / `test_catalog.py`: `chunk_id`→`evidence_id`,
  neue Felder (`kind`, `purpose`, `origin_source_id`, `review_status`).
- H-Ausschluss-Test bleibt (liest H-Signaturen zur Laufzeit).
- Neuer Test: S05 nie `purpose="technical"` (Absicherung [V-4]).
- Neuer Test: BRIEF/DOCX erzeugen `ReferenceRecord`, keine `Evidence`.
- Jakobs `tests/test_ingestion_contract.py` **muss grün** werden — ist mein
  Abnahme-Gate. Nicht verändern (gehört zur Übergabe).
- Lib-abhängige Pfade via `pytest.importorskip` (uv installiert sie lokal real).
- `conftest.py`: Pfade an Projektwurzel/`Settings` ausrichten.

## F. Reihenfolge der Umsetzung (jeder Schritt testbar)

1. **`main` in den T02-Branch mergen**, Overlaps gem. Abschnitt B lösen.
2. `types.py` auf Re-Export umstellen.
3. `ingest.py`: Helper + Mapping (Abschnitt C), BRIEF/DOCX→ReferenceRecord,
   Allowlist ohne BRIEF.
4. `s02_notes.yaml`: `review_status`/`review_note` statt Name/Text-Hack
   (`needs_visual_check: true` → `pending_visual_check`).
5. `build_index.py`: Settings-Defaults, reference_records.jsonl, Selbst-Validierung.
6. `requirements.txt` löschen; README vereinen/korrigieren.
7. Tests anpassen + neue Tests; Jakobs Contract-Test grün machen.
8. Lokal (Kevin) Integrationsgate fahren: `uv sync --locked`,
   `pytest -q`, `ruff check/format --check`, `build_index.py`.

## G. Abgrenzung / Umgebung

- Migration berührt **nur Kevins Dateien** + die Overlap-Dateien laut B.
  Jakobs `models.py`/`contracts.py`/`state.py`/`config.py`/`errors.py` bleiben
  unangetastet. `verify_quotes` [V-2] wird NICHT angefasst (nur PR-Hinweis).
- PyPI/uv in der Sandbox blockiert → realer `uv sync` + Indexbau laufen bei
  Kevin lokal; hier Fixture-Tests (stdlib + ggf. vorhandenes pydantic).
- **Merge-Richtung:** `main` → T02-Branch (ich überschreibe keine T01-Historie).
