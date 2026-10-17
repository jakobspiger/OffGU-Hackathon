# T06 B2 Parameter-Extraktor — technische Referenz & Fehlerdiagnose

Diese Doku beschreibt die Implementierung von T06 so ausführlich, dass sich ein
Fehlverhalten rückwärts bis zur verursachenden Stelle nachvollziehen lässt.
Bezug: `src/engine/extraction.py`, `src/engine/provider.py`, `src/models.py`
(Vertrag `extraction_version="1.1"`). Ergänzt
[parameters.md](parameters.md), [contracts.md](contracts.md) und die
Regel-Folgen für T03 in [t06-handover-an-kevin.md](t06-handover-an-kevin.md).

---

## 1. Zweck und Grenzen

B2 strukturiert Kundenfreitext in typisierte Fakten, **ohne** zu erfinden. B2
macht **kein** Retrieval, keine Methodenwahl, keine Fachbewertung und keinen
Zugriff auf finale Szenarien. Alles, was nicht wörtlich in der Anfrage steht,
wird nicht zu einem Fakt.

Öffentliche Einstiegspunkte:

| Aufruf | Datei | Rückgabe / Zweck |
|---|---|---|
| `extract(query, *, provider=None, settings=None)` | `extraction.py` | `ExtractionResult`; orchestriert Call + Validierung + Retries |
| `scalar_value(parameter, value)` | `extraction.py` | `NumericValue \| None`; konservativer Skalar-Parser |
| `extraction_node(state)` | `extraction.py` | T11-Graph-Adapter: setzt nur `state["extraction"]` |
| `ChatJSONProvider.complete(system, query)` | `provider.py` | roher Antworttext des LLM |
| `scripts/extract_query.py` | `scripts/` | CLI: stdin → validiertes JSON auf stdout |
| `scripts/smoke_llm.py` | `scripts/` | Live-Smoke-Test gegen echten Provider |

---

## 2. Datenfluss von `extract()` (Schritt für Schritt)

```
query
  │  (1) Eingabe-Guards
  ▼
Settings laden ──► ChatJSONProvider (wenn kein provider übergeben)
  │  (2) System-Prompt = SYSTEM_PROMPT + JSON-Schema(ExtractionDraft)
  ▼
Schleife attempt = 0 .. afs_max_retries:
  provider.complete(system, query)  ──► roher Text (3)
      │
      ▼
  validate_draft(raw, query)        ──► ExtractionResult (4)-(9)
      │ Erfolg → return
      │ ProviderError.retryable=False → raise (sofort)
      │ ProviderError.retryable=True  → nächste Runde
      │ ValueError (Validierung)      → Prompt verschärfen, nächste Runde
      ▼
  (nach letzter Runde) raise ExtractionError
```

### (1) Eingabe-Guards — `extract()`
- `query` kein `str` oder leer/nur Whitespace → `ValueError` (kein Provider-Call).
- `len(query) > MAX_QUERY_LENGTH` (20000) → `ValueError`.
- **Konsequenz für Debugging:** Ein `ValueError` *vor* jedem Netzwerkverkehr
  bedeutet immer schlechte Eingabe, nie ein Modellproblem. `FakeProvider.calls`
  bleibt in Tests leer (siehe `test_bad_input_never_calls_provider`).

### (2) Prompt-Konstruktion
`system = SYSTEM_PROMPT + json.dumps(ExtractionDraft.model_json_schema(), ensure_ascii=False)`.
Das Schema stammt aus `ExtractionDraft` (nur `stated_facts` + `conflicts`), **nicht**
aus dem vollen `ExtractionResult`. `assumptions`/`unknowns` werden absichtlich nicht
vom Modell erzeugt, sondern deterministisch nachgelagert gefüllt (siehe 8/9).

### (3) Provider-Call — siehe Abschnitt 3.

### (4) JSON-Parsing — `validate_draft()`
- Erst `ExtractionDraft.model_validate_json(raw)` direkt.
- Scheitert das mit `ValueError` (z. B. Codefence/Prosa um das JSON), wird
  `_extract_json_object(raw)` angewandt und erneut validiert. Nur echter Müll
  wirft weiter `ValueError`.
- `ExtractionDraft` hat `extra="forbid"` (via `ContractModel`). Zusätzliche
  Felder (z. B. ein erfundenes `accuracy`) führen zu `ValueError` →
  `test_extra_provider_fields_rejected`.

### (5) Zitatprüfung pro Fakt
Für jeden `DraftFact`:
- `fact.value != fact.input_quote` → `ValueError`. Wert und Zitat **müssen
  dieselbe Spanne** sein. Ein umgeschriebener/gekürzter Wert fliegt raus
  (`test_ungrounded_or_rewritten_values_are_rejected`).
- `_normalize_for_quote_check(fact.input_quote) not in haystack` → `ValueError`.
  `haystack = _normalize_for_quote_check(query)`. Die Normalisierung (siehe 6)
  erlaubt reine Darstellungsunterschiede, lehnt aber tatsächlich fehlende Zitate ab.

### (6) `_normalize_for_quote_check` (in `src/models.py`)
Reihenfolge: `unicodedata.normalize("NFC", …)` → `translate(_QUOTE_TRANSLATION)`
(smart quotes/Dashes/NBSP → ASCII) → `" ".join(split())` (Whitespace kollabieren)
→ `casefold()`.
- **Bewusst NICHT normalisiert:** Satzzeichen, Synonyme, Stemming. Dadurch bleibt
  der Halluzinationsschutz erhalten (ein erfundenes Wort fällt weiter durch).
- `input_quote` wird **im Original** gespeichert; nur der *Vergleich* normalisiert.
- Herkunft: V-2-Handover von Kevin (Issue #3).

### (7) `numeric_value` befüllen — `scalar_value()`
Nur wenn der Parameter in `{temperature, pressure, required_response_time}` liegt
UND der Wert exakt dem Regex entspricht:
`([+-]?\d+(?:\.\d+)?)\s*(°C|K|bar\(a\)|bar\(g\)|ms|s)` (Vollmatch).
Zusätzliche Guards: unmögliche Werte → `None` (`K < 0`, `s/ms/bar(a) < 0`,
`°C < -273.15`).
**Abstain-Fälle (→ `None`)**: fehlende Einheit (`80`), Näherung (`ca. 80 °C`),
Bereich (`20–80 °C`), Verneinung (`nicht 80 °C`), Komma-Dezimal (`1,000 °C`),
nicht unterstützte Einheit (`2 bar`, `2 %`, `20 ppm`). Siehe
`test_supported_scalars_keep_units` / `test_ambiguous_or_unsupported_numbers_abstain`.
`value` (Text) bleibt immer die maßgebliche Angabe.

### (8) Konflikte
- Modell-gelieferte `conflicts` werden beim Bau von `ExtractionResult` validiert
  (`check_conflict_references` in `models.py`): Indizes verschieden, im Bereich,
  gleicher Parameter. Verstoß → `ValueError`
  (`test_invalid_conflict_links_are_rejected`).
- Danach **deterministische Ergänzung**: Für jeden Parameter mit ≥ 2
  *unterschiedlichen* `value`s, der noch nicht markiert ist, wird ein
  `ParameterConflict` mit Standard-`reason` angehängt
  (`test_distinct_process_states_are_preserved_and_block_single_value_rules`).
  Identische Mehrfach-Fakten erzeugen **keinen** Konflikt
  (`test_duplicate_identical_facts_are_not_conflicts`).

### (9) `unknowns` berechnen
`unknowns` = alle `ParameterName`-Werte, die **entweder gar nicht** in
`stated_facts` vorkommen **oder** in `conflicts` als unaufgelöst gelten.
→ Ein Parameter kann gleichzeitig Fakten haben **und** in `unknowns` stehen,
wenn er umstritten ist. `assumptions` bleibt immer `[]` (bewusst, siehe 10).

---

## 3. Provider (`ChatJSONProvider`)

- Spricht `POST {base}/chat/completions` einer OpenAI-kompatiblen API.
  `base = openai_base_url or https://api.openai.com/v1` (abschließender `/`
  entfernt). `follow_redirects=False` (Credential-Leak-Schutz).
- **JSON-Mode-Fallback:** erst mit `response_format={"type":"json_object"}`
  (`_post(..., json_mode=True)`). Antwortet der Endpunkt mit HTTP **400/422** und
  der Body erwähnt `response_format`/`json_object`/`json mode`
  (`_rejects_json_mode`), wird **ohne** `response_format` erneut gesendet. Für
  Endpunkte wie GWDG SAIA nötig; für OpenAI unverändert.
- **Fehler-Sanitisierung:** Timeouts/Verbindungsfehler →
  `ProviderError(retryable=True)`. HTTP ≠ 200 → `ProviderError`, `retryable` nur
  bei 408/429/≥500. Response-Body und Key tauchen **nie** in der Meldung auf
  (`test_http_errors_are_sanitized`).
- **Envelope-Prüfung:** `choices[0].message`; bei `refusal` oder
  `finish_reason != "stop"` → `ProviderError`. Leerer/kein `content` → `ProviderError`.

---

## 4. Retry-Logik (`extract`)

- Höchstens `1 + afs_max_retries` Provider-Calls (`afs_max_retries` Default 2,
  Range 0–5 in `config.py`).
- `ProviderError.retryable=False` (z. B. HTTP 401/400) → **sofort** `raise`, kein
  Retry (`test_auth_error_not_retried`).
- `ProviderError.retryable=True` und `ValueError` (Validierung) **teilen sich das
  Budget** (`test_retry_budget_shared_by_transport_and_validation_failures`).
- Nach einem Validierungsfehler wird der System-Prompt um einen
  Korrektur-Hinweis ergänzt. Der Hinweis nennt nur die Klasse `quote` oder
  `schema`, nicht die Rohantwort und keine Validierungseingaben.
- Backoff: `time.sleep(min(2**attempt, 4))` zwischen den Runden (in Tests
  gemonkeypatcht).
- Alle Runden erschöpft → `ExtractionError`. **Ein API-Fehler wird nie zu einem
  fachlichen Ergebnis.**

---

## 5. Konfiguration (`src/config.py`)

Benötigt für Live-Betrieb (`require_llm`): `OPENAI_API_KEY`, `OPENAI_MODEL`.
Optional: `OPENAI_BASE_URL` (OpenAI-kompatibler Endpunkt; darf **keine**
Credentials/Query/Fragment enthalten), `AFS_REQUEST_TIMEOUT_SECONDS` (Default 60),
`AFS_MAX_RETRIES` (Default 2). `.env` wird aus der Projektwurzel geladen; der Key
wird nie geloggt (`exclude`, `repr=False`, `hide_input_in_errors`).

Live-Lauf:
```bash
uv sync --locked
cp .env.example .env     # OPENAI_API_KEY, OPENAI_MODEL, ggf. OPENAI_BASE_URL
uv run --locked python -m scripts.smoke_llm
uv run --locked pytest -q
```

---

## 6. Fehlerdiagnose (Symptom → Ursache → Stelle)

| Symptom | Wahrscheinliche Ursache | Wo nachsehen |
|---|---|---|
| `ValueError: query must be a non-empty string.` | leere/Nicht-String-Eingabe | `extract()` Guard (1) |
| `ValueError: query exceeds 20000 characters.` | zu lange Eingabe | `MAX_QUERY_LENGTH` |
| `ConfigurationError: Missing runtime settings: …` | `.env` unvollständig | `Settings.require_llm` |
| `ProviderError: Model request failed (HTTP 401).` (nicht retrybar) | falscher/abgelaufener Key | Key prüfen; `_post`/Status-Check |
| `ProviderError: Model request failed (HTTP 404).` | falsche `OPENAI_BASE_URL` oder Modellpfad | Base-URL muss auf `…/v1` enden |
| wiederholt HTTP 400 trotz Fallback | Endpunkt lehnt `response_format` ab, aber Body nennt es **nicht** → Fallback greift nicht | `_rejects_json_mode` ggf. Trigger erweitern |
| `ExtractionError: Extraction failed after bounded attempts;` | Modell liefert dauerhaft ungültiges JSON / falsche Zitate | Modellwahl, `afs_max_retries` erhöhen; Prompt (2) |
| `ValueError: Fact value must be an exact original quote.` | Modell schreibt den Wert um oder zitiert Nicht-Vorhandenes | Regel (5); ggf. ist `value != input_quote` |
| korrektes Zitat wird trotzdem abgelehnt | Unterschied, den die Normalisierung **nicht** glättet (z. B. echtes Satzzeichen) | `_QUOTE_TRANSLATION` in `models.py` (6) |
| `numeric_value` unerwartet `None` | Wert nicht exakt scalar/unit, Komma statt Punkt, Näherung, Bereich | `scalar_value` Regex + Guards (7) |
| `numeric_value` unerwartet gesetzt | sollte nach Design nicht möglich sein; Regex zu großzügig? | `scalar_value` Regex (7) |
| Parameter steht in `unknowns` trotz Fakt | Parameter ist konflikt-behaftet | `unresolved`-Berechnung (9) |
| erwarteter Konflikt fehlt | Werte identisch → kein Konflikt by design | Konflikt-Ergänzung (8) |
| `ValueError` bei Konflikt-Indizes | Modell liefert ungültige `fact_indices` | `check_conflict_references` in `models.py` |
| JSON mit Codefence schlägt fehl | sehr ungewöhnliches Format | `_extract_json_object` (4) |

**Grundregel beim Reverse-Engineering:** Zuerst klären, *welcher* Fehlertyp
auftritt — `ValueError` (Eingabe/Validierung, deterministisch, reproduzierbar
offline), `ProviderError` (Netz/HTTP/Envelope, Endpunkt-abhängig),
`ConfigurationError` (`.env`), `ExtractionError` (Retries erschöpft). Danach
anhand der Tabelle die zuständige Stelle lokalisieren. Die offline reproduzierbaren
Pfade sind mit `FakeProvider` in `tests/test_extraction.py` und den
stdlib-Logiktests in `tests/test_pure_logic_offline.py` abgedeckt.

---

## 7. Testabdeckung

- `tests/test_extraction.py` — End-to-end mit `FakeProvider`: Extraktion, Abstain,
  Negation/Unsicherheit, Prozesszustände/Konflikte, ungültige Konfliktlinks,
  Duplikate, Eingabe-Guards, irrelevanter Text, Retry-/Auth-Verhalten,
  Fenced/Prosa-JSON, Scalar-Parser-Parametrik.
- `tests/test_provider.py` — HTTP-Vertrag, Fehler-Sanitisierung, Timeout,
  ungültige/abgelehnte Envelopes.
- `tests/test_verify_quotes.py` — Darstellungstoleranz + echte Fehlzitate.
- `tests/test_pure_logic_offline.py` — stdlib-only, läuft ohne pydantic/httpx:
  Normalisierung + Scalar-Entscheidung gegen den echten Quellcode.
- `tests/test_parameter_contract.py`, `tests/test_foundation_models.py` —
  Vertrags-/Modellgrenzen.

> Stand der Ausführung: Die stdlib-Logiktests sind grün ausgeführt. Die
> pydantic-abhängige Vollsuite und der Live-LLM-Lauf sind in einer Umgebung mit
> Netzzugriff zu bestätigen (siehe Abschnitt 5 und PR-Checkliste).
