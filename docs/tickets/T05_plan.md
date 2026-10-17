# T05 — Few-Shot-Speicher D01–D08 · Umsetzungsplan

> Basiert auf `T05_analysis.md`. Ziel: kuratierte D01–D08-Entwicklungsbeispiele
> (getrennt von Fachevidenz) + ein **generischer**, deterministischer
> `select_examples(query, k=2) -> list[FewShotExample]` (Contract `ExampleSelector`).
> **Kein** Retrieval (T04), **keine** Regeln (T03), **keine** LLM/Prompt-Logik,
> **keine** Änderung an `src/models.py` oder `src/engine/prompts.py` (Jakob).

## Zerlegung in Arbeitspakete (AP0–AP5)

### AP0 — Beispieldaten-Grundgerüst (`data/examples/`)
- `data/examples/dev_examples.yaml`: die **8** D-Fälle, von Hand kuratiert,
  wörtlich aus der DOCX:
  - je Eintrag: `example_id` (D01..D08), `query` (Szenariotext),
    `reference_answer` (NUR D01/D02; sonst leer/weggelassen → `None`),
    `provenance` ("AFS_Examples_and_Reference.docx §1 scenario" bzw. für D01/D02
    zusätzlich "§2 worked example — development reference, not independent
    evidence").
  - **Keine erfundene Antwort** für D03–D08.
- `data/examples/README.md`: Zweck (Ton/Struktur-Kalibrierung), Abgrenzung zu
  `data/index/` (keine zitierfähige Fachevidenz), Auswahl-/Limit-Regeln,
  H-Ausschluss, Übergabe an T09/T11.

### AP1 — Datentypen & Laden (`src/knowledge/examples.py`, obere Hälfte)
- Lazy Re-Use des Contracts: `from src.models import FewShotExample`.
- `load_examples(path=DEFAULT) -> list[FewShotExample]`:
  - YAML lesen (PyYAML mit stdlib-Fallback, gleiches Muster wie rules.py).
  - **Validierung beim Laden:**
    - genau **D01–D08**, keine Duplikate, keine anderen IDs (H0x etc.) →
      `ExampleConfigError` (lokale AFSError-Subklasse).
    - `reference_answer` nur dort gesetzt, wo die DOCX eine hat (D01/D02);
      sonst `None`.
    - `provenance` nicht leer.
  - Rückgabe als `FewShotExample`-Objekte (pydantic). Pure-Parsing (ohne
    pydantic) separat testbar.

### AP2 — Auswahllogik (`src/knowledge/examples.py`)
- `select_examples(query, k=2) -> list[FewShotExample]` — erfüllt **exakt**
  `ExampleSelector`.
  - Input-Validierung: `query` non-empty str → ValueError; `k` int und
    1≤k≤8 (= Anzahl D-Fälle) → ValueError. Default `k=2` (dokumentiert begrenzt).
  - Scoring: **generisch**, deterministisch — lexikalische Ähnlichkeit
    query↔(example.query) (unicode-normalisiert, case-insensitiv, reines Python;
    gleiche Normalisierungsidee wie T04/V-2).
  - **Tie-Break-Gewichtung:** bei gleichem Score Beispiele **mit**
    `reference_answer` leicht bevorzugen (D01/D02 = Kalibrierungsmaßstab), dann
    stabil nach `example_id`. Rein generisch, **keine** Szenario-ID-Verzweigung.
  - Top-`k` zurück, deterministische Reihenfolge.

### AP3 — Interne Helfer
- `_normalize(text)` (NFC+casefold+Whitespace), `_lexical_score(q, text)` —
  pure-logic, ohne pydantic/httpx testbar (ggf. aus gemeinsamer Idee, aber
  **eigene** Funktion in examples.py; kein Import aus retrieval.py nötig, um
  Kopplung gering zu halten — Duplizierung ist hier akzeptabel und bewusst).

### AP4 — Tests (`tests/test_examples.py`)
- `test_examples_load_all_eight_dev_cases` (genau D01–D08).
- `test_only_d01_d02_have_reference_answers` (D03–D08 → None;
  Abnahmekriterium 1 + 4).
- `test_no_h_ids_in_examples_file` (liest Datei, verbietet H0x;
  Abnahmekriterium 5) + `test_contract_rejects_non_d_ids` (FewShotExample mit
  z. B. "H01"/"D09" → ValidationError, pydantic-guarded).
- `test_select_rejects_bad_input` (leere query, k außerhalb 1..8, k nicht int).
- `test_select_is_deterministic_and_limited` (gleiche Query → gleiche Reihenfolge;
  default k=2; max begrenzt; Abnahmekriterium 3).
- `test_select_ranks_relevant_example_first` (z. B. „petroleum water" → D06 vorn;
  „dairy fat protein" → D02 vorn) — **generisch** auf den echten D-Texten,
  keine Hardcode-ID-Logik im Code.
- `test_reference_answer_examples_preferred_on_tie` (Tie-Break).
- `test_examples_are_separate_from_evidence_index` (Selector liest NICHT
  `evidence.jsonl`; Abnahmekriterium 2).
- `test_select_matches_exampleselector_protocol` (Signatur/Typ, pydantic-guarded).
- Lib-/pydantic-abhängige Pfade via `importorskip`; Pure-Logik auf stdlib.

### AP5 — Doku & Schnittstellen-Notiz
- `data/examples/README.md` fertig.
- Kurze Notiz (im PR) an Jakob: `select_examples(query, k=2)` liefert
  `list[FewShotExample]` (Contract), `reference_answer=None` wo keine Antwort;
  Einbindung in `prompts.py`/Synthese macht Jakob — ich ändere die Datei nicht.
  Hinweis: Musterantworten D01/D02 sind **Struktur-/Ton-Vorbild**, keine
  unabhängige Fachevidenz (nicht als Beleg zitieren).

## Offene Entscheidungen für Kevin

1. **Default k=2, max k=8** (dokumentierte Begrenzung) — ok?
2. **Tie-Break: Beispiele mit reference_answer (D01/D02) leicht bevorzugen** —
   ok, oder strikt nur nach Ähnlichkeit (dann D01/D02 nicht bevorzugt)?
3. **reference_answer-Text:** vollständige DOCX-Musterantwort übernehmen (lang,
   aber vollständig) — oder nur den strukturellen Kern? Empfehlung: **vollständig
   und wörtlich** (keine Verfälschung, `provenance` dokumentiert Herkunft).

## Definition of Done

- `data/examples/dev_examples.yaml` mit D01–D08; nur D01/D02 mit
  `reference_answer`; getrennt von `data/index/`.
- `select_examples(query, k=2)` erfüllt `ExampleSelector`; deterministisch,
  begrenzt, generisch (keine Fall-Sonderregeln).
- H01–H06 ausgeschlossen (Contract-Regex + Datei + Test).
- Keine erfundenen Antworten/Leistungsbehauptungen.
- Tests grün (pure-logic Sandbox; voller Lauf lokal). `src/models.py` und
  `src/engine/prompts.py` unberührt. **Kein LLM/Key nötig.**
