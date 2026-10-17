# AFS Spectroscopy Design Assistant

Hackathon-Projekt von **Kevin und Jakob** für die Challenge „AI Assistant for In-line Spectroscopy Solution Design“ von Art Fiber Systems (AFS).

Der geplante Assistent übersetzt natürlichsprachige industrielle Kundenanfragen in eine vorsichtige, quellenbasierte erste Machbarkeitsbewertung für Spektroskopie. Er unterstützt Fachleute bei Methodenwahl, Rückfragen und Versuchsplanung. Er ersetzt keine fachliche Freigabe.

## Aktueller Stand

T01 liefert das Projektfundament: reproduzierbares Python-Setup, Konfiguration, typisierte Datenverträge, LangGraph-State, Vertragstests und einen startbaren Streamlit-Startbildschirm. Die fachliche Analyse und das Retrieval sind noch nicht implementiert; ihre öffentlichen Einstiegspunkte melden dies ausdrücklich. Die weiteren Aufgaben stehen in den 15 lokalen Tickets.

## Schnellstart

Voraussetzung: [uv](https://docs.astral.sh/uv/getting-started/installation/). Im Repository-Hauptordner:

```powershell
uv sync --locked
uv run --locked pytest -q
uv run --locked streamlit run app.py
```

Kein API-Key für Tests und Startbildschirm nötig. Für Jakobs bereits lokal vorbereitete Werkzeuge sowie Konfiguration und Prüfkommandos siehe [Entwicklungsanleitung](docs/development.md).

- [Technischer Deepdive und Architekturentscheidungen](docs/architecture.md)
- [Datenverträge und Zuständigkeiten](docs/contracts.md)
- [T02-Übergabe: Integration von Kevins bestehendem Branch](docs/t02-handover.md)

Wir verwalten Aufgaben direkt als Markdown-Dateien im Ordner [tickets/](tickets/README.md). GitHub-Issues, GitHub CLI und ein Projects-Board sind für unsere Zusammenarbeit nicht erforderlich.

## Wissensindex bauen (T02)

Der Quellen-Index wird deterministisch aus dem versionierten Ordner `materials/` erzeugt. `materials/` ist Teil des Repositorys und wird **nicht** ignoriert. Abhängigkeiten (PyMuPDF, python-docx, openpyxl, PyYAML, Pydantic) stammen ausschließlich aus `pyproject.toml` / `uv.lock`; es gibt keine `requirements.txt` mehr. Installation daher nur über `uv`:

```powershell
uv sync --locked
uv run python scripts/build_index.py
```

Ohne Argumente nutzt das Skript die Defaults aus `Settings()` (`afs_source_dir` und `afs_index_dir`). Explizite Argumente überschreiben sie:

```powershell
uv run python scripts/build_index.py --materials materials --out data/index
```

Das Skript schreibt vier Artefakte in den Ausgabeordner:

- `evidence.jsonl` — echte, zitierbare Evidenz (S01–S04 Seitentext, S02-Notizen, XLSX-Transkription, S05/S06 Business-Kontext), eine JSON-Zeile je Datensatz, sortiert nach `evidence_id`. Jede Zeile wird mit `Evidence.model_validate_json` gegen den Vertrag geprüft; ein Fehlschlag bricht den Build ab.
- `reference_records.jsonl` — Challenge-Brief (BRIEF) und Entwicklungsreferenz (DOCX) als `ReferenceRecord`, bewusst getrennt von der Evidenz (ersetzt das frühere `dev_reference.jsonl`).
- `catalog.json` — das Quelleninventar mit Vorhanden-/Fehlend-Status.
- `manifest.json` — UTC-Zeitstempel, Quelldateien mit Größe und SHA-256, Bibliotheksversionen, Zähler. Keine Secrets.

Jeder Evidenz-Datensatz trägt die gemeinsamen Vertragsfelder aus `src/models.py`: `evidence_id` (stabile ID, z. B. `S01-p010`, `XLSX-row03`, `S02-note-p13`), `source_id`, `page`, `origin_source_id`, `text`, `kind` (`pdf` / `curated_note` / `table_transcription` / `text`), `purpose` (`technical` / `research` / `business_context`) und `review_status` (`unreviewed` / `pending_visual_check` / `reviewed`). Die S02-Notizen bleiben `pending_visual_check` mit dokumentierter `review_note`, bis Kevin die gerenderten Folien visuell gegengeprüft hat; ein Textpräfix oder Name ist kein Prüfnachweis. BRIEF und DOCX sind keine wissenschaftliche Evidenz und erscheinen nie in `evidence.jsonl`; H01–H06 bleiben vollständig ausgeschlossen.

## Retrieval (T04)

`retrieve(query, k)` aus `src/knowledge/retrieval.py` findet die relevantesten AFS-Passagen und liefert `Evidence`-Objekte mit gesetzter Trefferinformation (`score`), absteigend nach Relevanz sortiert (Gleichstände stabil nach `evidence_id`). Es liest **ausschließlich** `data/index/evidence.jsonl` aus `Settings().afs_index_dir`. Fehlt der Index, wird ein klarer `RetrievalError` geworfen (kein `ComponentNotReadyError`). Der geladene Index wird je Prozess gecacht; `reset_cache()` leert ihn (für Tests).

### Hybrid mit Auto-Umschaltung

Der Modus wird automatisch aus der Konfiguration abgeleitet, ohne stillen Wechsel auf ein erfundenes Modell:

- **lexikalisch (Default):** `AFS_EMBEDDING_MODEL` ist leer. Ein deterministischer, unicode- und case-robuster Token-Score (NFC + Casefold + Whitespace-Normalisierung analog V-2) läuft über den Evidenz-Text. Kein Netz, kein API-Key. Das ist der reale Default, weil am konfigurierten OpenAI-kompatiblen Endpunkt derzeit **kein** `/embeddings`-Modell freigeschaltet ist.
- **hybrid/vektor:** `AFS_EMBEDDING_MODEL` ist gesetzt **und** `data/index/embeddings.jsonl` existiert neben `evidence.jsonl`. Dann wird die Query einmalig über den Endpunkt eingebettet und per Kosinus-Ähnlichkeit (reines Python) gegen die gespeicherten Evidenz-Vektoren verglichen.

### Quellenrang: business_context wird abgewertet, nicht gefiltert

In **beiden** Modi wird `purpose="business_context"` (S05 Flyer, S06 Link) im Ranking abgewertet (kleines, aber positives Gewicht). Diese Treffer bleiben als Kontext zitierbar, gelten aber **nie** als technischer Leistungsbeleg: technische und Research-Evidenz liegen im Rang immer davor. S06 behält `page=None` (keine erfundene PDF-Seite). H01–H06 und Entwicklungsreferenzen (DOCX/`ReferenceRecord`) sind bereits durch den T02-Build strukturell aus `evidence.jsonl` ausgeschlossen und können daher nie auftauchen.

### Embedding-Konfiguration

Der Vektor-Modus nutzt einen OpenAI-kompatiblen `/embeddings`-Endpunkt (gleiches httpx-Muster wie der Chat-Provider; der Key wird nie geloggt). Relevante Umgebungsvariablen (`.env`):

- `AFS_EMBEDDING_MODEL` — Embedding-Modellname. Leer = lexikalisch (Default).
- `OPENAI_BASE_URL` — Basis-URL des OpenAI-kompatiblen Endpunkts (ohne Zugangsdaten/Query/Fragment).
- `OPENAI_API_KEY` — API-Key, nur im Vektor-Modus nötig.

### Index bauen und Grenzen

```powershell
uv sync --locked
uv run python scripts/build_index.py
```

Der Build ist additiv zum T02-Bau: Ist ein Embedding-Modell gesetzt, bettet er jeden Evidenz-Text einmal ein und schreibt `data/index/embeddings.jsonl` (`{evidence_id, vector}`) plus `embedding_meta.json` (Modus, Modell, Dimension, UTC — **keine** Secrets). Ohne Embedding-Modell wird kein API-Call gemacht, keine `embeddings.jsonl` geschrieben, und `embedding_meta.json` vermerkt `mode="lexical"`. `manifest.json` trägt zusätzlich `retrieval_mode` und den Embedding-Modellnamen (ohne Key). Grenze: Ohne freigeschalteten Embedding-Endpunkt bleibt es beim lexikalischen Modus; die Retrieval-Tests mocken den Embedding-Transport und brauchen **keinen** Key.

## Geplantes Ergebnis

- Genannte Fakten, Annahmen und unbekannte Angaben getrennt darstellen.
- Entscheidende Rückfragen priorisieren und begründen.
- Bedingte Methodenkandidaten, Messgeometrie und Spektralbereiche vorschlagen.
- Technische Aussagen mit AFS-Quellen und konkreten PDF-Seiten belegen.
- Risiken, fehlende Nachweise und Grenzen sichtbar machen.
- Einen ersten Machbarkeitsversuch mit unabhängigen Referenzmessungen und Go/No-Go-Kriterien entwerfen.
- Ergebnisse strukturiert anzeigen und exportieren.

## Zielarchitektur

1. **Eingabe:** Kundenanfrage in natürlicher Sprache.
2. **LangGraph-Orchestrierung:** B2 Parameter-Extraktor → B3 Lücken-Analysator → B4/B5 Lösungssynthese → B6 Versuchsplan-Generator.
3. **Wissensbasis und deterministischer Kern:** Regel-Matrix aus AFS-XLSX/S01, Vektor-Index der Quellen S01–S06 und getrennter Few-Shot-Speicher für Entwicklungsfälle D01–D08.
4. **Verifikation und Ausgabe:** B7 Zitations- und Physik-Gate, Experten-Cockpit und Batch-Export.

Das Fundament verwendet Python 3.12 als Teamstandard, Streamlit, Pydantic und LangGraph. Direkte Abhängigkeiten stehen in `pyproject.toml`, aufgelöste Versionen in `uv.lock`. Lokale Wissensartefakte und eine konfigurierbare OpenAI-kompatible Modell-API werden in den Folgetickets angebunden.

Die aktuelle Teamentscheidung für LangGraph, Vektor-Retrieval und Few-Shot-Speicher konkretisiert die früheren, schlankeren Vorschläge in Strategiepapier und Masterprompt. Für die Umsetzung dienen die Tickets als Arbeitsgrundlage.

## Repository-Struktur

```text
OffGU-Hackathon/
├── README.md
├── pyproject.toml / uv.lock    # Projekt und reproduzierbare Abhängigkeiten
├── app.py                     # Startbildschirm, noch kein Analyse-Cockpit
├── src/                       # Modelle, State, Konfiguration, Schnittstellen
├── tests/                     # Lokale Fundament- und Vertragstests
├── docs/                      # Setup, Architekturentscheidungen, Datenvertrag
├── materials/                 # Planungsunterlagen und bereitgestellte Materialien
└── tickets/
    ├── README.md              # Reihenfolge, Zuständigkeiten und Zusammenarbeit
    ├── T01.md … T15.md        # Aufgaben mit Abnahmekriterien und Kollisionshinweisen
    └── publish-issues.ps1     # Optionaler Import; im aktuellen Ablauf nicht benötigt
```

- [Strategiepapier](materials/STRATEGIEPAPIER_AFS_TEAM.md)
- [Agent-Masterprompt](materials/CODEX_AGENT_MASTERPROMPT.md)
- [Ticketübersicht und Arbeitsaufteilung](tickets/README.md)

## Zusammenarbeit

| Verantwortlich | Tickets | Schwerpunkt |
|---|---|---|
| Kevin | T02–T05, T10, T13 | Quellen, Regeln, Retrieval, Beispiele, Validierung und Evaluation |
| Jakob | T01, T06–T09, T11, T12, T14 | Schnittstellen, Analyse, Orchestrierung, UI und Batch |
| Jakob mit Kevin | T15 | Reproduzierbarkeit und Abgabe |

Jakob pflegt gemeinsame Modelle, Konfiguration und Abhängigkeiten. Kevin pflegt die Wissensmodule und das Validierungs-Gate. Konkrete Dateigrenzen und notwendige Abstimmungen stehen in jedem Ticket. Gemeinsame Schnittstellen vor paralleler Implementierung abstimmen; anschließend können beide mit vereinbarten Testdaten unabhängig arbeiten.

### Ablauf pro Ticket

1. Aktuellen Stand von `main` holen und einen eigenen Branch erstellen, beispielsweise `feat/t01-project-foundation`.
2. Ticketumfang und Dateigrenzen beachten; Änderungen an gemeinsamen Schnittstellen absprechen.
3. Umsetzung und passende lokale Prüfungen durchführen. Eine automatische CI-Pipeline besteht aktuell nicht.
4. Kleine Commits pushen und im Pull Request das lokale Ticket verlinken, beispielsweise `tickets/T01.md`.
5. Der andere prüft den Pull Request. Abnahmekriterien im Ticket erst nach erfolgreichem Nachweis abhaken.
6. Nach dem Merge einen gemeinsamen Smoke-Test durchführen, sobald eine lauffähige Anwendung vorhanden ist.

Da die T-IDs lokale Kennungen sind, werden keine erfundenen GitHub-Issue-Nummern oder `Closes #T01` verwendet.

## Fachliche Leitplanken

- Keine erfundenen Konzentrationen, Genauigkeiten, Gerätekennwerte oder experimentellen Ergebnisse.
- Nominale Methodenbereiche sind kein Nachweis konkreter Geräte-, Faser- oder Sondenkompatibilität.
- Jede wichtige technische Aussage benötigt einen passenden Beleg. Eine existierende Quellenseite allein beweist die Aussage noch nicht.
- D01–D08 dienen der Entwicklung; Beispielantworten sind keine unabhängige wissenschaftliche Evidenz.
- H01–H06 bleiben aus Retrieval, Few-Shot-Speicher und fallbezogenen Regeln ausgeschlossen. Die finalen Ergebnisse entstehen durch dieselbe Pipeline und werden nicht manuell nachbearbeitet.
- API-Schlüssel gehören nicht ins Repository. Vor Veröffentlichung zusätzlicher Originalmaterialien muss deren Weitergabe geklärt sein.

## Umsetzungsreihenfolge

**T01–T02:** Schnittstellen und Quellenbasis → **T03–T10:** Wissen und Analysebausteine → **T11–T12:** integrierte Anwendung → **T13–T15:** Evaluation, finaler Batch und Abgabe.

Orchestrierung, UI und Tests können nach Festlegung der Schnittstellen mit Testdaten vorbereitet werden. Die genaue Integrationsreihenfolge steht in den jeweiligen Tickets.
