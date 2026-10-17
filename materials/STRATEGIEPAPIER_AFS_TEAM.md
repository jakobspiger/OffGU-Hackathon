# Strategiepapier – AFS Spectroscopy Design Assistant

**Hackathon:** National AI Hackathon 2026 · Art Fiber Systems (AFS)  
**Stand:** 17. Oktober 2026 · **Abgabe:** Sonntag, 18. Oktober 2026, 23:59 Uhr (laut Kick-off; Discord/Formular verbindlich prüfen)  
**Zielgruppe:** Team, neue Mitwirkende, Jury, externe Interessierte  
**Status:** Umsetzungsstrategie, kein bereits gebautes Produkt.

## 1. Problem: Was soll tatsächlich gelöst werden?

Ein Industriekunde weiß häufig, **welche Prozessgröße** er beobachten möchte: Feuchtigkeit, Wirkstoffkonzentration, Verunreinigungen, Reaktionsfortschritt oder Produktqualität. Er weiß aber nicht zwangsläufig, **welche optische Messtechnik** dafür geeignet ist. Eine sinnvolle Erstmessung hängt von der Matrix (Pulver, klare Flüssigkeit, trübe Suspension, heißer Schmelzprozess, Gewebe), den Zielstoffen, der gewünschten Messstelle, Prozessbedingungen, möglichen Störsignalen, verfügbaren Referenzmessungen und praktischen Grenzen ab.

Ein Beispiel: Für eine undurchsichtige, streuende Milchmatrix kann **NIR-Diffusreflexion** ein plausibler erster Prüfpfad sein. Eine relativ klare Flüssigkeit kann dagegen eine **Transmissions-/Transflexionsmessung** nahelegen. Beide Vorschläge bleiben vorläufig, bis Optik, Referenzwerte und Einsatzbedingungen geklärt sind. Bei MIR-ATR spielen Kontakt, Probenoberfläche, Verschmutzung und kompatible IR-Fasern eine wichtige Rolle. **Die nominelle Spektralabdeckung eines Verfahrens ist nicht die tatsächlich nutzbare Abdeckung eines konkreten Sonden-/Fasersystems.**

Die manuelle Erstberatung erfordert interdisziplinäres Wissen. Ein großer Fehler wäre, einfach aus einem LLM eine überzeugend klingende, aber unbelegte Gerätekonfiguration ausgeben zu lassen. Das kann technisch ungeeignete Entscheidungen fördern: etwa ein Signal mit direkter Konzentrationsmessung zu verwechseln, eine bestehende Kalibrierung ungeprüft auf eine neue Rezeptur zu übertragen oder eine Laborstudie als Beleg für klinische Einsatzreife zu behandeln.

**Offizielle Aufgabenstellung:** Ein KI-Assistent für AFS-Fachleute, der eine natürlichsprachige Kundenanfrage strukturiert, fehlende Informationen erkennt, **ein oder mehrere zu testende Verfahren** samt Messkonzept und Einschränkungen empfiehlt, Quellen nachvollziehbar zitiert und einen **praktischen ersten Machbarkeitsversuch** entwirft. Er ersetzt ausdrücklich keine fachliche Freigabe. Es wird **kein selbst gebauter Sensor**, **kein neues Spektren-Klassifikationsmodell** und **kein fertiges IoT-Monitoring** verlangt.

**Quellbasis:** Challenge-Brief S. 1–2; `AFS_Examples_and_Reference.docx`, S. 1, 4–8; `S01_Multispectral_Laboratory.pdf`, S. 5–7, 10–12.

## 2. Lösungsthese – ein überprüfbarer „Engineering Copilot“

Wir bauen **AFS Spectroscopy Design Assistant**: einen schlanken Web-Prototyp, der jede Anfrage nach demselben nachvollziehbaren Prüfprozess bearbeitet:

```text
Freitext-Kundenanfrage
        ↓
Anforderungen extrahieren (Fakten ≠ Annahmen ≠ offene Fragen)
        ↓
AFS-Materialien gezielt durchsuchen (Dokument, PDF-Seite, Textbeleg)
        ↓
Methoden-Kandidaten + Grenzen/Kompatibilität prüfen
        ↓
Vorläufige Empfehlung ODER „noch nicht entscheidbar“
        ↓
Rückfragen + Sondenkonzept + Risiken + erster Versuch + Go/No-Go
        ↓
Strukturierte, mit AFS-Quellen verknüpfte Antwort; Export
```

**Unser Wettbewerbsvorteil ist nicht die Anzahl der Agents, sondern nachweisbare fachliche Vorsicht.** Ein Experte soll in Sekunden erkennen: Was hat der Kunde gesagt? Was nehmen wir an? Welche Quelle rechtfertigt welchen Schluss? Was müsste man wirklich testen? Was dürfen wir noch nicht behaupten?

### Beispiel (bewusst vorläufig)

**Kunde:** „Wir messen Wasser in einer Petroleumleitung. MIR-ATR wäre interessant; ein vorhandenes Silica-Kabel vom Vis/NIR-System führt zu einem anderen Gebäude. Dürfen wir das wiederverwenden?“

**Erwartetes Verhalten:** Den Ansatz *MIR-ATR als Testkandidat* erläutern, aber **keine Freigabe des vorhandenen Silica-Links** erteilen. Spektralübertragung/Fasertyp, Strecke, Einbaubedingungen und Kompatibilität sind nicht nachgewiesen. Passende AFS-Belege nennen (`S02` S. 6 und 13; `S01` S. 6/9–10); nötige Rückfragen auflisten; einen vergleichenden Pilotversuch mit Laborreferenzen und passender MIR-fähiger Schnittstelle skizzieren. Keine unbelegte Reichweite und keine garantierte Messgenauigkeit nennen.

## 3. Die Qualitäts- und Bewertungslogik

| Jurykriterium | Gewicht | Unsere Umsetzung |
|---|---:|---|
| Technische Qualität | **30 %** | Methodenkandidaten fachlich plausibel; Matrix, Geometrie, Grenzen prüfen |
| Nutzung von AFS-Wissen | **20 %** | RAG/gezielter Retrieval-Kontext, Claim-zu-Seite-Belege, keine Scheinquellen |
| Machbarkeitsversuch | **15 %** | Proben/Prozessvariation, unabhängige Referenz, Vergleich, Validierung, Go/No-Go |
| Rückfragen & Unsicherheit | **15 %** | Fakten/Unknowns trennen; konditionale Antworten; korrekt verweigern können |
| Erklärbarkeit | **10 %** | Klare Abschnitte, Annahmen und direkt zuordenbare Belege |
| Prototyp & Präsentation | **10 %** | Funktionierende App, Live-Neuanfrage, kurze Demo |

**Priorität:** Erst belastbare Wissensbasis und Antwortlogik (80 % der Kriterien), dann Oberfläche/Politur (10 %). Gewichtung ist eine Priorisierungsheuristik, keine Garantie für die Jurywertung.

## 4. Verbindliche Produktanforderungen (Definition of Done)

1. Ein Nutzer kann eine **neue** Prozessanfrage in Freitext eingeben.
2. Der Assistent liefert: **genannte Fakten**, **offene Parameter**, **priorisierte Rückfragen**, **Verfahrenskandidaten**, **Messprinzip/Sonde/Geometrie**, **Spektralbereich inkl. korrekter Einheiten**, **Begründung**, **Grenzen/Risiken**, **konkrete Feasibility-Schritte**, **Entscheidungsmaßstab**, **prüfbare AFS-Quellen**.
3. Unsichere Fälle führen zu `provisional` / `insufficient_information` / `out_of_scope`, niemals zu erfundenen Messwerten oder einer unbegründeten finalen Spezifikation.
4. **AFS-Unterlagen sind die Hauptquelle.** Externe Quellen sind optional; falls genutzt, verlangt der Brief zusätzlich **Zitatpassage und URL**. Für schnelle Umsetzung empfehlen wir, externe Quellen zunächst auszuschalten.
5. Ein **funktionierender Prototyp** und ein **reproduzierbarer Startbefehl** existieren. Das System kann live eine neue Frage bearbeiten.
6. **H01–H06 werden vom Assistenten erzeugt, nicht von Hand geändert und nicht durch fallbezogene Sonderregeln programmiert**; Ergebnisse liegen im Repository.
7. Öffentlicher Git-Stand mit README, Source Code, Setup, Systemarchitektur, Ergebnissen sowie Links zu Slides (PDF) und Demovideo (**max. 5 Minuten**); zusätzliche Angaben im Formular beachten.

## 5. Wissen aus dem AFS-Material – wonach das System unterscheiden muss

| Ansatz | Plausibler Testkontext laut Material | Zu beachtende Grenzen | Primärbelege |
|---|---|---|---|
| NIR | Pulver, streuende/undurchsichtige Produkte per Reflexion; relativ klare Flüssigkeiten ggf. Transmission/Transflexion | überlappende Banden, Matrix- und Streueffekte, anwendungsspezifische Kalibrierung | S01 S. 5, 6, 10, 14–15, 17–18 |
| MIR/ATR | Flüssigkeiten, Pasten, weiche Feststoffe, Oberflächenkontakt; Wasser in Petroleum als Testansatz | Kompatibilität von IR-Faser und Kristall, Kontakt, Belag, tatsächlicher nutzbarer Bereich | S01 S. 5–6, 9–10; S02 S. 6, 13–14 |
| Raman | ergänzender Kandidat für Pulver und Flüssigkeiten; spezifische chemische Information | schwache Signale, Fluoreszenzhintergrund, Laser-Anregung und Raman-Shift getrennt benennen | S01 S. 5–6, 11–12, 14–16 |
| Fluoreszenz | begründeter fluoreszierender Marker/Indikator | hohe Empfindlichkeit ≠ direkter Nachweis beliebiger Stoffe | S01 S. 5–6, 16; S04 |
| UV/Vis | definierte Absorption bzw. optische Signale | Trübung/Überlagerung; optische Dichte nicht automatisch viable Zellzahl | S01 S. 5–6, 16 |
| Kombinationen | Nur dort vergleichen, wo komplementäre Informationen plausibel sind | Mehrwert muss gegenüber einzelnen Verfahren demonstriert werden; gleicher Messort/Zeitpunkt wichtig | S01 S. 7–9; S04 |

Nominale Bereiche laut AFS-Referenz: **NIR 780–2500 nm**, **MIR 4000–400 cm⁻¹**. Bei Raman Anregungswellenlänge (nm) und Raman-Verschiebung (cm⁻¹) nicht vermischen. Die Tabelle `AFS_method_comparison_table.xlsx` enthält qualitative statt gemessener Sensitivitäts-/Kostenbewertungen; sie ist eine **Transkription** aus S01 S. 6, keine Produktspezifikation.

### Quellenhierarchie für den Assistenten

- **Verbindlich:** Challenge-Brief und AFS Examples/Reference (Aufgabenstellung, Formvorgaben, Vorsichtsregeln).
- **Fachlich führend:** `S01_Multispectral_Laboratory.pdf`, inklusive Tabelle S. 6; `AFS_method_comparison_table.xlsx` zur tabellarischen Suche.
- **Anwendungs-/Hardwarekontext:** `S02_AFS_Process_Control_Slides.pdf` (bildlastig, insbesondere Slides 6, 13–16; visuell prüfen).
- **Nur Proof-of-Concept:** `S03_LED_Kidney_Study_2017.pdf` (in-vitro, **keine OP-Freigabe**) und `S04_Combi_MIR_Fluorescence_2021.pdf` (Modellgewebe, kein genereller klinischer Leistungsbeleg).
- **Unternehmenskontext, keine Leistungsvalidierung:** `S05_AFS_Flyer.pdf`, `S06_Laboratory_Link.txt`.

## 6. Schnellste belastbare Architektur

**Empfohlen:** **Python + Streamlit + Pydantic + PyMuPDF + OpenAI-kompatibles LLM-API + lokaler Wissensindex (JSON/JSONL)**. Kein Kubernetes, keine Datenbankserver, kein Login, kein unnötiges Multi-Agent-Runtime-Framework.

### Warum bewusst klein?

- Wenig Betriebsrisiko und leichte Demo.
- Alle Artefakte liegen lesbar im Repo.
- Kleinere Dokumentmenge: **klassischer Stichwort-/BM25-artiger Retrieval-Index oder begrenzte hybride Suche** reicht als erster Schritt; Vektor-DB ist optional, kein Selbstzweck.
- Serverseitige Modellanfragen bleiben austauschbar; ohne API-Key kann ein dokumentierter Offline-/Fixture-Modus *nur für UI-/Format-Tests* laufen. Demo/Ergebnisgenerierung muss echte neue Anfragen verarbeiten.

### Pipeline (modular, testbar)

1. **Ingestion:** PDF-Seiten separat extrahieren (`S01`–`S05`), `.docx` Entwicklungsreferenz, `.xlsx` Vergleichstabelle. Seitenquelle als `source_id`, `page`, `text`, `kind` persistieren. Für bildbasierte `S02`-Slides eine **manuell geprüfte, allgemeine** Seitenbeschreibung als statische Wissensnotiz anlegen (nicht szenariospezifisch). Auszüge aus S03/S04 nicht zu klinischen Behauptungen ausweiten.
2. **Retrieval:** Anfrage und abgeleitete Themen durchsuchen; relevante Quellenabschnitte samt Metadaten an das Modell liefern. Quellen-ID/Seiten-Angabe stabil und reproduzierbar halten. Gemeinsame methodische Basissnippets + passende Anwendungsbelege berücksichtigen.
3. **Analysis:** Striktes Schema erzwingen (`Pydantic`/JSON), Fakten getrennt von Annahmen und fehlenden Angaben; konditionale Vorschläge statt Gewissheit.
4. **Citation verification:** Zitierte Seiten müssen im Index existieren; überprüfbare Textpassage/belegte Aussage anzeigen. Eine existierende Seite allein beweist den Claim nicht: kritische Aussagen in Tests gegen den Beleg prüfen. Keine erfundenen Quellen.
5. **Render/UI:** Klar gegliederte Antwort mit Quellen, Entscheidungsstatus, Vergleich von Kandidaten, exportierbarem JSON/Markdown.
6. **Batch runner:** Gleiche Pipeline für D01–D08 (Entwicklung) und H01–H06 (finale Dateien). Laufparameter, Modellname, Zeitstempel, Version/Commit und erzeugte Rohantworten protokollieren.

**Wichtige Entwurfsentscheidung:** Keine sechs separat improvisierten Agenten in Produktion. Ein **klarer Orchestrator mit 2–3 logischen Stufen** (Retrieve → Recommend → Validate) ist schneller, debugbarer und unter Zeitdruck robuster. Mehrere **Coding-Agents** dürfen parallel an unabhängigen Modulen arbeiten.

### Vorgeschlagenes Antwortschema

```json
{
  "decision_status": "provisional",
  "stated_facts": ["..."],
  "assumptions": [],
  "unknowns": ["..."],
  "clarification_questions": [{"question": "...", "why_it_matters": "..."}],
  "recommendations": [{
    "method": "NIR",
    "role": "primary_candidate",
    "why": "...",
    "conditions": ["..."],
    "measurement_geometry": "diffuse reflection",
    "spectral_range": {"value": "780–2500", "unit": "nm", "scope": "nominal_method_only"},
    "source_refs": [{"id": "S01", "page": 10}]
  }],
  "measurement_concept": "...",
  "risks_and_limits": ["..."],
  "feasibility_plan": [{"step": 1, "action": "...", "evidence_needed": "..."}],
  "go_no_go_criteria": ["Agree application-specific acceptance thresholds with customer"],
  "overall_sources": [{"id": "S01", "page": 10}]
}
```

Schema als **Implementierungsvorschlag**, nicht als offizielles Pflichtformat. Bei `insufficient_information` sind *keine unbegründeten Methodenfestlegungen* erforderlich; gegebenenfalls bedingte Kandidaten nennen.

## 7. Agentic Vibe Coding – parallele Arbeit ohne Merge-Chaos

**Eine Person ist Integrator / Maintainer.** Alle Agents erhalten den Challenge-Brief und dieses Strategiepapier, arbeiten auf separaten Branches/Worktrees und haben explizite Dateigrenzen. Keine zwei Agents ändern dieselbe Hauptdatei gleichzeitig.

| Spur | Agent | Ergebnis | Dateibereich | Fertig wenn … |
|---|---|---|---|---|
| A | **Knowledge-Agent** | PDF-/DOCX-/XLSX-Ingestion, Quellenkatalog, Retrieval | `src/knowledge/**`, `data/index/**` | Seitenzitate stabil, S02-Slides 6/13/14 sichtbar erfasst |
| B | **Reasoning-Agent** | Prompt/Schema, fachliche Verhaltensregeln, Analysefunktion | `src/engine/**`, `src/models.py` | bei unvollständiger Anfrage kein Fake-Detail, JSON valide |
| C | **UI-Agent** | Streamlit-Maske mit Antwortsektionen/Quellen/Download | `app.py`, `src/ui/**` | eine neue Anfrage interaktiv vorführbar |
| D | **QA-Agent** | Tests, Szenario-Runner, CLI, Auswertungsbericht | `tests/**`, `scripts/**`, `outputs/**` | D01–D08 durchlaufbar, H-Batch generisch ausführbar |
| E | **Integrator / Teamlead** | API-Vertrag, PR-Review, Secrets/Setup, Repo/README, Slides, Video, finale Abgabe | `README.md`, `requirements.txt`, `docs/**`, Repo-Settings | Clone → Install → Run auf frischem System |

**Schnittstellenvertrag vor paralleler Arbeit:** `src/engine/service.py: analyze(query: str) -> AnalysisResult`; `src/knowledge/retrieval.py: retrieve(query: str, k: int = 8) -> list[Evidence]`; Pydantic-Typen in `src/models.py`. Darauf können Agents unabhängig aufbauen. UI soll zunächst mit einem Mock des Schemas arbeiten, nicht auf LLM-Code warten.

### Code- und Agent-Regeln

- Kein Hardcoding nach Szenario-ID oder Formulierungen aus H01–H06.
- H-Datei nie in Prompt, Retrieval-Korpus oder Beispielsammlung für die eigentliche Vorhersage übernehmen; nur als **Batch-Input nach Freeze** verwenden.
- Keine Beispielantworten D01/D02 blind als Retrieval-Wissen für neue Kundenfälle missbrauchen; die **Fachquellen** tragen die technischen Begründungen.
- Keine ungetesteten schweren Abhängigkeiten und keine geheimen Schlüssel im Repo.
- Klare Fehlerbehandlung bei fehlendem Key/API-Fehler/Timeout, damit die Demo nicht abstürzt.
- Jede Agent-Änderung mit kleinem Test und Commit/PR abgeben; Integrator merged laufend.

## 8. Taktischer Zeitplan – „funktioniert zuerst, hübsch danach“

**Die folgenden Zeiten sind relative Arbeitsblöcke ab Teamstart, keine Behauptung über die verbleibende Uhrzeit.** Deadline laut Kick-off: Sonntag 23:59 Uhr; möglichst deutlich früher einreichen.

| Phase | Dauer | Hauptziel | Harte Abnahme |
|---|---:|---|---|
| **0. Kickoff** | 20–30 min | Public Repo, Ordner, API-Vertrag, Tasks/Branches, API-Key testen | `streamlit run app.py` startet als Skeleton |
| **1. Wissensbasis** | 60–120 min | Seitenindex, Fachreferenzen, methodische Tabellen, S02-Bildnotizen | belegbarer Treffer für NIR, MIR, Raman, Fluo |
| **2. MVP vertikal** | 90–150 min | Eine echte Freitextanfrage durch gesamte Pipeline | strukturierte Antwort mit echten Quellen |
| **3. Fachliche Stabilisierung** | 2–4 h | D01–D08, Hardcases, kritische Behauptungen, Quellenprüfung | keine gravierenden erfundenen Daten/Fehlzitate |
| **4. Final-Evaluation** | 60–90 min | Pipeline einfrieren, H01–H06 automatisch erzeugen und abspeichern | sechs unbearbeitete Ergebnisdateien plus Run-Metadaten |
| **5. Packaging & Demo** | 2–3 h | README, Setup von sauberer Umgebung, Slides, <5 min Video | fremde Person kann starten, Links im Inkognito funktionieren |
| **6. Puffer** | 60–120 min | Fehlerbehebung und Einreichung | Formular bestätigt, keine offenen Blocker |

### Entschiedene Scope-Grenzen

**Muss:** belastbare Freitextanalyse, AFS-Belege, strukturierte Beratung, sinnvolle Fragen, Testplan, funktionierendes UI, Batch-Outputs, dokumentiertes Setup.

**Kann, wenn Zeit:** Method-Cards, Vergleichsansicht, PDF/Markdown-Export, Quellenseiten-Vorschau, einfache Treffer-Scores.

**Nicht bauen:** Sensor-Hardware, Echtzeit-IoT, ausufernde Agent-Frameworks, Nutzerkonten, Produktionsdeployment, Chat-History-Datenbank, automatisch recherchiertes Internet, generische chemische Allwissensdatenbank.

## 9. Qualitätssicherung – echte Failure-Modes testen

**D01–D08** sind die Entwicklungsfälle. Die **offiziellen Beispielantworten D01 und D02** sind Kalibrierungsmaßstab für vorsichtigen Ton, Aufbau und Experimentlogik, nicht Vorlagen zum Auswendiglernen. Zusätzlich eigene, neue Negativfälle ohne Szenario-IDs testen.

Prüfpunkte (jeweils automatisiert wo möglich, manuell bei wissenschaftlichem Urteil):

1. **Keine erfundenen Fakten:** Unbekannte Konzentration, Produktzusammensetzung, Messdauer, Genauigkeit oder Kabelstrecke werden gefragt, nicht behauptet.
2. **Methoden-/Matrix-Fit:** Streuende Probe vs. klare Probe; Kontakt/ATR vs. Reflexion; Prozessbedingungen.
3. **Citations:** Jede tragende technische Behauptung erhält eine stützende AFS-Stelle, richtige Seite, keine Fantasie-URLs.
4. **Korrekte Unsicherheit:** Bereits vorhandene Kalibrierung ist nicht automatisch auf neue Rezepturen übertragbar; mehr Verfahren sind nicht automatisch besser.
5. **Keine Sensitivitätsverwechslung:** Fluoreszenz-Empfindlichkeit beweist weder direkte Glucosemessung noch viable Zellzahl.
6. **Wellenlängenkompatibilität:** Vis/NIR-Silica ist nicht ohne Nachweis ein MIR-Link; nominelle Methodenspanne ≠ Faserspanne.
7. **Proof-of-Concept ≠ Freigabe:** In-vitro-Kidney-Studie beweist keine unmittelbare Einsatzreife für Operationen.
8. **Plan wirklich nützlich:** Repräsentative Proben, unabhängige Referenztests, konkurrierende Verfahren, held-out Chargen/Läufe, vorab festgelegter Entscheidungstest.
9. **Live-Generalisierung:** neue, bislang nicht gesehene Anfrage funktioniert mit identischem Ablauf.

**Bewertung als interne Heuristik:** je Testfall `0/1/2` für Vollständigkeit, fachliche Plausibilität, Quellen, Rückfragen, Risiken, Experiment. Zusätzlich **kritische Blocker** separat markieren (erfundene Messdaten, klinische Freigabe, unmögliche Faserfreigabe, kaputtes UI). Die interne Punktzahl ist **keine** offizielle Jurywertung.

### Umgang mit H01–H06

Die sechs finalen Szenarien sind im Material bereits enthalten. **Nicht vorab als Trainingsdaten, fallbezogene Promptbeispiele oder Spezialregeln einsetzen.** Nach der D-Entwicklung Code/Prompt-Version festhalten und mit dem **generischen** Runner erzeugen; Modellantworten als Dateien unverändert speichern; technische Run-Logs zusätzlich beilegen. Ein Fehler führt zu einem transparent dokumentierten erneuten **generischen** Lauf oder allgemeinen Code-Fix, nicht zur manuellen Bearbeitung einer Antwort.

## 10. Reproduzierbares Repository – Zielstruktur

```text
afs-spectroscopy-assistant/
├── app.py
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt              # oder pyproject.toml + lock
├── src/
│   ├── models.py
│   ├── knowledge/{ingest.py,retrieval.py,catalog.py}
│   ├── engine/{service.py,prompts.py,validators.py}
│   └── ui/
├── data/
│   ├── source/                  # AFS-Material, nur falls Weitergabe erlaubt
│   └── index/                   # nachbaubar; alternativ mit versioniertem Index
├── scripts/
│   ├── build_index.py
│   ├── run_scenarios.py
│   └── check_citations.py
├── tests/
├── outputs/
│   └── final_evaluation/        # H01–H06, generiert & unverändert
└── docs/
    ├── architecture.md
    ├── strategy.md
    └── presentation.pdf         # oder stabiler Link
```

**Hinweis zu Materialien im Public Repo:** Urheber-/Weitergaberechte der AFS-PDFs und Papers prüfen. Wenn Originaldateien nicht veröffentlicht werden dürfen, Setup zum lokalen Ablegen der Dateien und einen freigegebenen Index/Downloadprozess dokumentieren. **Die Jury muss die Lösung trotzdem ohne Teamhilfe reproduzieren können**; also nicht von geheimen lokalen Dateien abhängen. API-Key über Umgebungsvariable, `.env.example` ohne Secret; Lauf ohne Key dokumentiert verständlichen Fehler bzw. expliziten Demonstrationsmodus.

### README muss beantworten

Was wird gelöst? Welcher Python-Stand? Installation Schritt für Schritt? Woher kommen die AFS-Dateien? Wie entsteht der Index? Wie setzt man `OPENAI_API_KEY`/Provider-Modell? Startkommando? Beispielinput? Wie generiert man D- und H-Ausgaben? Welcher Commit/Modellkonfiguration erzeugte die eingereichten H-Dateien? Was sind Einschränkungen? Wo sind PDF-Slides und das Video?

## 11. Video/Pitch (maximal 5 Minuten)

- **0:00–0:35** Industrielles Problem und warum methodische Auswahl schwierig ist.
- **0:35–1:05** Unsere Lösung und welche Fachquellen sie benutzt.
- **1:05–3:10** Live-/aufgezeichnete **neue** Kundenanfrage → Fakten, Fragen, Varianten, Belege, Pilotplan, Unsicherheit.
- **3:10–4:10** Quellenprüfung und bewusst vorsichtiger Edge Case.
- **4:10–4:45** Architektur, reproduzierbarer Start, Nutzen für AFS.
- **Puffer bis 5:00**, nicht überschreiten.

**Demo-Narrativ:** „Wir ersetzen keinen Fachingenieur. Wir machen aus unsortierten Kundenanfragen in Minuten ein überprüfbares, vorsichtiges technisches Erstgespräch.“ Keine ungemessenen Genauigkeits-/Zeitersparniswerte nennen.

## 12. Sofortige erste Aktionen des Teams

1. Öffentlichen Repo-Namen und Integrator bestimmen; Zugang und Branch-Schutz sinnvoll einstellen.
2. Alle 10 bereitgestellten Materialien lokal in definierter Struktur ablegen; Commit-Rechte für Weitergabe prüfen.
3. API-Anbieter/Modell festlegen und vor allem **eine einzige** Live-Anfrage bis zur Modellantwort testen.
4. Agents A–D mit getrennten Dateirechten starten; Schnittstellenvertrag zuerst festziehen.
5. D01 und D02 als erstes integriertes Qualitätstor verwenden, danach D03–D08 und Negativfälle.
6. **Früh** H-Batchlauf, Installationsprobe, 5-Minuten-Demo und Link-Prüfung einplanen; Formular keinesfalls erst 23:59 abschicken.

## 13. Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| LLM halluziniert Chemie oder Genauigkeit | verbindliche Vorsichts-Prompts, Quellenbelege, Validator, Negativtests |
| Halluzinierte Quelle oder falsche Seite | seitenbasierter Katalog und Citation-Check; S02 visuell gegenlesen |
| Agents überschreiben sich | unabhängige Ordner/Branches und ein Integrator |
| RAG zu kompliziert/instabil | einfacher lokaler Seitenindex, begrenztes Retrieval; optional später Embeddings |
| API-Limit oder Demo-Ausfall | Retry/Timeout/Fehleranzeige; fertiges Video; expliziter Fixture-Modus nur als Backup |
| Public Repo kann AFS-Material nicht enthalten | Rechte prüfen, autorisierten Bereitstellungsweg + vollständige Setup-Anleitung |
| H-Ergebnisse wirken manuell geschönt | generischer Runner, Rohdateien, Metadaten, eingefrorene Konfiguration |
| Abgabe-Link unzugänglich | sämtliche URLs Inkognito und ohne Teamkonto testen |

---

### Dokumentgrundlage / genaue Fundstellen

- `AI-based molecular media analysis by process-spectroscopy in-line.pdf`: Challenge, Minimalanforderungen, Bewertung, Liefergegenstände S. 1–2.
- `AFS_Examples_and_Reference.docx`: D01–D08 S. 1–3; ausgearbeitete D01/D02-Beispiele S. 4–5; Qualitätsregeln S. 6; Quellenleitfaden S. 7; Methodentabelle S. 8.
- `S01_Multispectral_Laboratory.pdf`: Methodengrundlagen/vergleich S. 5–6; Kombinationen S. 7–9; technische Beschreibungen und Anwendungen S. 10–18.
- `S02_AFS_Process_Control_Slides.pdf`: Fasern und Anwendungsfälle, insbesondere S. 6, 13–16.
- `S03_LED_Kidney_Study_2017.pdf`: in-vitro-Proof-of-Concept, Abstract S. 1.
- `S04_Combi_MIR_Fluorescence_2021.pdf`: kombiniertes MIR-/Fluo-Messkonzept, S. 1–4.
- `AFS_method_comparison_table.xlsx`: maschinenlesbare Methode/Geometrie/Matrix-Tabelle; Tab `notes` erläutert die Transkription.
- `customer_scenarios_for_final_evaluation.txt`: H01–H06 und Regeln für unbekannte Kundenangaben.

**Trennung:** Alle genannten Challenge-Regeln und wissenschaftlichen Beispiele stammen aus den bereitgestellten Unterlagen. Stack, Agent-Aufteilung, Aufwandsschätzungen, Schema und UI sind **unsere Umsetzungsvorschläge**.
