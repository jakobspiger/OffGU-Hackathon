# T01: Architekturentscheidungen und technischer Deepdive

Stand: 17. Oktober 2026. Verantwortlich: Jakob. Vertragsversion: 1.0.

## Umfang und Ausgangslage

Vor T01 gab es Planung und Materialien, aber keinen Anwendungscode, kein Dependency-Manifest und keine Tests. Die zehn im Masterprompt erwarteten Eingabedateien wurden anhand ihrer Dateinamen unter `materials/` gefunden. Das ist keine fachliche Validierung ihrer Inhalte; Ingestion und Quellenprüfung bleiben T02.

T01 liefert die ausführbare Entwicklungsbasis und verbindliche, testbare Schnittstellen. Fachliche Extraktion, Retrieval, Regelprüfung, Synthese, Gate und finale Auswertung bleiben ihren Tickets zugeordnet. Die vorhandenen Fachquellen wurden weder verändert noch in ein Modell oder einen Index geladen.

## ADR 001: Ein Python-Projekt mit reproduzierbarer Umgebung

**Entscheidung:** Python 3.12 als Teamstandard; Paket unterstützt 3.11 bis 3.13. `pyproject.toml` definiert direkte Abhängigkeiten, `uv.lock` fixiert die aufgelösten Versionen. `uv sync --locked` installiert ohne unbeabsichtigtes Neuauflösen. Kein Docker, Server, Login oder CI-System für T01.

**Grund:** Ein Setup für beide Entwickler und spätere Jury-Ausführung, weniger lokale Abweichungen. Entwicklungswerkzeuge sind in einer eigenen Gruppe. Nach Abgleich mit Kevins T02 sind PyMuPDF, python-docx, openpyxl und PyYAML zentral aufgenommen. Ein zweites requirements.txt mit widersprechendem Pydantic-Pin soll entfallen. Embedding-Abhängigkeiten folgen in T04.

**Kompromiss:** `src` bleibt bewusst der Python-Paketname, damit die im Masterprompt vereinbarten Pfade und Imports bestehen bleiben. Das Paket wird explizit gebaut; Materialien werden nicht in das Wheel aufgenommen. Ein späterer Paket-Rename wäre eine koordinierte Schnittstellenänderung.

Quelle: [uv-Projekte und Lockfile](https://docs.astral.sh/uv/guides/projects/).

## ADR 002: Pydantic an den Datengrenzen

**Entscheidung:** Pydantic v2 für alle strukturierten fachlichen Übergaben; unbekannte Felder sind verboten, Feldtypen strikt und zentrale Angaben verpflichtend. Verschachtelte Modelle ersetzen die unbestimmten `list[dict]` des Masterprompts.

**Grund:** Tippfehler, fehlende Ausgabeabschnitte und falsche Datentypen müssen vor UI/Export auffallen. JSON-Serialisierung und JSON-Schema stehen ohne eigenes Formatframework zur Verfügung. PDF-Seiten müssen positive ganze Zahlen sein; S06 erhält keine erfundene PDF-Seite.

**Grenze:** Ein gültiges Schema beweist weder wissenschaftliche Richtigkeit noch passende Quellen. Existenz, Claim-Evidenz-Zuordnung und Kompatibilität gehören ins Gate (T10). String-Fakten bleiben im äußeren Ergebnis kompatibel; die Extraktion hat zusätzlich überprüfbare Originalzitate.

Quelle: [Pydantic-Modelle](https://docs.pydantic.dev/latest/concepts/models/).

## ADR 003: LangGraph mit explizitem State und begrenzter Zuständigkeit

**Entscheidung:** `PipelineState` ist ein TypedDict mit validierten Pydantic-Objekten als Nutzdaten. Knoten liefern partielle Updates. In v1 schreibt pro Schritt nur ein Knoten in ein State-Feld; Listen werden ersetzt, nicht implizit angehängt.

**Grund:** Ein fester Graph passt zum Teamdiagramm und macht Übergaben sichtbar. Es gibt keine frei improvisierenden autonomen Runtime-Agenten. Ein ausführbarer Test prüft den State bereits gegen einen echten LangGraph-Graphen.

**Grenze:** TypedDict validiert nicht automatisch zur Laufzeit. Jeder spätere Knoten muss externe Daten mit dem passenden Pydantic-Modell validieren. T11 implementiert Ablauf und begrenzte Korrekturschleifen. `draft` und freigegebenes `result` sind getrennt; ein ungeprüfter Entwurf darf nicht als finale Analyse ausgegeben werden.

Quelle: [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).

## ADR 004: Lokales Vektor-Retrieval, keine Datenbank-Infrastruktur

**Entscheidung:** T04 baut einen lokalen, rekonstruierbaren Vektor-Index hinter `retrieve(query, k)`. Vorgesehen sind ein JSONL-Evidenzkatalog und eine lokale Vektormatrix mit Ähnlichkeitssuche; bei der kleinen Quellenmenge ist zunächst kein Datenbankserver nötig. Die konkrete Embedding-Implementierung bestimmt Kevin mit Jakob in T04.

**Reproduzierbarkeitsvertrag:** Der spätere Index muss Dokument-Hashes, Chunking-Version, Embedding-Modell/-Version, Dimension und Distanzmetrik speichern. Query und Korpus benötigen dasselbe Embedding-Verfahren. Änderungen daran erfordern einen Neuaufbau. Index-Scores sind keine wissenschaftlichen Wahrscheinlichkeiten.

**Datentrennung:** Nur zulässige AFS-Quellen liefern Evidenz. H01–H06 bleiben draußen. S05/S06 werden als Unternehmenskontext, S03/S04 als Forschung markiert. T01 implementiert weder Index noch Embedding-Aufrufe.

## ADR 005: Few-Shot-Beispiele getrennt von Belegen

**Entscheidung:** Eigener Typ `FewShotExample`, eigene Auswahl-Schnittstelle und eigener Speicher für D01–D08. Fehlende Musterantworten dürfen `null` sein. Beispiele werden nicht als `Evidence` oder `SourceReference` ausgegeben.

**Grund:** Beispiele helfen bei Struktur und Vorsicht, sind aber keine unabhängigen Messbelege. Die Trennung verhindert, dass ein Szenario als wissenschaftliche Quelle zitiert wird. Referenzen akzeptieren nur S01–S06. Das ersetzt nicht die spätere Prüfung der tatsächlichen Indexinhalte.

## ADR 006: Konfiguration ohne Seiteneffekte

**Entscheidung:** `Settings()` lädt Umgebungsvariablen und optional die lokale `.env`. Umgebungsvariablen haben Vorrang. Pfade sind relativ zur Projektwurzel. Modulimporte lesen keine Secrets und starten keine Netzwerkanfragen.

API-Key und Modell sind für Tests/UI-Skeleton optional. Erst `require_llm()` fordert sie für Live-Aufrufe. Es gibt keinen erfundenen Default-Modellnamen. Timeout, Retry-Anzahl und Retrieval-Limit sind begrenzt. API-Keys sind aus Repräsentation und Serialisierung ausgeschlossen. Base-URLs mit eingebetteten Zugangsdaten/Query werden abgelehnt.

**Grenze:** SecretStr ersetzt kein Secret-Management. Fehlerobjekte nicht mit internen Eingabedetails protokollieren; insbesondere nicht `ValidationError.errors()` ungefiltert ausgeben. Das künftige Provider-Modul implementiert erst die tatsächlichen API-Aufrufe.

Quelle: [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

## Übergabe und Änderungsprozess

Die Details stehen in [contracts.md](contracts.md). Jakob pflegt Modelle, State, Konfiguration und Abhängigkeiten. Kevin übernimmt die Retrieval-Datei nach T01 und implementiert Regeln, Beispiele und Gate in seinen Modulen. Die hier getroffenen Verträge sind der konkrete Implementierungsstand zur Teamprüfung, keine behauptete persönliche Zustimmung Kevins.

Änderungen am Vertrag gemeinsam besprechen, Schema-Version bei inkompatiblen Änderungen erhöhen, Tests und Dokumentation im selben Pull Request aktualisieren. Keine zweite parallele Modelldefinition in Wissens- oder UI-Modulen anlegen.
