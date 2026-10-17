# T02 — AFS-Quellen aufbereiten · Deep-Dive-Analyse

> Branch: `T02-afs-quellen-aufbereiten` · Verantwortlich: Kevin
> Diese Datei dokumentiert die Material-Analyse **vor** der Umsetzung. Sie ist die
> Grundlage für `T02_plan.md`.

## 1. Was T02 verlangt (Abnahmekriterien, wörtlich aus dem Ticket)

- [ ] Vorhandene und fehlende Eingabedateien sind im Quellenkatalog dokumentiert.
- [ ] PDF-Passagen besitzen `source_id`, 1-basierte Seite, Text und stabile ID.
- [ ] Bildlastige S02-Seiten insbesondere 6 und 13–16 sind visuell geprüft; Notizen sind als solche markiert.
- [ ] XLSX-Transkription und DOCX-Entwicklungsreferenzen werden getrennt von Primärevidenz geführt.
- [ ] H01–H06 werden nicht in Wissens- oder Beispielindizes aufgenommen.
- [ ] Weitergabe und lokaler Bereitstellungsweg der Materialien sind dokumentiert.

**Dateibereich laut Ticket:** `src/knowledge/ingest.py`, `catalog.py`, `scripts/build_index.py`
**Abhängigkeit:** T01 (Projektgrundlage / `src/models.py`).

## 2. Umgebungs-Befund (wichtig!)

| Befund | Konsequenz für T02 |
|---|---|
| Python 3.11.15 vorhanden | OK |
| **PyPI ist in dieser Sandbox blockiert** (Proxy liefert 403; `pip install pymupdf` schlägt fehl) | PyMuPDF/python-docx/openpyxl können hier **nicht installiert** werden. Code wird so geschrieben, dass er diese Libs nutzt, aber die *Ausführung*/Index-Bau muss auf Kevins lokaler Maschine erfolgen. |
| Kein `pdftotext`, `mutool`, `libreoffice` im System | Analyse erfolgte über `unzip` (DOCX/XLSX = ZIP) und Roh-Strukturanalyse der PDFs. |
| **T01 existiert noch nicht** (`src/models.py` fehlt) | T02 darf T01 nicht überschreiben. Wir definieren nur die *minimal nötigen* Evidenz-/Katalog-Datentypen lokal im `knowledge`-Modul und halten sie kompatibel zum Interface-Vertrag (`Evidence`), damit T01 sie später übernehmen/ersetzen kann. |

## 3. Material-Inventar (real verifiziert)

Alle 10 Pflicht-Eingaben aus dem Masterprompt sind vorhanden unter `materials/`.

| ID | Datei | Typ | Extrahierbarkeit | Quellenrang |
|----|-------|-----|------------------|-------------|
| **BRIEF** | `AI-based molecular media analysis by process-spectroscopy in-line.pdf` | PDF, ~3 S. | textbasiert (17 Font-Refs) | Aufgabenstellung/Regeln |
| **S01** | `S01_Multispectral_Laboratory.pdf` | PDF, 19 S. | **textbasiert** (50 Fonts, 15 JPEG-Bilder) — Kerndokument | fachlich führend |
| **S02** | `S02_AFS_Process_Control_Slides.pdf` | PDF, 20 Slides | **bildlastig** (20 Fonts, **917 Image-Refs**, 304 JPXDecode) → Textextraktion liefert ~nur Titel | Anwendung/Hardware |
| **S03** | `S03_LED_Kidney_Study_2017.pdf` | PDF, ~17 S. | textbasiert (29 Fonts) | nur Proof-of-Concept (in-vitro) |
| **S04** | `S04_Combi_MIR_Fluorescence_2021.pdf` | PDF, ~6 S. | textbasiert (9 Fonts) | nur Proof-of-Concept |
| **S05** | `S05_AFS_Flyer.pdf` | PDF, 2 S. | **bildlastig** (2 Fonts, 91 Bilder) | nur Unternehmenskontext |
| **S06** | `S06_Laboratory_Link.txt` | TXT | trivial; enthält nur `https://mirphotonics.com/laboratory/` | nur Unternehmenskontext (**keine PDF-Seite!**) |
| **DOCX** | `AFS_Examples_and_Reference.docx` | DOCX | **vollständig extrahierbar** via `unzip` | Entwicklungsreferenz (D01–D08), **keine Primärevidenz** |
| **XLSX** | `AFS_method_comparison_table.xlsx` | XLSX | **vollständig** (inline strings, 2 Sheets) | Transkription von S01 Tab.1 (p.6) |
| **H** | `customer_scenarios_for_final_evaluation.txt` | TXT | — | **NUR Finaler Batch-Input — NIE indexieren** |

Zusätzlich vorhanden (nicht in der Pflichtliste): `Spectroscopy_Assistant_QA_schedule_17_October*.pdf` → Orga-/Zeitplan, **keine Fachevidenz**, nicht indexieren.

## 4. Was die DOCX inhaltlich liefert (bereits gelesen)

- **Abschnitt 1:** D01–D08 Szenariotexte + „Facts stated" + „Useful sources" (Seitenhinweise).
- **Abschnitt 2:** ausgearbeitete Musterantworten **D01 & D02** (Kalibrierungsmaßstab für Ton/Struktur — gehört zu **T05 Few-Shot**, nicht zur Primärevidenz).
- **Abschnitt 3:** empfohlene Antwortstruktur + „Do not invent"-Liste + häufige Fehler.
- **Abschnitt 4:** **offizieller Quellenkatalog** (S01–S06 Inhalt/Seiten + Zitierregeln) → maßgeblich für `catalog.py`.
- **Abschnitt 5:** Methodenübersicht mit nominalen Bereichen (NIR 780–2500 nm, MIR 4000–400 cm⁻¹, …) und Quellenseiten.

**Zitierformat (aus den Musterantworten abgeleitet):** `S01 p.10`, Seitenbereich `S01 p.14–15`, Tabelle `S01 Table 1 (p.6)`, Slide `S02 p.13`. Seiten sind **1-basiert inkl. Titelseite**.

## 5. Was die XLSX liefert (bereits gelesen)

- Sheet `method_comparison`: 19 Datenzeilen, Spalten `method_no, method, measurement_technique, physical_phenomenon, sample_type, optical_path_or_depth, sensitivity, selectivity, cost`.
- Sheet `notes`: dokumentiert Herkunft = **S01 Table 1, p.6**; „sensitivity/selectivity/cost sind qualitative Ratings (low/average/high), keine Messwerte"; `um` = Mikrometer; `ATR probe*` trägt einen Stern ohne gedruckte Fußnote.
- **Regel daraus:** XLSX ist Transkription, **keine Produktspezifikation** — qualitative Ratings nie als quantitative Gerätewerte ausgeben.

## 6. Kernrisiken, die T02 adressieren muss

1. **S02 nicht halluzinieren.** Textextraktion liefert fast nichts → wir erzeugen **manuell geprüfte, als `verified_note` markierte** Seitennotizen für die Schlüssel-Slides (6, 13–16) auf Basis des offiziellen DOCX-Quellenkatalogs (der genau beschreibt, was auf diesen Slides steht: Fasertypen/Transmissionsbereiche p.6–10, Wasser in Petroleum p.13, API in Polymerextrusion p.14, Kombiprobe p.15–16). Kein erfundener Slide-Inhalt.
2. **H01–H06 niemals in den Index.** Harte Allowlist der zu ingestierenden Dateien + Test, der die H-Textsignaturen im Index verbietet.
3. **Primärevidenz vs. Transkription vs. Entwicklungsreferenz strikt trennen** über ein `kind`-Feld pro Evidenzsatz (`pdf_text`, `verified_note`, `table_transcription`, `dev_reference`, `business_context`).
4. **S06 ist keine PDF-Seite** → `page=None`, `kind=business_context`.
5. **Weitergaberecht der AFS-PDFs unklar** → Setup dokumentiert lokalen Bereitstellungsweg (Dateien lokal unter `data/source/` ablegen), Index nachbaubar; keine Secrets, keine ungeklärten Rechte in Git erzwingen.
