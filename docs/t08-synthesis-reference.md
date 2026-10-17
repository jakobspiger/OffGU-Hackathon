# T08 B4/B5 Lösungssynthese — technische Referenz & Fehlerdiagnose

Diese Doku beschreibt die Implementierung von T08 so ausführlich, dass sich ein
Fehlverhalten rückwärts bis zur verursachenden Stelle nachvollziehen lässt.
Bezug: `src/engine/synthesis.py`, `src/engine/prompts.py`, Vertragstypen in
`src/models.py`. Ergänzt [contracts.md](contracts.md) und baut auf den Eingaben
von T06 ([t06-extraction-reference.md](t06-extraction-reference.md)), T07
([t07-gap-analyzer-reference.md](t07-gap-analyzer-reference.md)), T03
(`src/knowledge/rules.py`) und T04 (`src/knowledge/retrieval.py`) auf.

---

## 1. Zweck und Leitidee

B4/B5 leitet aus Extraktion, Regel-Findings, offenen Rückfragen und abgerufener
Evidenz **bedingte Methodenkandidaten** und ein **Messkonzept** ab und liefert
einen `AnalysisResult`-Entwurf (der von T10 später noch validiert wird).

Die zentrale Design-Entscheidung: **Das LLM entwirft nur den Freitext und die
Kandidaten-Begründung; die harten Garantien erzwingt der Code deterministisch
rund um das Modell.** Dadurch kann eine überzeugend klingende, aber unbelegte
Modellantwort **keine** erzwungene Auswahl durchsetzen. Diese Trennung ist der
Schlüssel zu den Abnahmekriterien 2 und 4.

Öffentliche Einstiegspunkte:

| Aufruf | Datei | Zweck |
|---|---|---|
| `synthesize(extraction, rules, questions, evidence, *, query, provider, settings)` | `synthesis.py` | Entwurf + Guardrails → `AnalysisResult` |
| `synthesis_node(state)` | `synthesis.py` | T11-Adapter: setzt nur `state["draft"]` |
| `SYNTHESIS_SYSTEM_PROMPT`, `SYNTHESIS_USER_TEMPLATE` | `prompts.py` | Prompt-Bausteine |

---

## 2. Schnittstelle (gegen die realen Verträge)

### Eingänge
- `extraction: ExtractionResult` (T06) — `stated_facts`, `assumptions`, `unknowns`.
- `rules: list[RuleFinding]` (T03, `evaluate_rules`) — `outcome` + `rule_id` + `reason`.
- `questions: list[ClarificationQuestion]` (T07) — `blocking` steuert die Enthaltung.
- `evidence: list[Evidence]` (T04 `retrieve`) — `evidence_id` ist die Grounding-Referenz.
- `query: str` (optional) — nur für den Prompt-Kontext; längenbegrenzt auf
  `MAX_QUERY_LENGTH` (aus `engine.extraction`).

### Ausgang
`AnalysisResult` (Entwurf). Felder siehe `models.py`; relevant: `decision_status`,
`recommendations`, `overall_sources`, `measurement_concept`, `risks_and_limits`,
`go_no_go_criteria`, plus die aus den Eingaben befüllten `stated_facts`,
`assumptions`, `unknowns`, `clarification_questions`.

### Was das Modell darf: `SynthesisDraft`
Das Modell liefert nur `decision_status`, `recommendations`,
`measurement_concept`, `risks_and_limits`, `go_no_go_criteria`
(`extra="forbid"`, Längenlimits). Die deterministischen Felder
(`stated_facts`/`assumptions`/`unknowns`/`clarification_questions`) ergänzt
`_assemble` aus den Eingaben — nie das Modell.

---

## 3. Datenfluss von `synthesize()` (Schritt für Schritt)

```
extraction, rules, questions, evidence, query
  │  (1) query-Längen-Guard
  ▼
Settings/Provider; system = SYNTHESIS_SYSTEM_PROMPT + JSON-Schema(SynthesisDraft)
user  = SYNTHESIS_USER_TEMPLATE.format(facts/questions/rules/evidence)   (2)
  ▼
Schleife attempt = 0 .. afs_max_retries:
    raw   = provider.complete(system, user)                              (3)
    draft = SynthesisDraft.model_validate_json(raw)                      (4)
    return _assemble(draft, extraction, questions, evidence, rules)      (5)
      │ ProviderError.retryable=False → raise sofort
      │ ProviderError.retryable=True  → nächste Runde
      │ ValueError (Schema)           → Prompt verschärfen, nächste Runde
      ▼
  (nach letzter Runde) raise SynthesisError
```

### (1) Guard
`len(query) > MAX_QUERY_LENGTH` → `ValueError` (vor jedem Call). Analog
`extraction.extract`.

### (2) Prompt-Aufbau
`_facts_block`, `_questions_block`, `_rules_block`, `_evidence_block` rendern die
Eingaben als lesbare Listen. Evidenz wird mit `[evidence_id]` prefixt, damit das
Modell **genau diese IDs** zitieren kann (und keine erfindet).

### (3) Provider-Call
Reuse von `ChatJSONProvider` (OpenAI-kompatibel, JSON-Mode-Fallback, Fehler-
Sanitisierung) — Details in t06-extraction-reference.md Abschnitt 3.

### (4) Draft-Validierung
`SynthesisDraft.model_validate_json(raw)`. Zusatzfelder/Typfehler → `ValueError`
→ Retry mit verschärftem Prompt.

### (5) Guardrails — `_assemble()` (der eigentliche Schutz)
In dieser Reihenfolge:

1. **Evidenz-Grounding + Regel-Ausschluss.** Behalte eine Empfehlung nur, wenn
   - ihre `method` **nicht** in einer `excluded`-Regel steht, **und**
   - `set(rec.evidence_ids) <= available_evidence_ids` (alle zitierten IDs sind
     in der tatsächlich übergebenen Evidenz vorhanden).
   `Recommendation` verlangt vertraglich bereits ≥ 1 `evidence_id` und ≥ 1
   `source_ref` — eine Empfehlung ohne Beleg ist also gar nicht konstruierbar.
2. **Enthaltung.** Wenn `not evidence` **oder** keine Empfehlung übrig **oder**
   eine offene **blockierende** Frage existiert → `decision_status` wird auf
   `insufficient_information` gezwungen (außer er ist `out_of_scope`, dann bleibt
   er), und `recommendations` wird geleert.
3. **`overall_sources` ableiten.** Aus den `source_refs` der verbliebenen
   Empfehlungen (dedupliziert). Das erfüllt den Validator
   `AnalysisResult.check_recommendation_sources` (jede Empfehlungsquelle muss in
   `overall_sources` erscheinen).
4. **Deterministische Felder** aus den Eingaben: `stated_facts` als
   `"{parameter}: {value}"`, `assumptions`/`unknowns`/`clarification_questions`
   direkt übernommen. `feasibility_plan` bleibt in v1 leer.

---

## 4. Retry- und Fehlerverhalten

- Höchstens `1 + afs_max_retries` Provider-Calls (Default 2).
- `ProviderError.retryable=False` (z. B. HTTP 401) → sofort `raise`.
- `ProviderError.retryable=True` und `ValueError` teilen sich das Budget.
- Nach Schemafehler wird der Prompt um einen Korrektur-Hinweis ergänzt
  (kein Response-Body/Key im Prompt oder Log).
- Alle Runden erschöpft → `SynthesisError` (Subklasse von `AnalysisError`).
  Ein API-/Parsingfehler wird **nie** zu einem fachlichen Ergebnis.

---

## 5. T11-Adapter `synthesis_node`

```python
def synthesis_node(state: dict) -> dict:
    return {"draft": synthesize(state["extraction"], state.get("rules", []),
                                state.get("questions", []), state.get("evidence", []),
                                query=state.get("query", ""))}
```
Schreibt **ausschließlich** `draft`. `extraction` muss im State vorhanden sein;
fehlende `rules`/`questions`/`evidence` werden zu leeren Listen (dann greift die
Enthaltung in Schritt 5.2).

---

## 6. Fehlerdiagnose (Symptom → Ursache → Stelle)

| Symptom | Wahrscheinliche Ursache | Wo nachsehen |
|---|---|---|
| Ergebnis immer `insufficient_information`, keine Empfehlungen | keine Evidenz übergeben (T04 noch Stub!) | `retrieve()`-Stand; `_assemble` (5.2) |
| Empfehlung des Modells fehlt im Ergebnis | zitiert `evidence_id`, die nicht in `evidence` ist | Grounding-Filter (5.1) |
| Empfehlung fehlt trotz gültiger Evidenz | `method` steht in einer `excluded`-Regel | `_excluded_methods`; (5.1) |
| `provisional` erwartet, aber Enthaltung | offene **blockierende** Frage aus T07 | `_has_blocking_question`; (5.2) |
| `ValueError: Recommendation sources must also appear in overall_sources` | sollte durch (5.3) nicht passieren; manuell gebauter Result? | `check_recommendation_sources` in `models.py` |
| `ValidationError` beim Bau des `AnalysisResult` | Modell-Draft verletzt ein Teilmodell (z. B. SpectralRange-Einheit) | `SynthesisDraft`/`Recommendation`/`SpectralRange` |
| `SynthesisError` nach Lauf | Modell liefert dauerhaft ungültiges JSON | Prompt (2); `afs_max_retries`; Modellwahl |
| `ProviderError` (HTTP 401, nicht retrybar) | Key/Endpoint falsch | `provider.py`; `.env` |
| `stated_facts`/`unknowns` wirken „erfunden" | kommen aus der Extraktion, nicht aus T08 | zuerst T06 prüfen (t06-ref.) |

**Grundregel:** T08 fügt **nichts** hinzu, was nicht durch Evidenz, Regeln und
Eingaben gedeckt ist. Fehlt eine erwartete Empfehlung, ist die Ursache fast
immer eine **nicht erfüllte Guardrail** (fehlende/falsch zitierte Evidenz,
Ausschlussregel, blockierende Frage) — nicht das Modell. Zuerst klären, welche
der drei Bedingungen in (5.2) gegriffen hat.

---

## 7. Testabdeckung (`tests/test_synthesis.py`)

Synthetische Eingaben, `FakeProvider` statt echtem LLM.

| Test | prüft |
|---|---|
| `test_grounded_recommendation_is_kept` | belegte Empfehlung bleibt; `overall_sources` deckt sie |
| `test_no_evidence_forces_abstention` | keine Evidenz → `insufficient_information`, leer |
| `test_recommendation_citing_unknown_evidence_is_dropped` | Falsch-Zitat verworfen → Enthaltung |
| `test_rule_excluded_method_is_removed` | `excluded`-Regel entfernt Kandidat |
| `test_blocking_question_forces_abstention` | blockierende T07-Frage → Enthaltung |
| `test_facts_and_unknowns_come_from_extraction_not_model` | deterministische Felder aus T06 |
| `test_invalid_json_is_retried_then_fails` | Retry-Budget + `SynthesisError` |
| `test_auth_error_not_retried` | nicht-retrybarer `ProviderError` sofort |

> Ausführungsstand: Die Guardrail-Verzweigungen (Grounding/Exclusion/Abstention/
> out_of_scope) wurden offline mit Stand-in-Objekten gegen die echte Logik
> verifiziert. `tests/test_synthesis.py` importiert `src.models` (pydantic) und
> läuft mit der vollen Suite erst in einer Umgebung mit Netzzugriff:
> `uv sync --locked && uv run --locked pytest -q`.

---

## 8. Zusammenspiel und bekannte Grenze

- **T04 ist aktuell ein Stub:** `retrieve()` liefert noch keine echte `Evidence`.
  Solange das so ist, hält T08 die Guardrail ein und gibt live
  `insufficient_information` zurück — das ist korrektes, ehrliches Verhalten,
  keine Fehlfunktion. Sobald T04 echte Passagen liefert, entstehen belegte
  Kandidaten **ohne Code-Änderung an T08**.
- **T10 (Gate):** validiert den Entwurf später zusätzlich (Seitenexistenz,
  Evidenz-Zuordnung, Claim-Unterstützung). T08 ist die erste, nicht die letzte
  Prüfschicht.
- **Few-Shot (T05):** optional; nicht Teil der harten T08-Abhängigkeiten
  (T03/T04/T07) und in v1 nicht eingebunden.
