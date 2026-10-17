# T10 — B7 Zitations- und Physik-Gate · Deep-Dive-Analyse

> Branch: `feat/t10-citation-physics-gate` (von aktuellem `main`) · Verantwortlich: Kevin
> Analyse **vor** der Umsetzung. Grundlage für `T10_plan.md`.

## 1. Was T10 verlangt (Abnahmekriterien, wörtlich)

- [ ] Quellen-ID, Seite und Evidenzpassage werden **gegen den Katalog** geprüft.
- [ ] Regeln prüfen bekannte **Kompatibilitätsbedingungen und Einheiten**.
- [ ] Fehlende Evidenz oder kritische Regelverletzungen **verhindern eine
      unbegründete Freigabe**.
- [ ] Befunde unterscheiden **Fehler / Warnung / nicht automatisiert prüfbar**.
- [ ] Eine existierende Seite gilt **nicht automatisch als semantischer Beleg**;
      Grenzen der Prüfung sind dokumentiert.
- [ ] Tests enthalten **erfundene Quellen, unpassende Belege und unbelegte
      Hardwarefreigaben**.

**Dateibereich:** `src/engine/validators.py` (gehört Kevin innerhalb `engine/`),
`scripts/check_citations.py` · **Abhängigkeit:** T03, T09.
**Kollision:** Jakob integriert das Gate in T11, ändert aber **nicht** die
Implementierung. `graph.py` **nicht** von mir ändern.

## 2. Vertrag & Integrationspunkt (gemergt auf `main`)

- **Contract** (`src/contracts.py`):
  ```python
  class ResultValidator(Protocol):
      def __call__(self, result: AnalysisResult,
                   evidence: list[Evidence],
                   rules: list[RuleFinding]) -> ValidationReport: ...
  ```
- **`ValidationFinding`** (`src/models.py`): `code`, `severity ∈
  {error, warning, not_checked}`, `message`, `field_path`, `evidence_ids`.
  → Die drei `severity`-Werte sind **exakt** die vom Ticket geforderten
  Kategorien (Fehler / Warnung / nicht automatisiert prüfbar).
- **`ValidationReport`**: `findings: list[ValidationFinding]`, Property
  `has_errors` (True wenn ein `error` dabei ist).
- **T11-Integration** (`src/engine/graph.py::gate_node`, bereits dokumentiert):
  - Mein Validator wird in `gate_node` eingehängt, `has_errors` steuert die
    Korrekturschleife (`should_revise`).
  - **KRITISCH:** Der Validator muss bei **jedem** Gate-Durchlauf **neu**
    validieren und eine **frische** `ValidationReport` liefern — **kein**
    internes State-Caching. (Ein veralteter Report würde die Schleife brechen.)
  - Ein Fehler führt nie zu Freigabe: Gate erzeugt bei erschöpfter Schleife
    `decision_status="insufficient_information"` mit den Befunden. (Das macht
    `gate_node`; mein Validator liefert nur den Report.)

## 3. Was der Validator prüft (abgeleitet aus Verträgen + Material)

### 3a. Zitations-Gate (Quellen/Evidenz gegen Katalog)
Eingaben: `result.recommendations[*].source_refs` (SourceReference:
source_id+page) **und** `evidence_ids` (Text, ≥1), `result.overall_sources`,
die gelieferte `evidence: list[Evidence]`, der Katalog (`catalog.get_entry`).

Prüfungen:
1. **Erfundene Quelle / Seite:** jede `SourceReference` muss einen bekannten
   `source_id` (S01–S06) haben; Seite muss zur Katalog-Seitenspanne passen
   (S06 ohne Seite). Verletzung → **error** (erfundene/nicht existente Quelle).
2. **Evidence-ID existiert:** jede `recommendation.evidence_ids` muss in der
   gelieferten `evidence`-Liste vorkommen. Fehlt sie → **error** (Behauptung
   ohne unterlegte Evidenz).
3. **Evidenz-Scope passt:** verweist eine technische Empfehlung auf
   `purpose="business_context"`-Evidenz (S05/S06) als Beleg → **error**
   (Unternehmenskontext ist kein Leistungsbeleg). Forschungsscope (S03/S04) für
   eine klinische/Prozess-Freigabe → **warning/error** je nach Behauptung.
4. **Seite ≠ semantischer Beleg:** existiert die Seite zwar, lässt sich der
   Claim aber nicht automatisch verifizieren → **not_checked** (ausdrücklich als
   Grenze der automatischen Prüfung markiert, Abnahmekriterium 5).

### 3b. Physik-/Einheiten-Gate
Eingaben: `result.recommendations[*].spectral_range` (SpectralRange).
Der Contract erzwingt bereits aufsteigende Grenzen + nm↔wavelength /
cm⁻¹↔wavenumber/raman_shift. Das Gate ergänzt **belegbare**, nicht schon vom
Schema erzwungene Checks:
1. **`scope="verified_instrument"` ohne Beleg:** eine als gerätegeprüft
   markierte Spanne ohne stützende Evidence/Beleg → **error** (unbelegte
   Hardwarefreigabe; nominale ≠ Geräte-Spanne).
2. **Nominalbereichs-Plausibilität:** NIR 780–2500 nm, MIR 4000–400 cm⁻¹ als
   bekannte nominale Bereiche; eine Spanne weit außerhalb ohne Beleg →
   **warning**.
3. **Methode↔Einheit-Konsistenz:** MIR sollte in cm⁻¹, NIR in nm argumentiert
   werden (nur Warnung, da Contract Grundkonsistenz schon sichert).

### 3c. Regel-Gate (kritische RuleFindings)
Eingaben: `rules: list[RuleFinding]` (von T03).
- Ein `outcome="excluded"`-RuleFinding, dessen Thema eine Empfehlung dennoch
  als Freigabe/`provisional` vertritt → **error** (belegter Widerspruch).
- `outcome="unknown"` bei entscheidungsblockierendem Parameter, während das
  Ergebnis `provisional` statt `insufficient_information` ist → **warning/error**
  (unbegründete Freigabe trotz offener Lücke, Abnahmekriterium 3).
- **Generisch:** keine Szenario-ID-Logik; nur über RuleFinding-Outcomes.

## 4. „Verhindert unbegründete Freigabe" — Rollenverteilung

- **Mein Validator** erzeugt nur die `ValidationReport` (Befunde). Er **ändert
  nicht** den `decision_status`.
- **`gate_node` (Jakob, T11)** konsumiert `has_errors` und setzt bei Fehlern
  `insufficient_information`. → Saubere Trennung: ich liefere die Diagnose,
  die Pipeline zieht die Konsequenz. Das deckt Abnahmekriterium 3 im
  Zusammenspiel (ich dokumentiere das als Schnittstelle).

## 5. `scripts/check_citations.py`

Eigenständiges CLI (für D-/H-Batch-QA, Abnahme/Repro): liest ein gespeichertes
`AnalysisResult`-JSON + den Index/Katalog, läuft denselben Zitations-Check und
meldet Befunde (Exit-Code ≠ 0 bei errors). Nutzt dieselbe Validator-Logik
(keine Duplikation der Regeln).

## 6. Grenzen der automatischen Prüfung (explizit, Abnahmekriterium 5)

- Das Gate prüft **Existenz/Scope/Format** von Quellen, Seiten, Evidence-IDs und
  Einheiten — **nicht** die inhaltliche Wahrheit eines Claims. „Seite existiert"
  ≠ „Seite belegt den Claim". Solche Fälle werden als **`not_checked`** markiert,
  nicht als bestanden. Das ist im Report-Code und in der Doku festgehalten.
- Kein LLM/semantisches Matching im Gate (deterministisch, reproduzierbar).

## 7. Risiken / offene Punkte

| Punkt | Umgang |
|---|---|
| pydantic/uv in Sandbox blockiert | Pure-Logik (Katalog-Seitencheck, Evidence-ID-Abgleich, Scope-/Einheiten-Regeln) mit stdlib-Stubs testen; Contract-Konstruktion via `importorskip`. Voller Lauf lokal. |
| T09 noch nicht gemergt | T10 braucht nur `AnalysisResult` (feasibility_plan ist schon drin via Synthese). Gegen main-Stand bauen; kein Zwang auf T09. |
| Frische Validierung pro Durchlauf | Validator ist **zustandslos/pure function** — kein Caching; erfüllt die T11-Seam-Anforderung. |
| Freigabe-Logik-Grenze | Validator setzt KEIN decision_status; nur Report. `gate_node` zieht die Konsequenz (dokumentiert). |
| Katalog-Import zieht pydantic | Seitencheck nutzt `catalog` lazy; Fallback auf statische S0x-Seitenspannen für Pure-Logik-Tests (wie in rules.py). |

## 8. Braucht es LLM / API-Key?

**Nein.** T10 ist deterministische Validierung (Katalog/Format/Einheiten/Regel-
Outcomes). Kein Embedding, kein LLM, kein Key. Tests offline; voller Lauf lokal.
