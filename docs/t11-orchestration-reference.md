# T11 LangGraph-Orchestrierung: technische Referenz & Fehlerdiagnose

Diese Doku beschreibt die Implementierung von T11 so ausführlich, dass sich ein
Fehlverhalten rückwärts bis zur verursachenden Stelle nachvollziehen lässt.
Bezug: `src/engine/graph.py`, `src/engine/service.py`, der typisierte State in
`src/state.py` und die Verträge in `src/models.py`. Baut auf den bereits
gemergten Bausteinen T06 Extraktion
([t06-extraction-reference.md](t06-extraction-reference.md)), T07 Lückenanalyse
([t07-gap-analyzer-reference.md](t07-gap-analyzer-reference.md)), T08 Synthese
([t08-synthesis-reference.md](t08-synthesis-reference.md)), T03 Regel-Matrix
(`src/knowledge/rules.py`) und T04 Retrieval (`src/knowledge/retrieval.py`) auf.

---

## 1. Zweck und Leitidee

T11 verbindet die einzelnen Pipeline-Bausteine zu einer kontrollierten Pipeline
hinter einer einzigen öffentlichen Funktion: `analyze(query)`. UI (T12) und Batch
(T14) rufen genau diese Funktion auf, damit beide Pfade dieselbe Logik und
dieselben Garantien nutzen.

Die zentrale Design-Entscheidung: Der Graph ist bewusst linear sequenziert. In
v1 schreibt jeder Knoten ein partielles Dict-Update, und es gibt keine
konkurrierenden Schreiber auf dasselbe Feld. Die Reihenfolge erfüllt alle
Datenabhängigkeiten, bevor ein Feld gelesen wird (`rules` vor `gaps`,
`rules` und `evidence` vor `synthesis`). Die Korrekturschleife hat eine feste
Obergrenze und ein definiertes Fehlerergebnis, sodass aus einem
Validierungsfehler nie eine fachliche Freigabe wird.

Öffentliche Einstiegspunkte:

| Aufruf | Datei | Zweck |
|---|---|---|
| `analyze(query)` | `service.py` | Einziger öffentlicher Einstieg für UI und Batch; Guard, `require_llm()`, Graph-Lauf, Ergebnis |
| `build_graph()` | `graph.py` | Baut und kompiliert den typisierten `StateGraph` |
| `compiled_graph()` | `graph.py` | Liefert den einmal kompilierten Graphen (Cache) |
| `rules_node(state)` | `graph.py` | T11-Adapter um `evaluate_rules`; setzt `state["rules"]` |
| `retrieval_node(state)` | `graph.py` | T11-Adapter um `retrieve`; setzt `state["evidence"]` (k aus Settings) |
| `experiment_node(state)` | `graph.py` | Seam für T09 (B6); aktuell Pass-through |
| `gate_node(state)` | `graph.py` | B7-Gate (T10); Default Pass-through, definiertes Fehlerergebnis an der Grenze |
| `should_revise(state)` | `graph.py` | Bedingte Kante nach dem Gate: `"revise"` oder `"end"` |

---

## 2. Graph-Topologie

Der kompilierte `StateGraph` wird über den typisierten `PipelineState`
(TypedDict in `src/state.py`) betrieben. Die reale, linear sequenzierte Topologie:

```
START
  -> extraction      (B2, extraction_node, setzt extraction)
  -> rules           (B3-Matrix, rules_node, setzt rules)
  -> retrieval       (B4, retrieval_node, setzt evidence)
  -> gaps            (B3-Fragen, gaps_node, liest rules, setzt questions)
  -> synthesis       (B4/B5, synthesis_node, liest extraction+rules+questions+evidence, setzt draft)
  -> experiment      (B6-Seam, experiment_node, Pass-through)
  -> gate            (B7, gate_node, setzt result oder leitet Revision ein)
  -> {revise -> increment_revision -> synthesis | end -> END}
```

Die Reihenfolge ist kein Zufall, sondern erfüllt die Datenabhängigkeiten:

- `rules_node` läuft vor `gaps_node`, weil `gaps_node` `state["rules"]` liest.
- `rules_node` und `retrieval_node` laufen vor `synthesis_node`, weil die Synthese
  `extraction`, `rules`, `questions` und `evidence` liest.

### Knoten-Adapter (dünne Wrapper)

- `rules_node` ruft `evaluate_rules(state["extraction"])` auf (Kevins Modul).
- `retrieval_node` ruft `retrieve(state["query"], k)` auf, wobei `k` aus
  `Settings().afs_retrieval_k` stammt.

Beide Adapter leben laut Teamregel in `graph.py`, nicht in `rules.py` oder
`retrieval.py`. `extraction_node`, `gaps_node` und `synthesis_node` stammen
unverändert aus den bestehenden Engine-Modulen und werden hier nur verdrahtet.

---

## 3. Bounded Correction Loop und definiertes Fehlerergebnis

Die Obergrenze `MAX_REVISIONS` wird aus `Settings().afs_max_retries` abgeleitet
(dokumentierte Wiederverwendung: die Synthese darf so oft nachgebessert werden,
wie ein Provider-Call wiederholt werden darf). Bei `afs_max_retries = 0` läuft die
Pipeline genau einmal. `service.analyze` koppelt die Grenze zur Laufzeit über
`set_max_revisions(settings.afs_max_retries)` an die aktive Konfiguration.

Der Schleifenzähler `revision_count` startet bei 0 (im Initialzustand gesetzt) und
wird vor jedem Rücksprung zur Synthese über `increment_revision` erhöht.

Die bedingte Kante `should_revise` entscheidet nach dem Gate:

- Es gibt eine `ValidationReport` in `state["validation"]`, sie meldet Fehler
  (`has_errors`) UND `revision_count < MAX_REVISIONS`: Rückgabe `"revise"`, der
  Graph springt über `increment_revision` zurück zu `synthesis`.
- Sonst (kein Validator, keine Fehler oder Obergrenze erreicht): Rückgabe
  `"end"`, der Graph terminiert.

### Definiertes Fehlerergebnis

Wird die Obergrenze erreicht und die Validierung meldet weiterhin Fehler, erzeugt
`gate_node` über `_failure_result` ein definiertes Fehlerergebnis: eine gültige
`AnalysisResult` mit `decision_status = "insufficient_information"` (bewusst nicht
`provisional`), die die Gate-Befunde in `validation_findings` trägt. An die
Befunde wird ein zusätzlicher `ValidationFinding` mit dem Code
`REVISION_LIMIT_CODE` (`"revision_limit_reached"`) und `severity = "error"`
angehängt. Es werden keine Fakten, Kennwerte oder Quellen erfunden: Die
deterministischen Felder stammen aus dem Synthese-Entwurf; `recommendations` und
`overall_sources` werden geleert, da sie das Gate nicht bestanden haben. Fehlt ein
Entwurf vollständig, wird eine minimale, aber gültige `AnalysisResult` gebaut.

---

## 4. Fehlerbehandlung (Timeouts, API-Fehler, fehlender Key)

- Fehlender Key: `analyze` ruft `Settings().require_llm()` früh auf. Fehlen
  `OPENAI_API_KEY` oder `OPENAI_MODEL`, scheitert der Aufruf sofort mit einer
  klaren `ConfigurationError`, bevor ein Provider kontaktiert wird (fail-fast).
- Leere oder nicht-String-Query: `analyze` wirft `ValueError`, bevor die Pipeline
  startet.
- API-Fehler und Timeouts: Diese werden innerhalb der Knoten über die bestehenden
  Bausteine behandelt. Ein nicht wiederholbarer `ProviderError`
  (`ProviderError.retryable = False`, z. B. HTTP 401) propagiert unverändert nach
  oben. Wiederholbare Fehler (`retryable = True`) teilen sich das bausteininterne
  Retry-Budget (`1 + afs_max_retries`).
- Es werden nie Provider-Antworten (Response-Bodies) oder Credentials geleakt; die
  bestehende Fehler-Sanitisierung der Bausteine bleibt wirksam.
- Ein API- oder Parsing-Fehler wird nie zu einer fachlichen Freigabe: Entweder
  propagiert der Fehler, oder die Korrekturschleife endet im definierten
  Fehlerergebnis (`insufficient_information`).

### Ergebnis-Rückgabe

`analyze` liefert `state["result"]` zurück (das Gate-Ergebnis). Hat noch kein Gate
ein Ergebnis gesetzt (Default-Pfad), fällt es auf `state["draft"]` zurück, sodass
der Synthese-Entwurf als Ergebnis dient.

---

## 5. Offene Grenzen / Seams

Diese Seams sind bewusst markiert und strukturell vorbereitet, aber in v1 noch
nicht ausimplementiert:

- T10 B7 Validierungs-Gate (`src/engine/validators.py`, Kevin): Noch nicht
  implementiert. Der Default-Pfad ohne Validator reicht den Synthese-Entwurf
  unverändert als `state["result"]` durch (Pass-through) und terminiert nach einem
  Lauf. Sobald T10 landet, wird der Validator in `gate_node` eingehängt; die
  Schleife konsumiert dann `ValidationReport.has_errors`. Die Struktur
  (`should_revise`, `_failure_result`) ist dafür bereits vorbereitet.
- T09 B6 Versuchsplan (`src/engine/experiment.py`, Jakob): Noch nicht
  implementiert. `AnalysisResult` trägt heute schon `feasibility_plan` und
  `go_no_go_criteria` aus der Synthese, daher ist noch kein eigener
  Experiment-Knoten nötig. `experiment_node` ist ein markierter Platzhalter
  (Pass-through), in den T09 später einsteigt.
- T05 Few-Shot-Beispiele (`examples`): Nicht implementiert; das State-Feld bleibt
  optional und leer, die Synthese akzeptiert den leeren Pfad.

### Ausführungsstand der Tests

Die Offline-Tests (`tests/test_graph.py`, `tests/test_service.py`) folgen dem
bestehenden Muster (FakeProvider/monkeypatch, `pytest.importorskip` für
pydantic/langgraph) und decken die Knoten-Adapter, das Gate-Pass-through, die
`should_revise`-Übergänge, das definierte Fehlerergebnis an der Obergrenze, den
Happy-Path über `build_graph().invoke`, die Propagierung eines nicht
wiederholbaren `ProviderError`, die Query-Guards und die `ConfigurationError` bei
fehlendem Key ab.

Die Testsuite wurde in der Sandbox NICHT ausgeführt, weil PyPI gesperrt ist
(HTTP 403; pydantic/langgraph/httpx/streamlit nicht installierbar). Ein Reviewer
mit funktionierender Umgebung verifiziert mit:

```
uv sync --locked && uv run --locked pytest -q tests/test_graph.py tests/test_service.py
```
