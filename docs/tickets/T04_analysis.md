# T04 — Vektor-Index und Retrieval · Deep-Dive-Analyse

> Branch: `feat/t04-vector-retrieval` (von aktuellem `main`) · Verantwortlich: Kevin
> Analyse **vor** der Umsetzung. Grundlage für `T04_plan.md`.

## 1. Was T04 verlangt (Abnahmekriterien, wörtlich)

- [ ] Ein lokaler **Vektor-Index** ist mit dokumentierter Embedding-Konfiguration
      reproduzierbar baubar.
- [ ] `retrieve(query, k)` liefert `Evidence` mit Quellen-ID, Seite, Text und
      **Trefferinformation** (= `score`).
- [ ] S01–S06 werden gemäß Inhalt und **Quellenrang** behandelt; S06 ist keine
      erfundene PDF-Seite.
- [ ] Unternehmenskontext (S05/S06) wird **nicht** als technischer
      Leistungsbeleg angeboten.
- [ ] Retrieval-Checks für **NIR, MIR, Fluoreszenz** liefern fachlich passende
      Passagen.
- [ ] Finale Szenarien (H01–H06) und Entwicklungsantworten (DOCX/D01–D08) sind
      **nicht** im fachlichen Evidenzindex.

**Dateibereich:** `src/knowledge/retrieval.py`, `scripts/build_index.py`,
`data/index/` · **Abhängigkeit:** T02.
**Kollision:** Überschneidung mit T02 bei `build_index.py` — beide gehören
Kevin, kein Konflikt. Jakob (T08) nutzt die `retrieve`-Schnittstelle; Änderungen
an Evidence/Embedding-Config/Dependencies mit Jakob abstimmen.

## 2. Aktueller Stand (gemergt auf `main`)

- **T04-Stub** (`src/knowledge/retrieval.py`, von T01):
  ```python
  def retrieve(query: str, k: int = 8) -> list[Evidence]:
      # ValueError bei leerer query / k nicht in 1..50
      raise ComponentNotReadyError("Knowledge retrieval is not implemented yet (T02-T04).")
  ```
  → T04 ersetzt den `ComponentNotReadyError`-Teil durch echtes Retrieval.
  **Signatur + Input-Validierung (query non-empty, 1≤k≤50) bleiben exakt.**
- **Contract** (`src/contracts.py`): `Retriever.__call__(query, k=8) -> list[Evidence]`.
- **T02 liefert den Korpus:** `scripts/build_index.py` schreibt
  `data/index/evidence.jsonl` (nur echte `Evidence`: S01–S04 Text, S02 Notes,
  XLSX, S05/S06 business_context), `reference_records.jsonl` (BRIEF+DOCX,
  **getrennt**), `catalog.json`, `manifest.json`. H01–H06 sind per
  `INDEXABLE_SOURCES`-Allowlist **nie** drin.
- **Evidence-Felder** (T01-Vertrag, relevant für Retrieval-Ausgabe):
  `source_id, page, evidence_id, text, kind, purpose, origin_source_id,
  review_status, review_note, score` (score optional, endlich).
- **T08 (Jakob, Branch `feat/t08-solution-synthesis`)** konsumiert
  `list[Evidence]` von `retrieve` und nutzt `evidence_ids` + `source_refs` für
  die Synthese. → `retrieve` muss stabile `evidence_id`s und sinnvolle `score`s
  liefern; Reihenfolge nach Relevanz.

## 3. Embedding-/Vektor-Infrastruktur — was da ist

- **T01-Settings** (`src/config.py`): `afs_embedding_model: str | None`,
  `afs_index_dir`, `afs_retrieval_k=8` (1..50), plus
  `openai_api_key/openai_model/openai_base_url` (OpenAI-kompatibel).
  → Der vorgesehene Weg ist ein **OpenAI-kompatibler Embedding-Endpoint**
  (`/embeddings`), passend zu eurem lokalen/GWDG-LLM.
- **T06 `provider.py`** zeigt das httpx-Muster gegen
  `openai_base_url` + Bearer-Key (für `/chat/completions`). Analog gibt es
  `/embeddings`. **T06-Code nicht ändern**, aber dasselbe Muster
  (httpx, Settings, Timeout/Retry, Key-Handling) nachbauen.
- **Dependencies:** `pyproject.toml` hat **nur `httpx`** — **kein** numpy,
  faiss, sentence-transformers, rank-bm25. → Vektor-Suche muss **ohne schwere
  Libs** auskommen: Embeddings über den API-Endpoint holen, Vektoren als JSON/
  Liste persistieren, Kosinus-Ähnlichkeit in **reinem Python** rechnen (Korpus
  ist klein: ~S01 19 S. + S02 Notes + S03/S04 + XLSX + S05/S06 ≈ einige Dutzend
  Chunks → lineare Suche ist völlig ausreichend, keine ANN-Bibliothek nötig).

## 4. Der zentrale Zielkonflikt (muss der Plan auflösen)

- **Masterprompt/Strategiepapier:** „lexikalischer/BM25-artiger Index zuerst;
  Vektor-DB nur wenn nach funktionierendem MVP nachweislich nötig."
- **T04-Ticket + T01-Teamentscheidung (README/architecture):** fordern explizit
  einen **Vektor-Index** mit dokumentierter Embedding-Konfiguration.

**Auflösung (Vorschlag für den Plan):** T04 baut einen **Vektor-Index** (erfüllt
Ticket + Teamentscheidung) **mit einem deterministischen lexikalischen Fallback**:
- Ist ein Embedding-Modell/Key konfiguriert → echter Vektor-Index (API-Embeddings
  + Kosinus in Python).
- Ist **kein** Key/Modell gesetzt (z. B. CI, Jury ohne Embedding-Endpoint) →
  **lexikalischer Fallback** (TF-ähnlich, reines Python) über **denselben**
  `evidence.jsonl`-Korpus und **dieselbe** `retrieve`-API, klar als Modus
  gekennzeichnet.
Damit ist die Lösung reproduzierbar, demofähig ohne externe Abhängigkeit, und
erfüllt trotzdem die Vektor-Anforderung, wenn ein Endpoint vorhanden ist.
→ **Das ist die wichtigste offene Entscheidung für Kevin.**

## 5. Quellenrang & Filter (Abnahmekriterien 3–6)

- **Quellenrang** aus T02-Katalog/`purpose`: S01/XLSX = primär-technisch,
  S02 = Anwendung/Hardware (verified_note), S03/S04 = Forschung, S05/S06 =
  business_context. → Retrieval soll `purpose="business_context"` (S05/S06)
  **nicht** als technischen Treffer hochranken; optional als eigene Kategorie
  oder leicht abgewertet. **Kein Herausfiltern** (S06 bleibt zitierbar als
  Kontext), aber klar nicht als Leistungsbeleg.
- **H01–H06 / DOCX:** schon durch T02-Build **nicht** in `evidence.jsonl`.
  T04 liest nur `evidence.jsonl` → strukturell ausgeschlossen. Ein Test
  verifiziert, dass `retrieve` nie Reference-Records/H-Texte zurückgibt.
- **NIR/MIR/Fluoreszenz-Checks:** Query „NIR powder", „MIR petroleum water",
  „fluorescence" muss die fachlich passenden S01/S02/XLSX-Passagen auf
  vorderen Rängen liefern (Abnahmekriterium 5).

## 6. Risiken / offene Punkte

| Punkt | Umgang |
|---|---|
| pydantic/httpx/uv in Sandbox blockiert | Pure-Logik (Kosinus, lexikalischer Score, Ranking, Filter) mit Fixtures testen; API-Embedding-Pfad via `importorskip`/Mock-Transport. Realer Lauf + echter Index bei Kevin lokal. |
| Kein Embedding-Endpoint in CI/Jury | Lexikalischer Fallback über dieselbe API; Modus im Manifest dokumentiert. |
| Index nicht gebaut (data/index gitignored) | `retrieve` wirft klaren `RetrievalError` (aus `src.errors`) wenn Index fehlt — nicht `ComponentNotReadyError`. |
| Embedding-Call kostet Tokens/Netz | Embeddings **beim Index-Bau** einmal persistieren (nicht pro Query neu); nur die Query wird zur Laufzeit eingebettet. |
| T08 erwartet stabile evidence_id/score | `retrieve` gibt Evidence mit gesetztem `score` (Trefferinfo) und unveränderter `evidence_id` zurück; Reihenfolge = absteigender Score. |
| Vektor- vs. lexikalisch-Zielkonflikt | Hybrid mit dokumentiertem Default (siehe §4) — Kevin entscheidet. |

## 7. Braucht es LLM / API-Key? (für Kevins lokalen Test)

- **Für den echten Vektor-Modus: ja** — ein **Embedding-Endpoint**
  (`AFS_EMBEDDING_MODEL` + `OPENAI_BASE_URL`/`OPENAI_API_KEY`). Das ist euer
  lokales/GWDG-LLM, falls es ein Embedding-Modell anbietet.
- **Für Tests/CI/Demo ohne Key: nein** — der lexikalische Fallback läuft ohne
  Netz. Die automatischen Tests brauchen **keinen** Key (API-Pfad wird gemockt).
- Ich sage dir im Plan genau, was du lokal mit vs. ohne Embedding-Endpoint
  testen musst.
