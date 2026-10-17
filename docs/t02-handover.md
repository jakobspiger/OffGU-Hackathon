# T02 an das gemeinsame T01-Fundament anbinden

Vergleichsbasis: Kevins Branch `T02-afs-quellen-aufbereiten`, Commit `30300fb`.
T01 enthält die gemeinsame Infrastruktur; Kevins Ingestion wird hier nicht kopiert oder gemergt.

## Verbindliche Übergabe

Gemeinsame Typen kommen aus `src.models`. `src/knowledge/types.py` darf diese zur Migration re-exportieren, aber kein zweites Evidence-Modell oder Dataclass-Fallback definieren. Pydantic ist eine installierte Pflichtabhängigkeit. SourceKind darf vorübergehend intern bestehen bleiben, muss aber vor Ausgabe in die gemeinsamen Werte übersetzt werden.

| Bisher in T02 | Gemeinsamer Vertrag |
|---|---|
| `chunk_id` | `evidence_id`; vorhandene stabile ID-Werte beibehalten |
| `pdf_text` | `kind="pdf"` |
| `verified_note` | `kind="curated_note"`; Prüfstatus separat |
| XLSX-Zeilen | `kind="table_transcription"`, `source_id="S01"`, `page=6`, `origin_source_id="XLSX"` |
| S01/S02 | `purpose="technical"`, ursprüngliche Quellen-ID auch in `origin_source_id` |
| S03/S04 | `purpose="research"`, ursprüngliche Quellen-ID auch in `origin_source_id` |
| S05-Katalogbeschreibung | `kind="curated_note"`, `purpose="business_context"`, Herkunft S05 |
| S06-Link | `kind="text"`, `purpose="business_context"`, Herkunft S06, `page=None` |
| BRIEF/DOCX-Text | `ReferenceRecord` mit `record_id`, außerhalb `evidence.jsonl` |
| Input-Inventar | `SourceCatalogEntry` erlaubt zusätzlich BRIEF/XLSX/DOCX |

`review_status` ist standardmäßig `unreviewed`. Die bestehenden S02-Notizen mit `needs_visual_check: true` erhalten `pending_visual_check`. Nur nach tatsächlicher Prüfung `reviewed` setzen und in `review_note` Prüfer/Datum/Vorgehen dokumentieren. Ein Text-Präfix oder der bisherige Name `verified_note` ist kein Prüfnachweis. T04 muss diesen Status erhalten; T10 muss offene Prüfungen berücksichtigen. T01 implementiert noch kein fachliches Gate.

## Änderungen bei Kevin

1. Nach Veröffentlichung T01 in den eigenen Branch übernehmen, vorzugsweise nach Teamreview über `main`; alternativ direkt `origin/feat/t01-project-foundation` mergen. Keine fremde Branch-Historie überschreiben.
2. Bei Konflikten `.env.example` und `.gitignore` vereinigen: T01-Konfiguration und Ausschlüsse lokaler Tools behalten. Leere `__init__.py` können durch T01-Beschreibungen ersetzt werden.
3. Gemeinsame Typen importieren; Evidence-Konstruktoren gemäß Tabelle umstellen. Sortierung und Tests von `chunk_id` auf `evidence_id` umstellen.
4. BRIEF nicht mehr als wissenschaftliche Evidenz indexieren. DOCX weiterhin getrennt speichern, nun als `ReferenceRecord`. Katalog darf beide weiterhin inventarisieren.
5. `requirements.txt` als zweite Dependency-Quelle entfernen. PDF-, DOCX-, XLSX- und YAML-Libraries sind jetzt in T01s `pyproject.toml`/`uv.lock` enthalten. Installation ausschließlich mit `uv sync --locked`.
6. CLI-Defaults aus `Settings().afs_source_dir` und `afs_index_dir` übernehmen; explizite CLI-Argumente überschreiben sie. S02-Notizpfad relativ zur Projektwurzel auflösen.
7. README um die Indexbau-Anleitung ergänzen, Projektübersicht und T01-Setup erhalten. Aussagen, dass `materials/` ignoriert oder unversioniert sei, korrigieren: diese Materialien sind bereits versioniert.
8. Gemeinsame Tests und echten Indexbau ausführen. Fehlende Parser dürfen bei der Integrationsprüfung nicht durch ausgelassene Tests oder reduzierte Ersatzindizes kaschiert werden.

## Integrationstest vor T02-Merge

```powershell
uv sync --locked
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python scripts/build_index.py --materials materials --out data/index
```

Zusätzlich jede Zeile von `evidence.jsonl` mit `Evidence.model_validate_json` prüfen; Entwicklungs-/Aufgabenreferenzen separat validieren. Vor einem Neuaufbau keine historischen finalen Ergebnisse überschreiben. H01–H06 bleiben ausschließlich finale Batch-Eingaben.

## Bewusste Grenzen

Der Vertrag ist jetzt an T02s Anforderungen angepasst, aber die bestehende T02-Ausgabe wird absichtlich nicht stillschweigend akzeptiert. T02 muss die Migration durchführen. Review durch Kevin ist noch offen; es wird keine Zustimmung behauptet. Der vollständige gemeinsame Indexbau kann erst nach dieser Migration als erfolgreich gelten.
