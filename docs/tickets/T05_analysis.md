# T05 — Few-Shot-Speicher D01–D08 · Deep-Dive-Analyse

> Branch: `feat/t05-fewshot-examples` (von aktuellem `main`) · Verantwortlich: Kevin
> Analyse **vor** der Umsetzung. Grundlage für `T05_plan.md`.

## 1. Was T05 verlangt (Abnahmekriterien, wörtlich)

- [ ] D01–D08 werden als Entwicklungsfälle geführt; **nur tatsächlich vorhandene
      Referenzantworten** werden als solche bezeichnet.
- [ ] Beispiele sind **getrennt** von zitierfähiger Fachliteratur gespeichert.
- [ ] Auswahl und Anzahl der Promptbeispiele sind **begrenzt und dokumentiert**.
- [ ] Beispielantworten **begründen keine technischen Leistungsbehauptungen**.
- [ ] H01–H06 sind ausgeschlossen; Auswahl/Pipeline enthalten **keine
      Fall-Sonderregeln**.

**Dateibereich:** `src/knowledge/examples.py`, `data/examples/` · **Abhängigkeit:** T02.
**Kollision:** keine direkten Dateikonflikte. Jakob bindet die Beispiele in
Prompts/T09/T11 ein; **Kevin ändert NICHT `src/engine/prompts.py`**. Übergabe-
format gemeinsam festgelegt.

## 2. Aktueller Stand (gemergt auf `main`)

- **Contract** (`src/models.py`):
  ```python
  class FewShotExample(ContractModel):
      example_id: Annotated[str, StringConstraints(pattern=r"^D0[1-8]$")]
      query: Text
      reference_answer: Text | None
      provenance: Text
  ```
  → `example_id` ist per Regex **auf D01–D08 beschränkt** ⇒ **H01–H06 sind
  strukturell unmöglich** (Contract wirft ValidationError). `reference_answer`
  ist optional (`Text | None`) — exakt passend, da nur D01/D02 Musterantworten
  haben.
- **Contract** (`src/contracts.py`): `ExampleSelector.__call__(query, k=2) -> list[FewShotExample]`.
- **T11-State** (`src/state.py`): Feld `examples: NotRequired[list[FewShotExample]]`
  ist **bereits reserviert**. `graph.py` dokumentiert: „T05 Few-Shot-Beispiele
  sind nicht implementiert; das Feld bleibt optional/leer, die Synthese
  akzeptiert einen leeren Pfad." → Mein Selector dockt genau hier an, ohne
  `graph.py`/`prompts.py` zu ändern.
- **T02 liefert die Rohtexte getrennt:** die DOCX (D01–D08 + Musterantworten)
  wird als **`ReferenceRecord`** ingestiert (`reference_records.jsonl`),
  **nicht** im Fach-Evidenzindex. T05 nutzt diese Trennung weiter.

## 3. Datenlage D01–D08 (real aus der DOCX verifiziert)

Die DOCX enthält:
- **Abschnitt 1:** alle **8 Szenariotexte D01–D08** (je ein Kunden-Enquiry-Text)
  + „Facts stated" + „Useful sources".
- **Abschnitt 2:** ausgearbeitete **Musterantworten NUR für D01 und D02**
  (`Decision status: Provisional feasibility assessment` …).

| ID | query (Szenariotext) | reference_answer |
|----|----------------------|------------------|
| D01 | Blend potency in a tablet press feed frame | **ja** (Musterantwort) |
| D02 | Fat and protein monitoring in opaque dairy product | **ja** (Musterantwort) |
| D03 | A clear whey stream before concentration | **nein** → `None` |
| D04 | Glucose and lactate trends in an aqueous bioprocess | **nein** → `None` |
| D05 | Biomass related monitoring during yeast fermentation | **nein** → `None` |
| D06 | Water content in a petroleum stream | **nein** → `None` |
| D07 | API concentration during hot polymer extrusion | **nein** → `None` |
| D08 | Local measurements of heterogeneous model tissues | **nein** → `None` |

→ Abnahmekriterium „nur tatsächlich vorhandene Referenzantworten als solche":
D01/D02 bekommen `reference_answer`, D03–D08 `None`. **Keine erfundenen
Antworten.**

## 4. Design-Fragen (für den Plan)

1. **Speicherort/-format:** kuratierte, von Hand geprüfte YAML/JSON unter
   `data/examples/` (analog `data/rules/`), klar als Entwicklungsreferenz
   markiert — **getrennt** von `data/index/evidence.jsonl`. Kein Vermischen mit
   zitierfähiger Fachliteratur (Abnahmekriterium 2).
2. **Auswahllogik (`select_examples(query, k=2)`):** deterministisch,
   **generisch** (keine Fall-Sonderregeln, kein `if "kidney"`). Kandidat: die
   D-Beispiele nach Ähnlichkeit zum Query ranken (dieselbe lexikalische,
   unicode-normalisierte Scoring-Idee wie T04-Retrieval, reines Python) und
   Top-`k` zurückgeben. **`k` klein und dokumentiert begrenzt** (Default 2, max
   z. B. 8 = Anzahl D-Fälle).
3. **Priorisierung D01/D02?** Da nur D01/D02 Musterantworten haben und diese den
   „Kalibrierungsmaßstab für Ton/Struktur" bilden (Strategiepapier), sollte der
   Selector bei Gleichstand Beispiele **mit** `reference_answer` bevorzugen —
   aber **ohne** szenariospezifische Hacks (reine generische Gewichtung
   „hat_reference_answer"). → offene Entscheidung.
4. **„keine technischen Leistungsbehauptungen":** Die Musterantworten D01/D02
   bleiben **wörtlich** aus der DOCX (keine erfundenen Zahlen); sie werden als
   *Struktur-/Ton-Beispiel* geführt, `provenance` sagt klar „AFS
   Examples_and_Reference.docx, worked example — development reference, not
   independent evidence". T05 selbst erzeugt **keine** neuen Fachaussagen.
5. **Keine H-Fälle:** doppelt abgesichert — (a) Contract-Regex `^D0[1-8]$`,
   (b) die Beispieldatei enthält nur D01–D08, (c) Test verbietet H0x-Strings.

## 5. Schnittstelle zu T09/T11 (Jakob)

- `ExampleSelector`-Protokoll exakt erfüllen: `select_examples(query, k=2) ->
  list[FewShotExample]`.
- Rückgabe: `FewShotExample`-Objekte (Contract), `reference_answer=None` wo keine
  Antwort existiert. Reihenfolge nach Relevanz, deterministisch.
- Jakob bindet in `prompts.py`/Synthese ein — **ich ändere diese Dateien nicht**.
  Übergabeformat (das Contract-Objekt) ist bereits vereinbart.

## 6. Risiken / offene Punkte

| Punkt | Umgang |
|---|---|
| pydantic/uv in Sandbox blockiert | Pure-Logik (Scoring, Auswahl, D-Parsing) mit stdlib testen; `FewShotExample`-Konstruktion via `importorskip`. Realer Lauf bei Kevin lokal. |
| Musterantworten wörtlich halten | D01/D02-Text direkt aus DOCX; keine Kürzung, die Aussagen verfälscht; `provenance` dokumentiert Herkunft. |
| Reference-Answer nur D01/D02 | D03–D08 strikt `reference_answer=None`; Test verifiziert, dass keine erfundene Antwort entsteht. |
| H-Ausschluss | Contract-Regex + Datei + Test. |
| Abgrenzung zu Fachevidenz | `data/examples/` getrennt; Selector liest NICHT `evidence.jsonl`; Beispiele nie als Retrieval-Evidenz ausgegeben. |
| DOCX-Weitergaberecht | wie T02: Beispieltexte aus dem bereits versionierten Material; `data/examples/` ist kuratierte, geprüfte Ableitung. |

## 7. Braucht es LLM / API-Key?

**Nein.** T05 ist reine kuratierte Daten + deterministische Auswahl-Logik.
Kein Embedding, kein LLM, kein Key. Tests laufen offline; voller Lauf lokal via
`uv run --locked pytest -q`.
