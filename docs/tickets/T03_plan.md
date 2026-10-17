# T03 — Deterministische Regel-Matrix · Umsetzungsplan

> Basiert auf `T03_analysis.md` (inkl. T06-Deep-Dive & Parameter-Versionierung).
> Ziel: belegte, qualitative Methoden-/Kompatibilitätsregeln **deklarativ** +
> eine **generische** Engine `RuleEvaluator(extraction) -> list[RuleFinding]`.
> **Kein** Retrieval (T04), **kein** Few-Shot (T05), **keine** LLM-/UI-Logik,
> **keine** Änderung an `src/models.py` (Jakobs Hoheit).

## Zerlegung in Arbeitspakete (AP0–AP6)

### AP0 — Verzeichnis & Regeldaten-Grundgerüst (`data/rules/`)
- `data/rules/rules_meta.yaml`: Versionierungs-Metadaten
  - `rule_set_version: "1.0"`
  - `parameter_contract: "T06 ParameterName (docs/parameters.md)"`
  - `expected_parameter_names: [matrix, sample_composition, …]` (exakt die 16)
- `data/rules/method_matrix.yaml`: aus XLSX (S01 Table 1 p.6) abgeleitete
  sample_type→Methode/Geometrie-Zuordnung, jede Zeile mit `source_ref`
  `S01 Table 1 (p.6)` und **qualitativem** Rating-Hinweis (nie als Zahl).
- `data/rules/compatibility_rules.yaml`: die belegten Vorsichts-/
  Kompatibilitätsregeln (Abschnitt 3c der Analyse), je mit `rule_id`,
  `conditions`, `outcome`, `reason`, `source_refs`.
- `data/rules/README.md`: Bedeutung von `excluded/conditional/unknown`,
  Schnittstelle zu T07/T08, Versionierungsregel.

### AP1 — Regel-Datentypen (`src/knowledge/rules.py`, obere Hälfte)
Interne, schlanke Pydantic-Modelle (kein Eingriff in `models.py`):
- `RuleCondition` {`parameter: ParameterName`, `predicate: Literal[...]`,
  `keywords: list[str]`, `negate: bool=False`} — Prädikate:
  `value_contains_any` (Zitat enthält eins der Keywords),
  `parameter_present`, `parameter_absent`.
- `Rule` {`rule_id`, `when: list[RuleCondition]` (AND), `requires:
  list[ParameterName]` (nötige Parameter), `outcome`, `reason`,
  `source_refs: list[SourceReference]`}.
- `RulesMeta` {`rule_set_version`, `expected_parameter_names: list[str]`}.
- `RuleConfigError(AFSError)` — eigene Fehlerklasse *lokal* in rules.py
  (nicht in `src/errors.py`, das ist T01s Datei; alternativ ValueError —
  siehe Entscheidung P1 unten).

### AP2 — Laden + Versionsverifikation (`rules.py`)
- `load_rules(rules_dir=Settings().… or data/rules) -> tuple[RulesMeta, list[Rule]]`.
- **Versions-Gate (Steering-Kern):** beim Laden
  `set(meta.expected_parameter_names) == set(get_args(ParameterName))` prüfen.
  Bei Abweichung `RuleConfigError` mit klarer Meldung (welche Parameter fehlen/
  neu sind). ⇒ Regeln können nicht still gegen eine veraltete Parameterliste
  laufen.
- Jede `RuleCondition.parameter` / `Rule.requires` muss ∈ `ParameterName` sein,
  sonst Ladefehler (fängt Tippfehler wie `temp`).
- `source_refs` jeder Regel: mind. 1, Seiten müssen zum Katalog passen
  (reuse `catalog.get_entry`), keine erfundenen Seiten.

### AP3 — Engine (`rules.py`): `evaluate_rules(extraction) -> list[RuleFinding]`
- Signatur erfüllt **exakt** `contracts.RuleEvaluator`.
- Pro Regel:
  1. **Requires-Check zuerst:** fehlt ein `requires`-Parameter in
     `extraction.stated_facts` (bzw. steht er in `extraction.unknowns`), →
     `RuleFinding(outcome="unknown", …)`. **Nie** Freigabe bei fehlenden Daten.
  2. Sonst `when`-Bedingungen (AND) gegen die Fakten matchen (Prädikate auf dem
     **Zitattext** `value`, case-insensitiv, kein Zahlenvergleich).
  3. Treffer → `RuleFinding(outcome=rule.outcome ∈{excluded,conditional}, reason,
     source_refs)`. Kein Treffer → Regel trägt nichts bei (kein Finding).
- Deterministisch: stabile Reihenfolge nach `rule_id`.
- Robust gegen T06-noch-nicht-gemergt: liest nur `parameter`/`value`/`unknowns`;
  `numeric_value`/`conflicts` optional (hasattr/getattr-sicher).
- **Konflikt-Awareness (wenn T06-Felder da):** steht ein für eine Regel nötiger
  Parameter in `extraction.conflicts`, → `unknown` („Scope strittig").

### AP4 — Regelinhalt befüllen (die eigentlichen Regeln)
Belegte, **allgemeine** Regeln (keine Szenario-IDs), u. a.:
- `calib_transfer_new_formulation` → conditional (S01 p.10,14–15)
- `raman_does_not_rescue_calibration` → conditional (S01 p.11,14–16)
- `clear_vs_turbid_geometry` → conditional (S01 p.17–18; XLSX)
- `fluorescence_without_marker` → conditional/excluded (S01 p.5–6,16; S04)
- `mir_atr_on_vis_nir_fiber` → conditional-nicht-freigeben (S01 p.6,9–10; S02 p.6,13–14)
- `nominal_range_not_fiber_range` → conditional (S02 p.6; S01 p.10)
- `undefined_target_no_spec` → unknown (S01 p.5–6; DOCX §3)
- `invitro_not_clinical` → excluded für OP-Claim (S03; DOCX §3)
- method_matrix-abgeleitete sample_type→Geometrie conditional-Kandidaten.

### AP5 — Tests (`tests/test_rules.py`)
- `test_rules_load_and_parameter_version_matches` — Versions-Gate grün bei
  korrekter Liste; **und** ein Negativtest, der eine manipulierte
  `expected_parameter_names` → `RuleConfigError` erzwingt. (Steering-Nachweis!)
- `test_missing_required_parameter_yields_unknown_not_approval`.
- `test_rules_never_output_approved` (outcome ∈ {excluded,conditional,unknown}).
- `test_every_rule_has_id_conditions_outcome_source` (Abnahmekriterium 1).
- `test_qualitative_ratings_not_emitted_as_numbers` (Abnahmekriterium 3).
- `test_nominal_vs_fiber_range_separation` (Abnahmekriterium 4).
- `test_no_scenario_ids_in_rules` — keine `H0x`/`D0x`/Szenario-Strings in
  Regeln (liest Regeldateien, Abnahmekriterium 5).
- `test_evaluate_matches_ruleevaluator_protocol` — Signatur/Typ.
- Lib-/pydantic-abhängige Pfade via `importorskip`; Pure-Logik (Prädikate,
  Versions-Set-Vergleich, YAML-Parsing) ohne Libs testbar.

### AP6 — Doku & Schnittstellen-Hinweis
- `data/rules/README.md` fertig (Semantik + Versionierung).
- **PR-Hinweis an Jakob (T06):** expliziten `PARAMETER_VERSION`-Marker neben
  `ParameterName` in `models.py` erwägen (analog `extraction_version`), damit
  T03 künftig gegen eine *Versionsnummer* statt nur Set-Gleichheit prüfen kann.
  T03 ändert `models.py` nicht selbst.
- `docs/tickets/T03_*.md` sind Teil des PR.

## Offene Entscheidungen (im Plan vorab entschieden)

- **P1 Fehlerklasse:** `RuleConfigError` **lokal** in `rules.py` als Subklasse
  von `AFSError` (import aus `src.errors`) — erweitert `errors.py` **nicht**
  (nur Import). Falls Jakob eine zentrale Klasse will → späterer Angleich.
- **P2 Regel-Reingabe:** Engine nimmt `ExtractionResult` (Vertrag), liest robust
  gegen den main-Stand; additive T06-Felder optional. Kein Zwang auf T06-Merge.
- **P3 Keine Zahlenlogik:** Bedingungen sind reine Keyword-/Presence-Prädikate
  auf Zitattext; `numeric_value` wird höchstens als zusätzlicher Beleg gelesen,
  nie zur Schwellenentscheidung (T06-Regel „keine stille Numerik").

## Definition of Done

- `data/rules/*` vorhanden, jede Regel mit ID/Bedingung/outcome/source_refs.
- Versions-Gate funktioniert (Positiv + Negativtest).
- `evaluate_rules` erfüllt `RuleEvaluator`-Protokoll; nur
  excluded/conditional/unknown; fehlende Parameter → unknown.
- `pytest tests/test_rules.py` grün (Pure-Logik in Sandbox; voller Lauf lokal
  bei Kevin via `uv run --locked pytest -q`).
- Keine Szenario-ID-Verzweigung; qualitative Ratings nie als Zahl.
- `src/models.py` unverändert; Schnittstelle zu T07/T08 dokumentiert.
