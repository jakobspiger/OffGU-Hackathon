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
