# T03 — Deterministische Regel-Matrix · Deep-Dive-Analyse

> Branch: `feat/t03-rule-matrix` (von `main` nach T01+T02-Merge) · Verantwortlich: Kevin
> Analyse **vor** der Umsetzung. Grundlage für `T03_plan.md`.

## 1. Was T03 verlangt (Abnahmekriterien, wörtlich)

- [ ] Jede Regel enthält stabile ID, Bedingungen, Ergebnis und Quellenbeleg.
- [ ] Ergebnisse unterscheiden **ausgeschlossen / bedingt geeignet / unbekannt**;
      fehlende Angaben erzeugen **keine Freigabe**.
- [ ] Qualitative XLSX-Bewertungen werden **nicht** zu quantitativen
      Gerätespezifikationen umgedeutet.
- [ ] Nominale Methodenbereiche werden von konkreten Faser-/Gerätebereichen getrennt.
- [ ] Tests prüfen belegte Einschränkungen + Verhalten bei unbekannten Parametern;
      **keine Szenario-ID-Verzweigungen**.

**Dateibereich:** `src/knowledge/rules.py`, `data/rules/` · **Abhängigkeit:** T02.
**Kollision:** keine direkten Dateikonflikte mit Jakob. Schnittstelle zu T07/T08
(Eingabeparameter, Rückgabeformat, Bedeutung von unknown/conditional/excluded)
ist abzustimmen. **`src/models.py` ändert Jakob**, nicht Kevin.

## 2. Aktueller Stand (gemergt auf `main`)

- **T01 + T02 sind auf `main`.** Verfügbar: `src/models.py`, `src/contracts.py`,
  `src/knowledge/{catalog,ingest,types,retrieval}.py`, `data/source_notes/`.
- **Der Vertrag für T03 steht schon in `src/models.py` (main):**
  ```python
  class RuleFinding(ContractModel):
      rule_id: Text
      outcome: Literal["excluded", "conditional", "unknown"]
      reason: Text
      source_refs: Annotated[list[SourceReference], Field(min_length=1)]
  ```
  ```python
  # src/contracts.py
  class RuleEvaluator(Protocol):
      def __call__(self, extraction: ExtractionResult) -> list[RuleFinding]: ...
  ```
- **T06 (Jakob, noch NICHT gemergt, Branch `feat/t06-parameter-extractor`):**
  erweitert `ExtractionResult` additiv um `extraction_version="1.1"`,
  `conflicts: list[ParameterConflict]`, `ExtractedFact.numeric_value:
  NumericValue|None`. **`ParameterName`** (16 feste Werte) ist bereits definiert
  und ist die verbindliche Parameterliste (siehe `docs/parameters.md`).
  V-2 (`verify_quotes`) ist dort noch offen — für T03 irrelevant.

**Konsequenz:** T03 baut gegen `RuleFinding` (stabil) und konsumiert
`ExtractionResult.stated_facts[*].parameter ∈ ParameterName`. Die additiven
T06-Felder (`numeric_value`, `conflicts`) **darf** T03 nutzen, **muss** aber
robust sein, wenn sie fehlen (T06 noch nicht gemergt). → T03 liest nur
`parameter` + `value` (Text) und behandelt `numeric_value` als optionales Extra.

## 3. Regelquellen (real verifiziert)

### 3a. XLSX `method_comparison` (bereits von T02 ingestiert, S01 Table 1 p.6)
19 Zeilen, Spalten: `method, measurement_technique, physical_phenomenon,
sample_type, optical_path_or_depth, sensitivity, selectivity, cost`.
**Kernnutzen für Regeln:** `method × measurement_technique(=Geometrie) × sample_type`.

Verdichtete Matrix (sample_type → plausible Methode/Geometrie):
| sample_type (XLSX) | plausible Methoden/Geometrien (belegt) |
|---|---|
| liquid | IR cuvette; NIR cuvette/transmission; Raman cuvette/probe; UV/Vis cuvette/transmission; Fluorimetrie |
| liquid, paste, soft | IR ATR (platform/probe) |
| scattering media, powder | NIR diffuse reflection probe |
| solid, powder | NIR integrating sphere / surface at a distance |
| solid | IR sample surface (diffuse reflection) |
| solid film | IR sample layer |
| solid, pill | UV/Vis diffuse reflection probe |
| liquid, colloidal | NIR transmission/transflection |
| liquid, powder, solid | Raman probe |
| liquid, solid | Fluorimetrie-Probe |
| radiating sample | UV/Vis emission |

**Ratings `sensitivity/selectivity/cost` sind qualitativ (low/avg/high)** →
dürfen **nie** als Messwert/Gerätespezifikation ausgegeben werden (nur als
qualitativer Hinweis mit XLSX-Beleg).

### 3b. S01-Methodenübersicht (nominale Bereiche — NUR nominal, NICHT Gerät)
NIR **780–2500 nm**; MIR **4000–400 cm⁻¹**; Raman: Anregung (nm) ≠ Raman-Shift
(cm⁻¹); Fluoreszenz: hängt vom Fluorophor ab; UV/Vis: zielabhängig.
Belege: S01 p.5–6, 10, 11–12, 14–18; XLSX = S01 Table 1 (p.6).

### 3c. Belegte Kompatibilitäts-/Vorsichtsregeln (aus Masterprompt + Strategiepapier + DOCX)
Diese sind **allgemeine, belegte Domänenregeln** — **keine** Szenario-Hacks:
| Regel-Thema | Ergebnis | Beleg |
|---|---|---|
| NIR-Kalibrierung überträgt sich NICHT automatisch auf neue API/Excipient-Rezeptur | conditional (Validierung nötig) | S01 p.10, 14–15 |
| Raman hinzufügen rettet alte Kalibrierung NICHT automatisch | conditional | S01 p.11, 14–16 |
| Klare vs. trübe/streuende Flüssigkeit → andere Geometrie (Transmission vs. Reflexion) | conditional | S01 p.17–18; XLSX |
| Fluoreszenz-Empfindlichkeit ≠ direkter Glukose-/Viable-Biomass-Nachweis ohne Fluorophor/Referenz | conditional/excluded (ohne Marker) | S01 p.5–6, 16; S04 |
| MIR-ATR auf vorhandener Vis/NIR-Silica-Faser NICHT freigegeben ohne Transmissionsnachweis | conditional (nicht freigeben) | S01 p.6, 9–10; S02 p.6, 13–14 |
| Nominaler Methodenbereich ≠ nutzbarer Faser-/Sondenbereich | conditional (immer) | S02 p.6; S01 p.10 |
| Undefinierter Zielstoff/Kontaminant → KEINE exakte Sensorspezifikation | unknown (keine Freigabe) | DOCX §3 „Do not invent"; S01 p.5–6 |
| In-vitro-Studie (LED-Kidney) ≠ klinische/OP-Einsatzreife | excluded (für OP-Claim) | S03; DOCX §3 |

## 4. Entscheidende Design-Fragen (für den Plan)

1. **Regel-Repräsentation:** deklarativ in `data/rules/*.yaml` (ID, when-Bedingungen
   auf `ParameterName`, outcome, reason, source_refs) + schlanke, **generische**
   Engine in `rules.py`. Kein `if "kidney"`-Code.
2. **Bedingungen matchen gegen was?** Gegen `ExtractedFact.parameter`
   (∈ ParameterName) + Textwert. Da `value` Freitext ist (T06-Regel: keine stille
   numerische Interpretation), arbeiten Bedingungen mit **Schlüsselwort-/
   Enthaltensein-Prädikaten** auf dem Wert, nicht mit Zahlenvergleichen.
3. **„fehlende Angaben → keine Freigabe":** Fehlt ein für eine Regel nötiger
   Parameter in `stated_facts`, ist das Ergebnis **`unknown`** (nie `excluded`
   als Scheinentscheidung, nie eine positive Freigabe).
4. **`source_refs` Pflicht (≥1):** jede Regel trägt mind. einen `SourceReference`
   (S0x+page oder S01 p.6 für XLSX). Keine erfundenen Seiten.
5. **Rückgabe:** `list[RuleFinding]` exakt nach Vertrag. `outcome` nur aus
   {excluded, conditional, unknown} — es gibt bewusst **kein „approved"**.

## 4b. T06 Deep Dive — Parameter-Versionierung (Steering-Fokus)

Vollständige Durchsicht von `feat/t06-parameter-extractor`
(`src/engine/extraction.py`, `provider.py`, `src/models.py`):

**Versionierungs-Ist-Zustand in T06:**
- `SCHEMA_VERSION = "1.0"` global (auf `AnalysisResult.schema_version`).
- `ExtractionResult.extraction_version = Literal["1.1"]` → T06 hat die
  Extraktions­struktur **additiv** von 1.0→1.1 angehoben (`conflicts`,
  `ExtractedFact.numeric_value`, `NumericValue`).
- **`ParameterName` (die 16-Werte-Liste) ist NICHT separat versioniert.** Kein
  `PARAMETER_VERSION`-Marker in `models.py`; `docs/parameters.md` nennt keine
  Versionsnummer.

**Wie T06 die Parameter benutzt (wichtig für T03-Regelmatch):**
- `extraction.py::validate_draft` erzwingt `value == input_quote` **und** Zitat
  wörtlich in der Query → `value` ist immer ein **Originalzitat**, nie
  interpretierter/normalisierter Text. ⇒ T03-Bedingungen müssen auf rohem
  Zitattext arbeiten (Schlüsselwort-Prädikate), **keine** Annahme sauberer Enums
  im `value`.
- `scalar_value()` füllt `numeric_value` nur für `temperature/pressure/
  required_response_time` und nur bei exaktem Skalar mit erlaubter Einheit
  (`°C,K,bar(a),bar(g),s,ms`) — sonst `None`. ⇒ T03 darf `numeric_value`
  **optional** nutzen, aber nie voraussetzen.
- `validate_draft` setzt `unknowns` = alle `ParameterName`, die **nicht** in
  `stated_facts` vorkommen **oder** in einem ungelösten `conflict` stehen. ⇒ T03
  bekommt die fehlenden/strittigen Parameter sauber in `unknowns` geliefert und
  kann darauf „unknown → keine Freigabe" stützen.

**Das Problem (dein Steering-Punkt):** T03-Regeln referenzieren
`ParameterName`-Schlüssel. Ändert Jakob die Liste (neuer/umbenannter Parameter),
matchen meine Regeln **still ins Leere** — kein Fehler, nur falsch-leere
Ergebnisse. Die Parameterbasis **muss versioniert** sein, damit T03 beim Laden
prüfen kann, dass seine Regeln gegen die **erwartete** Parameter-Version
geschrieben sind.

**T03-Lösung (ohne `models.py` zu ändern — Jakobs Hoheit):**
1. T03 definiert in `data/rules/` eine `rules_meta` mit
   `expected_parameter_names` = exakte Kopie der 16 Werte **plus**
   `parameter_contract = "T06/parameters.md"`.
2. Beim Laden der Regeln verifiziert `rules.py` **zur Laufzeit** gegen
   `typing.get_args(src.models.ParameterName)`: Stimmt die Menge nicht überein,
   wird ein klarer `RuleConfigError` geworfen (fail-fast statt stilles
   Fehlmatchen). Ein Test friert dieselbe Prüfung ein.
3. Jede Regelbedingung darf **nur** Parameter aus `ParameterName` referenzieren —
   per Validierung beim Laden erzwungen (kein Tippfehler-`temp`/`accuracy`).
4. **Empfehlung an Jakob (separat dokumentiert, nicht selbst umgesetzt):** einen
   expliziten `PARAMETER_VERSION`-Marker neben `ParameterName` in `models.py`
   einführen, analog zu `extraction_version`. Bis dahin ist die Set-Gleichheits-
   Prüfung aus (2) der sichere Ersatz. → geht in den T03-PR als Schnittstellen-
   Hinweis an T06.

## 5. Risiken / offene Punkte

| Punkt | Umgang |
|---|---|
| pydantic/uv in Sandbox blockiert | Engine-Pure-Logik + YAML-Regeln mit Fixtures testen; `RuleFinding`-Konstruktion via `importorskip`. Realer Lauf lokal bei Kevin. |
| T06 noch nicht gemergt (`ExtractionResult` v1.1) | gegen main-Stand bauen; additive T06-Felder optional nutzen, nicht voraussetzen. |
| Gefahr qualitativ→quantitativ | Ratings nur als qualitative `reason`-Hinweise mit XLSX-Beleg; nie als Zahl/Spezifikation. |
| Szenario-Hack-Verbot | Regeln sind allgemeine Domänenprädikate auf ParameterName; Test verbietet H-ID/Szenario-Strings in Regeln. |
| Schnittstelle zu T07/T08 | `RuleEvaluator`-Signatur exakt einhalten; Bedeutung unknown/conditional/excluded in `data/rules/README` dokumentieren und mit Jakob abstimmen. |
