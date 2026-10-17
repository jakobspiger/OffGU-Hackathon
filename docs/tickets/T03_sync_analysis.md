# T03 · Abgleich mit aktuellem `main` (T01+T02+T06+T07) — Fehleranalyse

> Auslöser: Kevin — „pull, T03 mit aktuellem Stand (T01,T02,T06) abgleichen,
> Fehlerquellen suchen, Plan, dann coden; bei grünen Tests mergen."
> Stand nach `git merge origin/main` in `feat/t03-rule-matrix` (konfliktfrei).
> **Noch kein Fix-Code** — erst Analyse + Plan.

## 0. Was sich auf `main` geändert hat (seit T03-Push)

- **T06 (PR #4) gemergt:** `ExtractionResult` jetzt v1.1 mit `conflicts`,
  `ExtractedFact.numeric_value`, `NumericValue`; `verify_quotes` V-2-normalisiert.
- **T07 (PR #7) gemergt:** `src/engine/gaps.py` — **konsumiert direkt
  `list[RuleFinding]` von meinem T03** (`analyze_gaps(extraction, rules)`).
- **`PARAMETER_VERSION = "1.0"` auf `main`** — genau meine T03-Empfehlung wurde
  von Jakob übernommen (Marker neben `ParameterName`).
- Jakob hat `docs/t06-handover-an-kevin.md` geschrieben (Übergabe an T03).
- Mein T03 (PR #5) wurde **vor** all dem erstellt → mein Branch war gegen einen
  Stand gebaut, in dem `ParameterName` noch gar nicht existierte.

## 1. Fehlerquellen (priorisiert)

### F1 — HAUPTFEHLER: `rules_meta` nutzt das neue `PARAMETER_VERSION` nicht
Jakob hat `PARAMETER_VERSION = "1.0"` **ausdrücklich für das T03-Gate**
eingeführt (Kommentar in models.py: „so dependent components (e.g. the T03
rule-set gate) can check a version instead of set equality").
Mein Code prüft aber **nur** Set-Gleichheit von `expected_parameter_names`.
→ **Fix:** `rules_meta.yaml` bekommt `expected_parameter_version: "1.0"`; das
Gate prüft **zusätzlich** `meta.expected_parameter_version == PARAMETER_VERSION`
(und weiterhin die Set-Gleichheit als zweite, inhaltliche Absicherung).
**Risiko wenn nicht gefixt:** Jakob bumpt künftig nur die Version (z. B. Reihen-
folge/Doku) ohne Set-Änderung → mein Gate merkt es nicht. Oder umgekehrt eine
Set-Änderung ohne Versionsbump → Gate greift, aber der vereinbarte Mechanismus
(Versionsnummer) wird ignoriert. Beides sauber abgedeckt mit beiden Prüfungen.

### F2 — Veraltete Test-Skips „T06 not merged"
`tests/test_rules.py` skippt 5 Tests mit Begründung „ParameterName not in
src.models yet (T06 not merged)". **Das ist jetzt falsch** — T06 **ist**
gemergt, `ParameterName` existiert. In der Sandbox skippen sie weiterhin (kein
pydantic), aber die **Begründung ist irreführend** und lokal bei Kevin (mit uv)
würden sie jetzt real laufen — dafür müssen sie korrekt sein.
→ **Fix:** Skip-Grund nur noch an pydantic/Umgebung koppeln, nicht an „T06 nicht
gemergt". Die ParameterName-`ImportError`-Zweige können bleiben (defensiv),
aber der Normalpfad ist jetzt „vorhanden".

### F3 — `_expected_parameter_names()` wirft bei fehlendem `ParameterName`
War als Fail-fast gedacht, als `ParameterName` noch nicht existierte. Jetzt
existiert es; der Zweig ist toter/irreführender Pfad für die Sandbox. Harmlos,
aber sollte an F1/F2 angepasst werden (Versionscheck zuerst).

### F4 — Integrationsfläche zu T07 (gaps.py) verifizieren — KEIN Codefehler
T07 liest `finding.outcome` (nur `"unknown"` löst blockierende Rückfrage aus)
und `finding.rule_id` / `finding.reason`. Mein `RuleFinding` liefert exakt diese
Felder, und meine Engine erzeugt `outcome="unknown"` bei fehlenden/strittigen
Pflichtparametern — **deckt sich 1:1** mit T07s Erwartung und Jakobs Handover
(conflicts/unknowns → unknown, keine Freigabe).
→ **Kein Fix nötig**, aber ich ergänze einen **Integrationstest**, der
`evaluate_rules` → `analyze_gaps` verkettet, damit die Schnittstelle
regressionssicher ist.

### F5 — `numeric_value`/`conflicts` werden bereits robust gelesen
Mein Code liest beide getattr-sicher und behandelt konflikt-behaftete Parameter
als „unknown". Jakobs Handover Punkt 1–4 bestätigt genau dieses Verhalten.
→ **Kein Fix nötig**; ich ergänze einen Test, der einen `conflicts`-Parameter →
`unknown`-Finding nachweist (gegen den echten v1.1-Vertrag).

## 2. Was NICHT kaputt ist (bewusst geprüft)

- Keine Merge-Konflikte; T03 berührt nur eigene Dateien.
- `RuleFinding`/`RuleEvaluator`-Vertrag unverändert → `evaluate_rules`-Signatur
  passt weiter.
- Die 16 `ParameterName`-Werte sind unverändert → `expected_parameter_names`
  stimmt bereits.
- Keine Szenario-ID-Verzweigung; qualitative Ratings nie numerisch.

## 3. Braucht es den LLM / API-Key? (Kevins Frage)

**Nein — T03 benötigt KEIN LLM und KEINEN API-Key.** T03 ist rein
deterministische Logik (YAML-Regeln + Prädikate auf bereits extrahiertem Text).
Der einzige Live-LLM-Pfad im Repo ist `scripts/smoke_llm.py`, und der testet
**T06** (den Extraktor), nicht T03.
→ Für T03 reicht `uv run --locked pytest -q` **ohne** `.env`/Key. Du musst nur
dann lokal mit eurem LLM testen, wenn du zusätzlich die **T06-Extraktion** live
gegen euer GWDG-LLM prüfen willst (optional, separater Schritt).

## 4. Umgebungsnotiz

pydantic/uv weiterhin in der Sandbox blockiert → die pydantic-abhängigen Tests
(inkl. neuer Integrationstest) laufen hier als `skip`, aber **vollständig grün
bei Kevin lokal** via `uv run --locked pytest -q`. Pure-Logik (Gate,
YAML-Parsing, Prädikate, Versionsvergleich) läuft in der Sandbox real.
