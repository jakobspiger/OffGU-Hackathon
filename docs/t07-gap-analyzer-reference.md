# T07 B3 Lücken-Analysator — technische Referenz & Fehlerdiagnose

Diese Doku beschreibt die Implementierung von T07 so ausführlich, dass sich ein
Fehlverhalten rückwärts bis zur verursachenden Stelle nachvollziehen lässt.
Bezug: `src/engine/gaps.py`, Vertragstypen in `src/models.py`
(`ClarificationQuestion`, `ExtractionResult`, `RuleFinding`). Ergänzt
[contracts.md](contracts.md) und baut auf
[t06-extraction-reference.md](t06-extraction-reference.md) (Eingabeseite) sowie
Kevins Regel-Engine T03 (`src/knowledge/rules.py`, Ausgabeseite) auf.

---

## 1. Zweck und Grenzen

B3 bestimmt aus der **Extraktion** (T06) und den **Regel-Findings** (T03), welche
Informationslücken eine Entscheidung behindern, und formuliert daraus
**priorisierte Rückfragen**. B3 ist bewusst **deterministisch**:

- **kein** LLM-Call, **kein** Retrieval, **keine** Methodenwahl, **keine**
  Fachbewertung;
- es werden **nur Fragen** erzeugt — niemals Zahlen, Sensorspezifikationen oder
  Quellen (T07-Abnahmekriterium 4).

Damit ist jedes Ergebnis von B3 bei gleicher Eingabe **exakt reproduzierbar** —
das ist die Grundlage für die Fehlerdiagnose in Abschnitt 6.

Öffentliche Einstiegspunkte:

| Aufruf | Datei | Rückgabe / Zweck |
|---|---|---|
| `analyze_gaps(extraction, rules)` | `gaps.py` | `list[ClarificationQuestion]` |
| `gaps_node(state)` | `gaps.py` | T11-Graph-Adapter: setzt nur `state["questions"]` |

---

## 2. Schnittstelle (gegen die realen Verträge gebaut)

### Eingänge
- `extraction: ExtractionResult` (T06). Genutzt werden:
  - `unknowns: list[str]` — fehlende **oder** strittige Parameter (`ParameterName`-Werte);
  - `conflicts: list[ParameterConflict]` — widersprüchliche Angaben zum selben Parameter.
  - `stated_facts` wird **nicht** direkt gelesen; die Lücken stecken bereits in
    `unknowns`/`conflicts`, die T06 deterministisch befüllt (siehe
    t06-extraction-reference.md, Schritte 8/9).
- `rules: list[RuleFinding]` (T03, aus `evaluate_rules(extraction)`). Genutzt werden:
  - `outcome ∈ {excluded, conditional, unknown}` — nur `unknown` erzeugt eine Lücke;
  - `rule_id`, `reason` — fließen in die Begründung ein.

### Ausgang
`list[ClarificationQuestion]` mit je `question`, `why_it_matters`,
`priority` (≥ 1, 1 = höchste) und `blocking`. Aufsteigend nach `priority`
sortiert (wie in contracts.md für B3 festgelegt).

### Warum `getattr(..., default)` statt direktem Attributzugriff
`analyze_gaps` liest `extraction.unknowns`/`extraction.conflicts` defensiv über
`getattr(…, [])`. Grund: Der T06-Vertrag ist mit `extraction_version="1.1"`
gewachsen; der defensive Zugriff hält B3 auch gegen einen älteren
Extraktionsstand lauffähig (leere Liste als robuster Default), statt mit
`AttributeError` zu brechen.

---

## 3. Datenfluss von `analyze_gaps()` (Schritt für Schritt)

```
extraction, rules
  │  unknowns   = extraction.unknowns            (fehlend ODER strittig)
  │  conflicted = {c.parameter for c in extraction.conflicts}
  ▼
(1)+(2) für jedes RuleFinding mit outcome=="unknown":
        → blockierende Frage, priority 1, nennt rule_id + reason
  ▼
(3) für jeden conflicted-Parameter (sortiert), noch nicht abgedeckt:
        → blockierende Frage, priority 2  ; parameter zu `covered`
  ▼
(4) für jeden unknowns-Parameter, nicht in covered UND nicht conflicted:
        → nicht-blockierende Frage, priority 3 ; parameter zu `covered`
  ▼
(5) return sorted(questions, key=priority)   # aufsteigend, Ties stabil
```

### (1)+(2) Regelgetriebene blockierende Lücken
Ein `RuleFinding(outcome="unknown")` bedeutet laut T03: Die Regel konnte **nicht
greifen**, weil ein Pflichtparameter (`requires`) fehlt oder strittig ist (siehe
`evaluate_rules` → „Requires gate first"). Das ist die **wichtigste** Lücke, denn
hier blockiert eine konkrete Regel eine Entscheidung → `blocking=True`,
`priority=PRIORITY_RULE_BLOCKING (1)`.
- `question`: generisch gehalten (nennt die `rule_id`), weil T03 die konkret
  fehlenden Parameter bereits im `reason`-Text führt.
- `why_it_matters`: `"Rule {rule_id} cannot reach a decision yet: {reason}"` —
  übernimmt Kevins `reason` wörtlich, erfindet nichts dazu.
- `excluded`/`conditional`-Findings erzeugen **keine** Frage (sie sind
  Entscheidungen, keine Lücken).

### (3) Ungelöste Widersprüche (T06-`conflicts`)
Pro strittigem Parameter genau **eine** blockierende Frage, `priority=2`. Die
Iteration läuft über `sorted(conflicted)` → **deterministische Reihenfolge**
unabhängig von der Dict-/Set-Einfügereihenfolge. Der Parameter wird in `covered`
vermerkt, damit er in Schritt 4 nicht erneut als simple Missing-Frage auftaucht.

### (4) Verbleibende unbekannte Parameter
Parameter, die in `unknowns` stehen, aber von keiner Regel blockiert und nicht
strittig sind: eine **nicht-blockierende** Frage, `priority=3`. Die
Guard-Bedingung `parameter in covered or parameter in conflicted` verhindert
Dubletten. Formulierung bleibt eine Rückfrage (`"Could you specify …?"`) — **kein
Zahlen-/Spezifikationswert** (Kriterium 4).

### (5) Sortierung
`sorted(..., key=lambda q: q.priority)` ist **stabil**: gleiche Prioritäten
behalten die Einfügereihenfolge (erst Regel-, dann Konflikt-, dann
Missing-Fragen). Entspricht contracts.md: „B3 sortiert aufsteigend; gleiche
Prioritäten sind erlaubt."

---

## 4. Prioritätsbänder und `_PARAMETER_LABELS`

| Konstante | Wert | Bedeutung |
|---|---|---|
| `PRIORITY_RULE_BLOCKING` | 1 | Eine Regel kann ohne diesen Parameter nicht entscheiden. |
| `PRIORITY_CONFLICT` | 2 | Widersprüchliche Angaben müssen aufgelöst werden. |
| `PRIORITY_MISSING_PARAMETER` | 3 | Parameter fehlt, aber keine Regel braucht ihn aktuell. |

`_PARAMETER_LABELS` ordnet jedem der 16 `ParameterName`-Werte eine lesbare
Beschreibung zu (nur für die Fragetexte). `_label()` fällt bei einem
unbekannten Schlüssel auf den Rohnamen zurück — bewusst **ohne** Einheiten/Werte,
damit B3 nichts behauptet. Ändert sich das `ParameterName`-Set
(`PARAMETER_VERSION` in `models.py`), sollte dieses Dict mitgezogen werden; ein
fehlender Eintrag ist aber kein Fehler (Fallback greift).

---

## 5. T11-Adapter `gaps_node`

Analog zu `engine.extraction.extraction_node`:
```python
def gaps_node(state: dict) -> dict:
    return {"questions": analyze_gaps(state["extraction"], state.get("rules", []))}
```
- liest `state["extraction"]` (muss vorhanden sein) und `state.get("rules", [])`
  (fehlende Regeln → leere Liste, dann entstehen nur Konflikt-/Missing-Fragen);
- schreibt **ausschließlich** `questions` zurück — keine konkurrierenden
  Schreibzugriffe auf andere State-Felder (v1-Regel aus contracts.md,
  „Graph-State und Schreibrechte": `questions` wird von B3 geschrieben).

---

## 6. Fehlerdiagnose (Symptom → Ursache → Stelle)

Weil B3 deterministisch ist, lässt sich jedes Ergebnis exakt aus Eingabe +
Code herleiten.

| Symptom | Wahrscheinliche Ursache | Wo nachsehen |
|---|---|---|
| `KeyError: 'extraction'` in `gaps_node` | State ohne `extraction` übergeben | `gaps_node` (5); T11-Verdrahtung |
| gar keine Fragen trotz fehlender Angaben | `unknowns`/`conflicts` der Extraktion sind leer | zuerst T06 prüfen (t06-ref. 8/9), nicht gaps.py |
| erwartete blockierende Frage fehlt | kein `RuleFinding(outcome="unknown")` vorhanden | T03 `evaluate_rules` (Requires-Gate); `rules`-Liste leer? |
| `excluded`/`conditional` erzeugt fälschlich Frage | sollte by design nicht passieren | Filter in (1): `if finding.outcome != "unknown": continue` |
| Konflikt-Parameter taucht **doppelt** auf (p2 **und** p3) | `covered`/`conflicted`-Guard umgangen | Dedup in (3)/(4) |
| Reihenfolge der Fragen schwankt zwischen Läufen | nicht-deterministische Eingabe-Reihenfolge | (3) nutzt `sorted(conflicted)`; (5) sortiert nach priority |
| Frage enthält eine Zahl | dürfte nicht sein (Kriterium 4) | Fragetexte in (1)/(3)/(4); ggf. kam Zahl aus `finding.reason` |
| `ValidationError` beim Bau von `ClarificationQuestion` | leeres `question`/`why_it_matters` (Text min_length 1) oder `priority < 1` | Modell `ClarificationQuestion` in `models.py` |
| Parameter ohne lesbares Label | Schlüssel fehlt in `_PARAMETER_LABELS` | `_label()`-Fallback (4); Dict ergänzen |

**Grundregel beim Reverse-Engineering:** B3 fügt **nichts** hinzu, was nicht in
`unknowns`, `conflicts` oder einem `unknown`-RuleFinding steckt. Fehlt eine
erwartete Frage, liegt die Ursache fast immer **upstream** (T06-Extraktion oder
T03-Regeln), nicht in `gaps.py`. Erst prüfen, was `analyze_gaps` als Eingabe
bekommt; dann die drei Erzeugungsblöcke (1)/(3)/(4) durchgehen.

---

## 7. Testabdeckung (`tests/test_gaps.py`)

Synthetische Eingaben, keine AFS-Fachaussagen. Deckt alle fünf Abnahmekriterien ab:

| Test | prüft |
|---|---|
| `test_no_gaps_yields_no_questions` | vollständige Angabe → keine Frage |
| `test_unknown_rule_finding_is_blocking_and_top_priority` | (1): blockierend, priority 1, `rule_id` in Begründung |
| `test_excluded_and_conditional_findings_do_not_create_gaps` | Filter: nur `unknown` erzeugt Lücken |
| `test_conflict_produces_blocking_question` | (3): genau eine blockierende p2-Frage, keine p3-Dublette |
| `test_plain_unknown_is_non_blocking_and_lower_priority` | (4): nicht-blockierend, priority 3 |
| `test_questions_are_sorted_by_priority_ascending` | (5): aufsteigende Sortierung |
| `test_unknown_target_substance_never_produces_numbers` | Kriterium 4: keine Ziffern in den Fragetexten |
| `test_gaps_node_updates_only_questions` | Adapter schreibt genau `questions` |

> Ausführungsstand: Die Verzweigungslogik (blocking/priority/dedup/sort) wurde
> offline mit leichtgewichtigen Stand-in-Objekten gegen den echten Code
> verifiziert. `tests/test_gaps.py` importiert `src.models` (pydantic) und läuft
> zusammen mit der vollen Suite erst in einer Umgebung mit Netzzugriff:
> `uv sync --locked && uv run --locked pytest -q`. Siehe PR #7.

---

## 8. Zusammenspiel mit anderen Tickets

- **T06 (Eingabe):** liefert `ExtractionResult` mit `unknowns`/`conflicts`.
  Qualität der Lücken hängt direkt an T06s deterministischer Befüllung.
- **T03 (Eingabe):** `evaluate_rules` liefert die `RuleFinding`s; nur `unknown`
  wird zur blockierenden Lücke. Offener Abstimmungspunkt mit Kevin: Formulierung
  bei strittigen vs. fehlenden Parametern.
- **T08 (Synthese) / UI (Ausgabe):** konsumieren die sortierte Fragenliste über
  das State-Feld `questions`.
- **`PARAMETER_VERSION`** (neu in `models.py`, T07): erlaubt Kevins T03-Gate, die
  Parameter-Kompatibilität gegen eine Versionsnummer statt Set-Gleichheit zu
  prüfen (siehe contracts.md).
