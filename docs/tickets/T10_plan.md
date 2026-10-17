# T10 — B7 Zitations- und Physik-Gate · Umsetzungsplan

> Basiert auf `T10_analysis.md`. Ziel: deterministischer, **zustandsloser**
> `validate_result(result, evidence, rules) -> ValidationReport` (Contract
> `ResultValidator`) + CLI `scripts/check_citations.py`.
> **Keine** Änderung an `src/models.py`, `src/engine/graph.py` o. a. Jakob-
> Modulen. Validator ändert **nie** `decision_status` (das macht `gate_node`).

## Zerlegung in Arbeitspakete (AP0–AP6)

### AP0 — Modulgerüst (`src/engine/validators.py`)
- Lazy-Imports der Contract-Typen (`AnalysisResult, Evidence, RuleFinding,
  ValidationReport, ValidationFinding`) — pydantic nur dort nötig.
- Severity-Konstanten + Finding-Code-Katalog (stabile `code`-Strings, z. B.
  `CITATION_SOURCE_UNKNOWN`, `CITATION_PAGE_OUT_OF_RANGE`,
  `EVIDENCE_ID_MISSING`, `EVIDENCE_SCOPE_BUSINESS_CONTEXT`,
  `EVIDENCE_SCOPE_RESEARCH`, `SEMANTIC_SUPPORT_NOT_CHECKED`,
  `SPECTRAL_VERIFIED_WITHOUT_EVIDENCE`, `SPECTRAL_RANGE_IMPLAUSIBLE`,
  `RULE_EXCLUDED_CONTRADICTION`, `RULE_UNKNOWN_UNRESOLVED`).
- Eigene Hilfsfunktion zum Finding-Bauen; keine Fremd-Dateien anfassen.

### AP1 — Zitations-Gate (`_check_citations`)
- Für jede `recommendation` und `overall_sources`:
  - `source_id ∈ {S01..S06}` prüfen (sonst `CITATION_SOURCE_UNKNOWN` = **error**).
  - Seite gegen Katalog-Seitenspanne prüfen (S06 ohne Seite; sonst 1-basiert in
    Spanne). Außerhalb/erfunden → `CITATION_PAGE_OUT_OF_RANGE` = **error**.
  - `recommendation.evidence_ids` müssen in der `evidence`-Liste existieren
    (per `evidence_id`); fehlend → `EVIDENCE_ID_MISSING` = **error**.
  - Scope: referenzierte Evidenz mit `purpose="business_context"` (S05/S06) als
    Beleg einer technischen Empfehlung → `EVIDENCE_SCOPE_BUSINESS_CONTEXT` =
    **error**. `purpose="research"` (S03/S04) → `EVIDENCE_SCOPE_RESEARCH` =
    **warning** (Forschungsscope nicht überdehnen).
  - Jede inhaltliche Claim↔Seite-Beziehung, die nicht automatisch prüfbar ist →
    genau **ein** `SEMANTIC_SUPPORT_NOT_CHECKED` = **not_checked** (dokumentierte
    Grenze; Abnahmekriterium 5). Kein „bestanden" vortäuschen.
- Katalog lazy über `src.knowledge.catalog`; Fallback auf statische S0x-
  Seitenspannen, damit Pure-Logik ohne pydantic testbar ist.

### AP2 — Physik-/Einheiten-Gate (`_check_physics`)
- Für jede `recommendation.spectral_range` (falls gesetzt):
  - `scope="verified_instrument"` ohne stützende Evidence/Beleg →
    `SPECTRAL_VERIFIED_WITHOUT_EVIDENCE` = **error** (unbelegte Hardwarefreigabe;
    nominal ≠ Gerät).
  - Spanne weit außerhalb bekannter nominaler Bereiche (NIR 780–2500 nm,
    MIR 4000–400 cm⁻¹) ohne Beleg → `SPECTRAL_RANGE_IMPLAUSIBLE` = **warning**.
- Einheiten-Grundkonsistenz ist bereits im Contract (nicht doppeln); nur
  belegbare Zusatzprüfungen.

### AP3 — Regel-Gate (`_check_rules`)
- `rules: list[RuleFinding]` auswerten:
  - `outcome="excluded"` zu einem Thema, das eine Empfehlung dennoch vertritt /
    das Ergebnis `provisional` ist → `RULE_EXCLUDED_CONTRADICTION` = **error**.
  - `outcome="unknown"` (blockierende Lücke), während `decision_status ==
    "provisional"` → `RULE_UNKNOWN_UNRESOLVED` = **warning** (Hinweis auf
    unbegründete Freigabe; die harte Konsequenz zieht `gate_node`).
  - **Generisch** über Outcomes/`rule_id` — keine Szenario-ID-Logik.

### AP4 — Öffentlicher Validator (`validate_result`)
- `validate_result(result, evidence, rules) -> ValidationReport`, erfüllt
  **exakt** `ResultValidator`.
- **Zustandslos / pure:** sammelt Findings aus AP1–AP3, baut **frische**
  `ValidationReport`. Kein Modul-Cache, kein Seiteneffekt (T11-Seam-Anforderung).
- Deterministische Reihenfolge (nach `field_path`, dann `code`).
- Setzt **kein** `decision_status` (bleibt Sache von `gate_node`).

### AP5 — CLI (`scripts/check_citations.py`)
- `python scripts/check_citations.py --result <result.json> [--index data/index]`.
- Lädt `AnalysisResult`-JSON + Evidence aus `evidence.jsonl` (reuse T04-Loader
  oder direkter JSONL-Read), ruft denselben Validator (Zitations-Teil), gibt
  Befunde aus; **Exit-Code ≠ 0 bei errors**. Für D-/H-Batch-QA & Repro.
- Keine Regel-Duplikation: ruft `validators`-Funktionen auf.

### AP6 — Tests (`tests/test_validators.py`)
Mit Fixture-`AnalysisResult`/`Evidence`/`RuleFinding` (pydantic-guarded für
Contract-Konstruktion; Pure-Logik-Checks mit Stubs):
- `test_fabricated_source_is_error` (unbekannte source_id / Seite außerhalb
  Katalog → error). **(Abnahmekriterium 6: erfundene Quellen)**
- `test_missing_evidence_id_is_error` (evidence_id nicht in evidence-Liste).
- `test_business_context_evidence_as_proof_is_error` (S05/S06 als technischer
  Beleg). **(unpassende Belege)**
- `test_research_scope_overreach_is_warning`.
- `test_verified_instrument_range_without_evidence_is_error`
  (**unbelegte Hardwarefreigabe**).
- `test_implausible_spectral_range_is_warning`.
- `test_excluded_rule_contradiction_is_error`.
- `test_unresolved_unknown_with_provisional_is_warning`.
- `test_unverifiable_claim_marked_not_checked` (Grenze der Prüfung;
  Abnahmekriterium 5).
- `test_valid_result_has_no_errors` (sauberes Ergebnis → `has_errors=False`).
- `test_validator_is_stateless_fresh_report` (zweimal aufrufen → unabhängige,
  frische Reports; T11-Seam).
- `test_validate_matches_resultvalidator_protocol` (Signatur/Typ).
- `test_validator_sets_no_decision_status` (Validator ändert result nicht).
- `test_no_scenario_ids_in_validator` (keine H0x/D0x im Code).
- Lib-abhängige Pfade via `importorskip`; Pure-Logik auf stdlib.

## Offene Entscheidungen für Kevin

1. **Scope-Verstöße (S05/S06 als Beleg) = error** (empfohlen) vs. warning?
   Empfehlung: **error** — „Unternehmenskontext ist kein Leistungsbeleg" ist ein
   hartes Abnahmekriterium.
2. **`unknown`-Regel bei `provisional` = warning** (empfohlen) vs. error?
   Empfehlung: **warning** im Validator; die harte Freigabe-Verhinderung macht
   ohnehin `gate_node` (vermeidet Doppelbestrafung).
3. **`SEMANTIC_SUPPORT_NOT_CHECKED`:** ein gesammeltes `not_checked`-Finding pro
   Recommendation (empfohlen, knapp) vs. eines pro Claim? Empfehlung: **pro
   Recommendation**, Message nennt die betroffenen Belege.

## Definition of Done

- `validate_result` erfüllt `ResultValidator`; zustandslos, frische Reports.
- Quellen/Seiten/Evidence-IDs gegen Katalog geprüft; Einheiten/Scope/Regeln
  geprüft; Befunde als error/warning/not_checked.
- `scripts/check_citations.py` läuft, Exit-Code bei errors.
- Tests grün (pure-logic Sandbox; voller Lauf lokal). `graph.py`/`models.py`
  unberührt. Grenzen der Prüfung dokumentiert. **Kein LLM/Key nötig.**
