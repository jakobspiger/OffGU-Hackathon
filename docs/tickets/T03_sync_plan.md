# T03 · Sync-Fix-Plan (gegen aktuellen `main`)

> Basiert auf `T03_sync_analysis.md`. Behebt F1–F3, ergänzt Integrationstests
> (F4/F5). Scope: **nur** Kevins Dateien (`src/knowledge/rules.py`,
> `data/rules/*`, `tests/test_rules.py`). `src/models.py` bleibt Jakobs.

## Fixes

### AP1 — `PARAMETER_VERSION`-Gate verdrahten (F1, Kern)
- `data/rules/rules_meta.yaml`: Feld `expected_parameter_version: "1.0"` ergänzen.
- `rules.py`:
  - `RulesMeta` um `expected_parameter_version: str` erweitern (Dataclass +
    `parse_meta`).
  - Neuer Schritt im Gate: `PARAMETER_VERSION` aus `src.models` lesen
    (lazy import, wie bei `ParameterName`); prüfen
    `meta.expected_parameter_version == PARAMETER_VERSION`, sonst
    `RuleConfigError` mit beiden Werten.
  - **Beide** Prüfungen behalten: zuerst Versionsnummer (billig, der vereinbarte
    Mechanismus), dann Set-Gleichheit (inhaltliche Absicherung gegen stillen
    Drift ohne Versionsbump). Klarer Fehlertext je Fall.

### AP2 — Veraltete Skip-Begründungen bereinigen (F2/F3)
- `tests/test_rules.py`: Skip-Reason von „T06 not merged" auf reine
  Umgebungsabhängigkeit umstellen (`pydantic is provided by uv sync`).
  `ParameterName`-`ImportError`-Guard als rein defensiv kommentieren (Normalfall:
  vorhanden).
- `rules.py` Docstring/Kommentar in `_expected_parameter_names`: Hinweis „T06
  nicht gemergt" entfernen; jetzt ist der Marker Teil von `main`.

### AP3 — Versions-Tests (F1)
- `tests/test_rules.py`:
  - Positiv: `rules_meta.expected_parameter_version` == Modul-`PARAMETER_VERSION`
    (pure-logic via AST-Read von models.py, damit ohne pydantic lauffähig — wie
    es `test_pure_logic_offline.py` von T06 vormacht).
  - Negativ: manipulierte `expected_parameter_version` → `RuleConfigError`.
  - Negativ bleibt: manipulierte `expected_parameter_names`-Menge → Fehler.

### AP4 — Integrationstest T03 → T07 (F4) und conflicts→unknown (F5)
- Neuer Test (pydantic-guarded): `evaluate_rules(extraction)` →
  `analyze_gaps(extraction, findings)` ergibt für einen fehlenden
  Pflichtparameter eine **blockierende** Rückfrage (T07 verlangt
  `outcome=="unknown"`).
- Neuer Test (pydantic-guarded): `ExtractionResult` mit echtem
  `ParameterConflict` → betroffener Parameter führt zu `unknown`-Finding (nie
  conditional/Freigabe). Nutzt den **echten v1.1-Vertrag**.

### AP5 — Doku nachziehen
- `data/rules/README.md`: Versions-Gate-Abschnitt auf
  `PARAMETER_VERSION`-Vergleich + Set-Gleichheit aktualisieren; T06-„Empfehlung"
  → „umgesetzt (PARAMETER_VERSION auf main)".
- `docs/tickets/T03_plan.md` Querverweis auf Sync nicht nötig (separate Datei).

## Abnahme & Merge-Kriterium (Kevins Vorgabe)

- **Sandbox:** `python -m pytest tests/test_rules.py -q` → pure-logic grün,
  pydantic-Pfade skippen sauber.
- **Lokal bei Kevin (maßgeblich für Merge):**
  `uv sync --locked && uv run --locked pytest -q` → ALLE T03-Tests inkl. der
  jetzt aktivierten pydantic/Integrationstests müssen grün sein. Zusätzlich
  `ruff check . && ruff format --check .`.
- **Kein LLM/API-Key für T03 nötig.** (Nur falls du zusätzlich T06 live gegen
  euer LLM prüfen willst → `uv run --locked python -m scripts.smoke_llm`.)
- **Merge:** Wenn die Tests grün sind, PR #5 nach `main` mergen (merge commit),
  Branch danach optional aufräumen.

## Scope-Grenzen

- `src/models.py`, `src/engine/*`, `src/knowledge/{catalog,ingest,types,retrieval}.py`
  unverändert. Kein Retrieval/Few-Shot/UI. Keine Szenario-ID-Logik.
