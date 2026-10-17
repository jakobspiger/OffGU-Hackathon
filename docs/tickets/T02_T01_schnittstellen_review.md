# Schnittstellen-Review: T02 (Kevin) ↔ T01 (Jakob)

> Vergleichsbasis: `main` @ `67ff75a` (T01 gemergt) vs. Branch
> `T02-afs-quellen-aufbereiten` @ `30300fb`.
> Zweck: kritische Prüfung der Schnittstellen **vor** T02-Merge. Jede
> Verbesserung ist mit **[V-n]** nummeriert und wartet auf Kevins Validierung.
> **Noch kein Code geändert.**

## 0. Gesamturteil

T01 ist ein starkes, striktes Fundament (`extra="forbid"`, `strict=True`,
Validatoren für Seiten/Einheiten/Quellen-Scope). Jakob hat den gemeinsamen
Vertrag **bewusst an T02 angepasst** (XLSX→S01 p.6, review_status,
ReferenceRecord) und ein exaktes Handover (`docs/t02-handover.md`) + einen
Contract-Test (`tests/test_ingestion_contract.py`) geliefert, der genau gegen
meine Datenstruktur zielt.

**Fazit:** Mein T02 ist funktional korrekt, aber **schnittstellen-inkompatibel**
mit T01 in mehreren Punkten. T02 muss migriert werden — die Richtung gibt T01
vor, und das ist sachlich berechtigt (ein einziges `Evidence`-Modell ist besser
als zwei). Ich habe aber **4 Punkte, bei denen ich T01 kritisch hinterfrage**
(Abschnitt 3) — die brauchen deine Entscheidung, bevor ich blind migriere.

---

## 1. Harte Inkompatibilitäten (T02 MUSS sich anpassen)

| # | Thema | T02 aktuell | T01-Vertrag | Konsequenz |
|---|---|---|---|---|
| I1 | **Doppeltes Evidence-Modell** | `src/knowledge/types.py` definiert eigenes `Evidence` + stdlib-Fallback | `src.models.Evidence` ist der einzige Vertrag; Handover verbietet ein zweites Modell/Fallback | `types.py` darf nur noch **re-exportieren** |
| I2 | **Feldname `chunk_id`** | `chunk_id="S01-p010"` | `evidence_id` | umbenennen, ID-Werte behalten |
| I3 | **`kind`-Werte** | `pdf_text / verified_note / table_transcription / dev_reference / business_context` | `pdf / curated_note / table_transcription / text` + **separates** `purpose` (technical/research/business_context) | `kind` neu mappen, `purpose` neu einführen |
| I4 | **`dev_reference` als Evidence-kind** | DOCX/BRIEF als `Evidence(kind=dev_reference)` | Das sind **`ReferenceRecord`** (eigener Typ), keine Evidence | Umbau auf `ReferenceRecord` |
| I5 | **`verified_note` = Prüfnachweis?** | Name suggeriert „geprüft", Provenance im Text | `review_status` (default `unreviewed`); S02-Notes → `pending_visual_check`; `reviewed` nur mit `review_note` | Status-Feld nutzen, nicht den Namen/Textpräfix |
| I6 | **`origin_source_id` fehlt** | nicht vorhanden | Pflichtfeld; XLSX: `source_id=S01, page=6, origin_source_id=XLSX` | für jede Evidence setzen |
| I7 | **S06 `kind`** | `business_context` | `kind="text"`, `purpose="business_context"`, `page=None` (Validator erzwingt: nur S06 = kind text) | anpassen |
| I8 | **BRIEF als Evidence indexiert** | BRIEF in `PDF_TEXT_SOURCES` + `INDEXABLE_SOURCES`, landet in evidence.jsonl | BRIEF ist `ReferenceRecord`, **nicht** wissenschaftliche Evidenz | BRIEF aus Evidenzindex raus |
| I9 | **Zweite Dependency-Quelle** | `requirements.txt` | `pyproject.toml` + `uv.lock` (inkl. pymupdf/docx/openpyxl/pyyaml) | `requirements.txt` entfernen |
| I10 | **CLI-Defaults** | hartkodiert `materials` / `data/index` | aus `Settings().afs_source_dir` / `afs_index_dir`, CLI überschreibt | Defaults aus Settings ziehen |
| I11 | **Datei-Overlaps** | `.env.example`, `.gitignore`, `src/__init__.py`, `src/knowledge/__init__.py` von BEIDEN angelegt | T01-Versionen sind reicher | bei Merge T01-Fassung behalten + T02-Ausschlüsse vereinen |
| I12 | **README/`materials` ignoriert** | README sagt `data/source/` + Index git-ignored; impliziert `materials/` unversioniert | `materials/` ist bereits **versioniert** | README-Aussage korrigieren |

**Gute Nachricht:** T01 hat seinen Vertrag so geformt, dass meine stabilen
ID-Werte (`S01-p010`, `XLSX-row03`, `S02-note-p13`) **erhalten bleiben** — nur
das Feld heißt jetzt `evidence_id`. Die `kind`-Trennung, S06-ohne-Seite,
XLSX→p.6, H-Ausschluss: alles was T02 konzeptionell macht, deckt sich mit T01.
Es ist überwiegend **mechanische Migration**, kein Redesign.

---

## 2. Was bereits übereinstimmt (keine Änderung nötig)

- 1-basierte Seiten, S06 ohne Seite, XLSX zitiert S01 p.6.
- Qualitative XLSX-Ratings ≠ Messwerte (meine QUALIFIER-Logik bleibt gültig).
- H01–H06 nie im Index; DOCX getrennt gehalten.
- Deterministische stabile IDs; idempotenter Build; Manifest mit UTC/Hashes.
- S02 bildlastig → kuratierte Notizen statt angeblicher PDF-Extraktion.
- `retrieve`/`analyze` nicht belegt (gehören T04/T11).

---

## 3. KRITISCHE RÜCKFRAGEN an T01 — brauchen Kevins Validierung

Hier hinterfrage ich T01, nicht nur mich. Diese Punkte bitte entscheiden:

### [V-1] `CatalogSourceID` enthält „XLSX"/„DOCX", aber `SourceReference.source_id` nicht — gewollt, aber eine Falle
`Evidence.source_id` ist `SourceID` (nur S01–S06). Für XLSX-Zeilen muss man
daher `source_id="S01"` setzen und die Herkunft in `origin_source_id="XLSX"`.
Das ist logisch (zitiert wird S01 p.6), aber **leicht falsch zu machen** und der
Fehler fällt erst zur Laufzeit auf. **Vorschlag:** so lassen (Vertrag ist
sauber), aber ich baue in der Ingestion einen Helper `make_table_evidence()`,
der die drei Felder garantiert korrekt setzt. → *nur Bestätigung nötig.*

### [V-2] `ExtractedFact.verify_quotes` verlangt wörtliches Teilstring-Match
`input_quote not in query` (exakter Substring). Das ist streng und gut gegen
Halluzination — aber bricht bei normalisierten Anführungszeichen/Whitespace/
Unicode (z. B. „ vs ", NBSP). Betrifft **T06 (Extraktor)**, nicht T02 direkt,
aber es ist eine gemeinsame Schnittstelle. **Vorschlag [V-2]:** mit Jakob klären,
ob `verify_quotes` eine definierte Normalisierung erlaubt (z. B. casefold +
Whitespace-Kollaps) — sonst produziert der Extraktor später False-Negatives.
→ *Team-Entscheidung, kein T02-Blocker.*

### [V-3] `review_note` als `Text` (min_length=1) — Format undefiniert
Handover fordert „Prüfer/Datum/Vorgehen" in `review_note`, aber das Modell
erzwingt nur „nicht leer". **Vorschlag [V-3]:** leichte Konvention dokumentieren
(z. B. `"reviewed_by=<name>; date=<ISO>; method=<...>"`), damit T10 das später
maschinell prüfen kann. Optional, aber billig jetzt. → *deine Entscheidung.*

### [V-4] `kind="curated_note"` mischt S02-Notizen und S05-Flyer-Beschreibung
Nach Handover werden **S02-Slide-Notizen** UND **S05-Business-Beschreibung**
beide `curated_note`. Sie unterscheiden sich nur über `purpose`
(technical vs business_context). Das ist tragbar, aber `purpose` wird damit zum
einzigen Trenner zwischen „technische Slide-Notiz" und „Marketing-Flyer".
**Vorschlag [V-4]:** akzeptieren (Vertrag deckt es über `purpose` ab); ich
stelle per Test sicher, dass S05 nie `purpose="technical"` bekommt. → *nur
Bestätigung.*

---

## 4. Vorgeschlagener Migrationsplan für T02 (nach deiner Freigabe)

Reihenfolge, rein mechanisch, pro Schritt testbar:

1. **T01 in den T02-Branch mergen** (`origin/main` → Branch), Overlaps lösen:
   `.env.example`/`.gitignore` vereinen (T01-Basis behalten), leere
   `__init__.py` durch T01-Fassung ersetzen.
2. **`src/knowledge/types.py`**: Eigenes Evidence-Modell + Dataclass-Fallback
   entfernen; stattdessen `from src.models import Evidence, SourceReference,
   ReferenceRecord, SourceCatalogEntry` re-exportieren. `SourceKind` darf intern
   als Mapping-Helfer bleiben, muss aber vor Ausgabe in Vertragswerte übersetzen.
3. **`ingest.py`**: Konstruktoren gem. Handover-Tabelle umstellen
   (`evidence_id`, `kind`, `purpose`, `origin_source_id`, `review_status`);
   `make_pdf_evidence/make_table_evidence/make_note_evidence/make_business_
   evidence`-Helper; BRIEF+DOCX → `ReferenceRecord`; `INDEXABLE_SOURCES` ohne
   BRIEF.
4. **S02-Notes**: `review_status="pending_visual_check"` + `review_note`
   („pending final visual check …"); Provenance raus aus dem Text-Hack, rein
   ins Feld. `needs_visual_check: true` → Status.
5. **`build_index.py`**: Defaults aus `Settings()`; `evidence.jsonl` nur echte
   Evidence; `reference_records.jsonl` (BRIEF+DOCX) ersetzt `dev_reference.jsonl`;
   Sortierung nach `evidence_id`; jede Zeile mit `Evidence.model_validate_json`
   selbst-prüfen.
6. **`requirements.txt` löschen**; Doku auf `uv sync --locked` umstellen.
7. **Tests**: `chunk_id`→`evidence_id`; neue Felder prüfen; Jakobs
   `tests/test_ingestion_contract.py` muss grün werden; H-Ausschluss-Test
   bleibt; Lib-abhängige Tests via `importorskip` (uv installiert sie lokal real).
8. **README**: Indexbau-Anleitung ergänzen, T01-Setup erhalten,
   `materials/`-Aussage korrigieren.
9. **Integrationsgate** (aus Handover) lokal bei Kevin fahren:
   `uv sync --locked`, `pytest -q`, `ruff check/format --check`,
   `python scripts/build_index.py`, + Zeilen-Validierung von `evidence.jsonl`.

## 5. Offene Abhängigkeits-/Umgebungsnotiz

- In meiner Sandbox bleibt PyPI/uv-Netz blockiert → **realer Indexbau + uv sync
  laufen bei Kevin lokal**. Migrationscode + Fixture-Tests schreibe ich hier.
- Die Migration berührt **nur Kevins Dateien** (`src/knowledge/*`, `scripts/`,
  `tests/test_catalog|ingest`, README). Jakobs T01-Dateien bleiben unangetastet.
