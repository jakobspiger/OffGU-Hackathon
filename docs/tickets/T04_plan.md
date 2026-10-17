# T04 — Vektor-Index und Retrieval · Umsetzungsplan

> Basiert auf `T04_analysis.md`. Ziel: reproduzierbarer lokaler **Vektor-Index**
> + `retrieve(query, k) -> list[Evidence]` (Contract `Retriever`), mit
> deterministischem lexikalischem Fallback ohne Embedding-Endpoint.
> **Kein** Few-Shot (T05), **keine** Regel-Logik (T03), **keine** LLM-Analyse,
> **keine** UI. `src/models.py` bleibt Jakobs.

## Zerlegung in Arbeitspakete (AP0–AP7)

### AP0 — Embedding-Konfiguration & Modus-Entscheidung
- Modus aus `Settings()` ableiten:
  - **vector** wenn `afs_embedding_model` **und** (`openai_api_key`+evtl.
    `openai_base_url`) gesetzt sind.
  - **lexical** sonst (deterministischer Fallback, kein Netz).
- Modus wird im Index-`manifest.json` und im Retrieval-Ergebnis-Log vermerkt.

### AP1 — Embedding-Client (`src/knowledge/embedding.py`, neu)
- `embed_texts(texts: list[str], settings) -> list[list[float]]` gegen einen
  **OpenAI-kompatiblen `/embeddings`-Endpoint** (httpx, Bearer-Key, Timeout/
  Retry — gleiches Muster wie T06 `provider.py`, aber **eigene** Datei; T06
  nicht ändern).
- Saubere Fehler: `RetrievalError` (aus `src.errors`) bei Netzwerk-/API-Fehler;
  Key/Secret nie loggen.
- Testbar via injizierbarem httpx-Transport (Mock) — kein echter Call in Tests.

### AP2 — Index-Erweiterung (`scripts/build_index.py`)
- **Additiv** zum bestehenden T02-Build: nach `evidence.jsonl` einen
  **Embedding-Index** erzeugen.
  - **vector-Modus:** `embed_texts` über jeden Evidence-`text`; schreibe
    `data/index/embeddings.jsonl` (je Zeile `{evidence_id, vector:[...]}`) +
    `embedding_meta.json` (`model`, `dim`, `mode`, UTC) — **keine Secrets**.
  - **lexical-Modus:** kein API-Call; `embeddings.jsonl` wird **nicht** erzeugt,
    `embedding_meta.json` vermerkt `mode="lexical"`. Retrieval baut den
    lexikalischen Index zur Laufzeit aus `evidence.jsonl`.
- `manifest.json` um `retrieval_mode` + Embedding-Modellname (ohne Key) ergänzen.
- Bestehende T02-Ausgaben/Verhalten unverändert (reiner Zusatz).

### AP3 — Retrieval-Kern (`src/knowledge/retrieval.py`)
- `retrieve(query, k=8) -> list[Evidence]` — Signatur/Input-Validierung aus dem
  Stub **unverändert** übernehmen (query non-empty; `type(k) is int`, 1≤k≤50).
- Ablauf:
  1. Index laden (`evidence.jsonl` → `Evidence`-Objekte; `embeddings.jsonl` wenn
     vorhanden). Fehlt der Index → `RetrievalError` (klar, nicht
     `ComponentNotReadyError`).
  2. **vector:** Query einbetten (`embed_texts([query])`), Kosinus-Ähnlichkeit in
     reinem Python gegen alle Evidence-Vektoren.
  3. **lexical:** deterministischer Score (Token-Overlap/TF-artig,
     case-insensitiv, unicode-normalisiert analog V-2) gegen `text`.
  4. **Quellenrang-Gewichtung:** `purpose="business_context"` (S05/S06) wird
     abgewertet (klein, nicht 0 → bleibt zitierbarer Kontext, nie als
     Leistungsbeleg oben). Rang aus `purpose`/`kind`.
  5. Top-`k` nach absteigendem Score; jede zurückgegebene `Evidence` bekommt
     `score` gesetzt (Trefferinfo, Abnahmekriterium 2). `evidence_id`/Felder
     unverändert.
- Index wird **gecached** (einmal laden pro Prozess), damit die UI/Batch nicht
  bei jeder Query neu von Platte liest.

### AP4 — Scoring/Utils (`src/knowledge/retrieval.py`, interne Helfer)
- `_cosine(a, b)` reines Python (kein numpy).
- `_lexical_score(query, text)` deterministisch, unicode-/case-robust.
- `_rank_weight(evidence)` aus `purpose` (technical > research > business_context).
- Alles pure-logic → ohne pydantic/httpx testbar.

### AP5 — Tests (`tests/test_retrieval.py`)
- `test_retrieve_rejects_bad_input` (leere query, k außerhalb 1..50, k nicht int).
- `test_missing_index_raises_retrieval_error`.
- `test_cosine_and_lexical_scoring_pure` (bekannte Vektoren/Texte → erwartete
  Ordnung).
- `test_business_context_downranked` (S05/S06 nicht vor S01-Technik bei
  technischer Query).
- `test_nir_mir_fluorescence_queries_hit_right_passages` — auf **Fixture-Evidenz**
  (synthetische S01/S02/XLSX-Chunks mit den echten Stichworten), prüft, dass die
  fachlich passende Passage vorn liegt (Abnahmekriterium 5).
- `test_retrieve_never_returns_reference_or_h_text` — Index enthält nur
  `evidence.jsonl`; ein Fixture mit untergeschobenem H-Text/Reference wird nicht
  geliefert (Abnahmekriterium 6).
- `test_returned_evidence_has_score_and_valid_fields` (Trefferinfo gesetzt;
  S06 page=None bleibt).
- `test_vector_mode_uses_embeddings_via_mock_transport` — API-Pfad mit
  gemocktem httpx-Transport (kein echter Call), `importorskip` für httpx/pydantic.
- `test_retrieve_matches_retriever_protocol`.
- Lib-/pydantic-/httpx-abhängige Pfade via `importorskip`; Pure-Logik auf stdlib.

### AP6 — Doku
- `data/index/README` bzw. Abschnitt in `README.md`: Embedding-Konfiguration
  (`AFS_EMBEDDING_MODEL`, `OPENAI_BASE_URL`, Key), beide Modi, Index-Bau-Befehl,
  reproduzierbarer Lauf, Grenzen (Fallback). Quellenrang-Verhalten dokumentieren.
- Schnittstellen-Notiz an T08 (Jakob): `retrieve` liefert Evidence mit `score`,
  absteigend sortiert, stabile `evidence_id`; business_context abgewertet.

### AP7 — Integrations-Check mit anderen Tickets
- Verifizieren, dass `retrieve`-Ausgabe mit **T08** (`synthesis.py` konsumiert
  `list[Evidence]`, nutzt `evidence_ids`/`source_refs`) kompatibel ist
  (Felder/Score/Reihenfolge). Soweit ohne pydantic möglich: Logik-Check; voller
  Test lokal bei Kevin.

## Offene Entscheidungen für Kevin

1. **Hybrid vector+lexical mit Auto-Modus (empfohlen)** — oder strikt nur Vektor
   (dann ist CI/Jury ohne Embedding-Endpoint nicht lauffähig)? Empfehlung:
   Hybrid, Default = vector wenn konfiguriert, sonst lexical.
2. **Embedding-Endpoint:** Habt ihr an eurem lokalen/GWDG-LLM ein
   **Embedding-Modell** (OpenAI-kompatibles `/embeddings`)? Wenn ja: Modellname
   für `.env.example`-Doku. Wenn nein: Fallback ist der reale Default, Vektor-
   Modus bleibt optional/dokumentiert.
3. **business_context-Abwertung** statt Herausfiltern — ok? (S06 bleibt als
   Kontext zitierbar, nie als Leistungsbeleg.)

## Was du lokal testen musst (Kevins Umgebung)

- **Ohne Embedding-Endpoint (Minimum):**
  `uv sync --locked && uv run --locked pytest -q` → alle Retrieval-Tests grün
  (API-Pfad gemockt, lexical real). **Kein Key nötig.**
- **Mit Embedding-Endpoint (für echten Vektor-Modus):** `.env` mit
  `AFS_EMBEDDING_MODEL` + `OPENAI_BASE_URL`/`OPENAI_API_KEY`, dann
  `uv run --locked python scripts/build_index.py` (baut `embeddings.jsonl`) und
  eine Beispiel-Query über `retrieve` prüfen. Optional — nur wenn ihr ein
  Embedding-Modell habt.

## Definition of Done

- Vektor-Index reproduzierbar baubar (dokumentierte Embedding-Config) **+**
  lexikalischer Fallback.
- `retrieve(query,k)` liefert Evidence mit Quellen-ID/Seite/Text/**score**.
- business_context nicht als Leistungsbeleg; H/DOCX strukturell ausgeschlossen.
- NIR/MIR/Fluoreszenz-Checks liefern passende Passagen.
- Tests grün (pure-logic Sandbox; voller Lauf lokal). `src/models.py` unberührt.
