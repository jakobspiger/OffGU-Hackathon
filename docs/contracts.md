# Datenvertrag 1.0 und Übergabe an die Folgetickets

Implementierung: `src/models.py`, `src/contracts.py`, `src/state.py`.

T06-Schritt 1 konkretisiert `ExtractedFact.parameter` als `ParameterName` statt freiem Text. Die verbindliche Liste und ihre Bedeutung stehen in [parameters.md](parameters.md); Erzeuger und Regeln müssen diese Schlüssel verwenden.

Für den bereits parallel entstandenen T02-Branch gilt die konkrete [Migrationsanleitung](t02-handover.md). Die hier dokumentierte Version 1.0 ist der erste veröffentlichte Vertrag; der frühere lokale Entwurf war noch nicht veröffentlicht.

## Öffentliche Aufrufe

| Aufruf | Ergebnis | Zuständig / Umsetzung |
|---|---|---|
| `src.engine.service.analyze(query: str)` | `AnalysisResult` | Jakob, T06–T11 |
| `src.knowledge.retrieval.retrieve(query: str, k: int = 8)` | `list[Evidence]` | Kevin, T04 |
| `RuleEvaluator(extraction)` | `list[RuleFinding]` | Kevin, T03 |
| `ExampleSelector(query, k=2)` | `list[FewShotExample]` | Kevin, T05 |
| `ResultValidator(result, evidence, rules)` | `ValidationReport` | Kevin, T10 |

Die letzten drei Einträge sind Callable-Protocols, keine bereits implementierten Funktionen. Die beiden öffentlichen Funktionen sind importierbare Stubs: ungültige Eingaben erzeugen `ValueError`, gültige Eingaben derzeit `ComponentNotReadyError`. Sie liefern keine vorgetäuschten Ergebnisse.

Später gilt: Ein erfolgreicher Retrieval-Lauf ohne Treffer liefert `[]`; ein fehlender/kaputter Index erzeugt `RetrievalError`. Provider-/Pipelinefehler erzeugen `AnalysisError`, Konfigurationsfehler `ConfigurationError`. `insufficient_information` ist ein fachlicher Status, kein Ersatz für einen API-Fehler.

## Zentrale Datenobjekte

- **SourceReference:** `source_id` S01–S06 und `page`; S01–S05 brauchen eine 1-basierte Seite, S06 hat `null`. XLSX-Zeilen zitieren die zugrunde liegende S01-Seite; keine neue unabhängige Quelle erfinden.
- **Evidence:** ergänzt stabile `evidence_id`, `text`, `kind`, `purpose` und optionalen endlichen `score`. Kevin bestimmt die stabile ID-Generierung in T02, beispielsweise aus Quellversion, Seite und Chunk. Kuratierte Bildnotizen sind `curated_note`, keine angeblich wörtliche PDF-Extraktion.
- **Herkunft und Prüfung:** `origin_source_id` hält das Ursprungsdokument fest. Tabellen-Transkriptionen aus XLSX zitieren S01 S. 6 und haben `kind="table_transcription"`. `review_status` unterscheidet `unreviewed`, `pending_visual_check` und `reviewed`; letzteres erfordert `review_note`. Diese Kennzeichnung ersetzt keine tatsächliche Prüfung.
- **SourceCatalogEntry / ReferenceRecord:** Das Inventar darf zusätzlich BRIEF, XLSX und DOCX enthalten. BRIEF-/DOCX-Passagen sind separate ReferenceRecords, keine zitierfähige wissenschaftliche Evidence. Das gemeinsame Modell vermeidet doppelte Typdefinitionen in der Wissensbasis.
- **ExtractionResult:** typisierte Fakten mit Parameter, Wert und Originalzitat; Annahmen und Unbekanntes in getrennten Listen. B2 ruft `verify_quotes(query)` gegen die unveränderte Eingabe auf. Ein passendes Zitat allein beweist noch keine korrekte Interpretation. Mit `extraction_version="1.1"` (T06-Schritt 2) ergänzt um `ExtractedFact.numeric_value` (optionaler exakter Skalar mit Einheit) und `conflicts` (explizit markierte Widersprüche); `unknowns` führt fehlende und konflikt-behaftete Parameter mit ihrem `ParameterName`. Details und Regelfolgen für T03 in [t06-handover-an-kevin.md](t06-handover-an-kevin.md). `verify_quotes` toleriert reine Darstellungsunterschiede (V-2, Issue #3), ohne den Halluzinationsschutz aufzuweichen.
- **ClarificationQuestion:** Frage, Begründung, positive Priorität (1 = höchste) und `blocking`. B3 sortiert die Ausgabe aufsteigend; gleiche Prioritäten sind erlaubt.
- **RuleFinding:** Regel-ID, Ergebnis `excluded / conditional / unknown`, Grund und Quellen. `unknown` ist keine Freigabe.
- **ValidationFinding:** Code, Schweregrad `error / warning / not_checked`, Nachricht, Feldpfad und Evidenz-IDs. `ValidationReport.has_errors` berechnet, ob mindestens ein Fehler vorliegt. Ein fehlerloser Bericht mit `not_checked` ist kein vollständiger Prüfbeleg.
- **Recommendation:** Methode, Rolle, Bedingungen, Geometrie, optionaler Spektralbereich, Quellen und Evidenz-IDs. Fehlende Spektraldaten bleiben `null`; keine Ersatzwerte erfinden.
- **SpectralRange:** positive, aufsteigende numerische Grenzen; `nm` für Wellenlänge, `cm^-1` für Wellenzahl/Raman-Shift; Scope und Kompatibilitätshinweis. Ein als `verified_instrument` markierter Bereich muss in T10 zusätzlich anhand konkreter Evidenz geprüft werden.
- **FewShotExample:** D01–D08-ID, Anfrage, optionale Referenzantwort und Herkunft. H-IDs sind unzulässig.

## AnalysisResult

Die äußeren Felder aus dem Masterprompt bleiben bestehen: `decision_status`, `stated_facts`, `assumptions`, `unknowns`, `clarification_questions`, `recommendations`, `measurement_concept`, `risks_and_limits`, `feasibility_plan`, `go_no_go_criteria` und `overall_sources`.

Die vorherigen generischen Dictionaries sind durch typisierte Untermodelle ersetzt. Hinzu kommen `schema_version="1.0"` und `validation_findings`. Quellen verwenden durchgängig `source_id` (nicht das uneinheitliche `id` aus dem Strategiepapier). Empfehlungsquellen müssen in `overall_sources` erscheinen. T10 prüft darüber hinaus tatsächliche Seitenexistenz, Evidenz-ID-Zuordnung und Claim-Unterstützung.

Leere Listen sind zulässig, damit eine ehrliche Enthaltung möglich bleibt. Die Vollständigkeit eines konkreten Versuchsplans und die Angemessenheit des Status sind fachliche Prüfungen, die das Schema allein nicht sicherstellen kann.

Serialisierung: `result.model_dump(mode="json")` bzw. `result.model_dump_json()`. Einlesen: `AnalysisResult.model_validate_json(payload)`. JSON-Schema: `AnalysisResult.model_json_schema()`. LLM-Ausgabe wird vor Verwendung validiert; unbekannte Felder werden nicht still verworfen.

## Graph-State und Schreibrechte

| Feld | Schreiber | Leser |
|---|---|---|
| query | Service | alle Knoten |
| extraction | B2 | B3, Synthese |
| questions | B3 | Synthese, UI |
| rules | Regeladapter | B3, Synthese, Gate |
| evidence | Retrievaladapter | Synthese, Gate |
| examples | Beispieladapter | Synthese/Versuchsplan |
| draft | B4/B5, danach B6 (sequenziell) | Gate |
| validation | B7 | Orchestrator |
| result | Orchestrator nach Gate | UI, Batch |
| revision_count | Orchestrator | Korrekturrouting |

Nur `query` muss initial vorhanden sein. Fehlende Zwischenergebnisse sind nicht dasselbe wie erfolgreich berechnete leere Listen. Keine API-Keys oder Provider-Clients im State speichern. Keine parallelen Schreibzugriffe auf dasselbe Feld in v1; hierfür wären später explizite Reducer erforderlich.

T11 darf `result` erst nach Gate-Behandlung setzen. Fehler führen zu begrenzter Überarbeitung oder definiertem Fehler; Warnungen und ungeprüfte Punkte müssen in der Ausgabe erhalten bleiben. T01 enthält noch keine solche Routing-Implementierung.

## Paralleles Weiterarbeiten

Kevin kann T02–T05 gegen Evidence, SourceReference und die Callable-Protocols entwickeln. Jakob kann B2–B6 mit synthetischen, schema-konformen Testdaten aufbauen. Die Testdaten sind keine fachliche Evidenz und keine Demoanalyse. Beide importieren gemeinsame Typen aus `src.models`.

Einmalig vor dem parallelen Start Feldnamen und Signaturen zusammen durchgehen. Gemeinsame Änderungen laufen über Jakob; niemand kopiert und verändert einen eigenen Vertragsstand.
