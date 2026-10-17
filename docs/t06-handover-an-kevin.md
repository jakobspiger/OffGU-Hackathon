# T06 → Kevin: Vertragsänderungen für T03 (Regel-Matrix)

> Von: Jakob (T06, Eigentümer von `src/models.py`) · An: Kevin (T03 Regel-Engine,
> T04/T05/T10)
> Branch: `feat/t06-parameter-extractor`. Status: Extraktor implementiert
> (`src/engine/extraction.py`, `src/engine/provider.py`), Vertrag auf
> `extraction_version = "1.1"` erweitert — rückwärtskompatibel, alle neuen Felder
> haben Defaults.

Diese Übergabe ergänzt [parameters.md](parameters.md) und [contracts.md](contracts.md).
Die 16 `ParameterName`-Werte und ihre Semantik sind unverändert. Kevin braucht
keine eigene Namensliste; es gelten weiterhin die gemeinsamen Schlüssel.

## Warum das T03 betrifft

Der Regeladapter `RuleEvaluator(extraction: ExtractionResult) -> list[RuleFinding]`
(siehe [contracts.md](contracts.md)) bekommt sein Eingabeobjekt direkt von B2.
Mit dem Extraktionsschritt wächst `ExtractionResult`. Nichts an bestehenden
Feldern wurde entfernt oder umbenannt; es kommen Felder hinzu, die die Regeln
berücksichtigen sollten.

## Was neu ist (Zusammenfassung)

| Neu in `src/models.py` | Bedeutung für T03 |
|---|---|
| `ExtractedFact.numeric_value: NumericValue \| None` | Optionaler exakt geparster Skalar mit Einheit. `None` ist der Normalfall. |
| `ExtractionResult.conflicts: list[ParameterConflict]` | Explizit markierte Widersprüche zum selben Parameter. |
| `ExtractionResult.extraction_version = "1.1"` | Versionskennzeichen der Extraktionsstruktur. |
| `unknowns` enthält `ParameterName`-Werte | Fehlende **und** konflikt-behaftete Parameter stehen hier. |
| `verify_quotes` normalisiert Darstellung (V-2, Issue #3) | Betrifft T06 intern; kein Verhalten für T03 zu ändern. |

## Regel-relevante Festlegungen

1. **`numeric_value` ist optional und konservativ.**
   `NumericValue` hat `magnitude: float` und `unit` aus genau
   `{"°C", "K", "bar(a)", "bar(g)", "s", "ms"}`. Gefüllt wird nur bei einem
   einzelnen Dezimalwert mit Punkt und unterstützter Einheit (z. B. `80 °C`,
   `2.5 bar(a)`, `100 ms`). **`None` bei**: Bereichen (`20–80 °C`), Näherungen
   (`ca. 80 °C`), Verneinungen (`nicht 80 °C`), Komma-Dezimalen (`1,000 °C`),
   fehlender Einheit (`80`), nicht unterstützten Einheiten (`2 bar`, `2 %`,
   `20 ppm`) und physikalisch unmöglichen Werten (`-1 K`, `-300 °C`).
   → Regeln dürfen `numeric_value` nur dort numerisch vergleichen, wo es gesetzt
   ist. Bei `None` bleibt `value` (Text) maßgeblich; keine eigene Zahlenextraktion
   im Regelmodul, keine stillen Umrechnungen. Fehlender Skalar ist **keine**
   Freigabe.

2. **`conflicts` müssen eine Freigabe verhindern.**
   `ParameterConflict` hat `parameter: ParameterName`, `fact_indices`
   (0-basiert, ≥ 2, verschieden, Index in `stated_facts`, gleicher Parameter) und
   `reason: str`. Ein Konflikt bedeutet: mehrere unterschiedliche Werte oder ein
   vom Modell markierter ausdrücklicher Widerspruch zum selben Parameter.
   → Für einen in `conflicts` gelisteten Parameter darf T03 **nicht** `conditional`
   oder gar freigebend entscheiden; `unknown` ist das passende Ergebnis, bis die
   Mehrdeutigkeit (B3/T07) geklärt ist. Das deckt sich mit T03-Kriterium
   „fehlende/unklare Angaben erzeugen keine Freigabe".

3. **`unknowns` kann einen Parameter trotz vorhandener Fakten enthalten.**
   `unknowns` listet jeden vollständig fehlenden Parameter mit seinem exakten
   `ParameterName`. Zusätzlich steht ein konflikt-behafteter Parameter in
   `unknowns`, obwohl er in `stated_facts` auftaucht — weil seine Bedeutung bis
   zur Klärung offen ist.
   → Regeln sollten „Parameter in `unknowns`" als „nicht belastbar" behandeln und
   nicht aus den vorhandenen (widersprüchlichen) Fakten eine Freigabe ableiten.

4. **Mehrfache Fakten pro Parameter bleiben erhalten.**
   Unterschiedliche Prozesszustände (z. B. „Vorher 20 °C", „nachher 80 °C")
   erscheinen als getrennte `ExtractedFact` und zusätzlich als `conflict`. Regeln
   dürfen diese nicht zu einem Einzelwert verrechnen.

5. **`assumptions` ist derzeit leer.**
   T06 unterlässt unbelegte Ergänzungen und bevorzugt `unknowns`. Regeln sollten
   sich nicht auf `assumptions`-Inhalte verlassen.

## Was sich NICHT ändert

- `ParameterName` (16 Werte) und `ExtractedFact.parameter`/`value`/`input_quote`.
- `RuleFinding` und das Callable-Protocol `RuleEvaluator`.
- Die Datei-Grenzen: `src/models.py` bleibt bei Jakob; T03 lebt in
  `src/knowledge/rules.py` / `data/rules/`.

## Bezug

- V-2 / `verify_quotes`-Normalisierung: Issue #3, umgesetzt in diesem Branch
  (`src/models.py`, `src/engine/extraction.py`, `tests/test_verify_quotes.py`).
- Schnittstellenänderungen bitte wie vereinbart gemeinsam dokumentieren; alle
  Vertragsänderungen laufen weiterhin über Jakob.
