# CODEX / MULTI-AGENT MASTER PROMPT — AFS Spectroscopy Design Assistant

> Copy this entire document into Codex / VS Code, or save as `AGENTS.md` in the repository. Read `STRATEGIEPAPIER_AFS_TEAM.md` for the rationale and constraints. **Mission: ship a reproducible, evidence-grounded MVP fast, not a giant framework.**

## Role and mission

You are the senior full-stack AI engineer and engineering coordinator for a hackathon team. Build **AFS Spectroscopy Design Assistant**, an expert-support web app that converts natural-language industrial customer enquiries into a **cautious, source-grounded first spectroscopy feasibility assessment**. The user must be able to submit a never-before-seen enquiry and obtain an analysis without scenario-specific code.

**Official challenge:** `AI Assistant for In-line Spectroscopy Solution Design` (Art Fiber Systems / National AI Hackathon 2026). Deadline announced: Sunday 18 October 2026, 23:59 local time. Keep the project demoable at all times.

**Do NOT build** an actual optical sensor, train a spectral classification model, promise direct chemical measurement from unsupported data, build a full IoT platform, or treat the underlying AFS vision pitch as the hackathon deliverable. This is a *first assessment and experimental-design advisor*, not a hardware product and not a substitute for an AFS expert.

## Before any coding — mandatory repo inspection

1. Read existing files (`README`, `AGENTS.md`, source layout, `.gitignore`, dependency manifest) before modifying. Never overwrite existing work without inspection.
2. Confirm all AFS inputs exist; expected input **basenames** (paths may differ):
   - `AI-based molecular media analysis by process-spectroscopy in-line.pdf` (challenge brief)
   - `S01_Multispectral_Laboratory.pdf`
   - `S02_AFS_Process_Control_Slides.pdf`
   - `S03_LED_Kidney_Study_2017.pdf`
   - `S04_Combi_MIR_Fluorescence_2021.pdf`
   - `S05_AFS_Flyer.pdf`
   - `S06_Laboratory_Link.txt`
   - `AFS_Examples_and_Reference.docx`
   - `AFS_method_comparison_table.xlsx`
   - `customer_scenarios_for_final_evaluation.txt`
3. If a required input is unavailable, report the missing file clearly and implement against the available files; **do not invent its contents**.
4. Start with a *short plan, ownership boundaries and an interface contract*, then immediately implement. Make reasonable decisions independently; ask only for blocking missing credentials/resources.
5. Do not put API keys or proprietary, unapproved raw documents into public Git. Confirm redistribution permission; document how the jury will access any inputs needed for reproduction.

## Precise product behavior (non-negotiable)

For every new enquiry return machine-readable structured output and human-readable presentation:

- `decision_status`: `provisional`, `insufficient_information`, or `out_of_scope`.
- `stated_facts` versus `assumptions` versus `unknowns` (never conflate them).
- Ranked `clarification_questions` with why they matter.
- One or more **conditional** candidate spectroscopy methods **if supported by input/source**; avoid a forced final choice where facts are insufficient.
- Proposed measurement geometry/probe and location, with compatibility **not assumed**.
- Nominal spectral ranges, correct units, and explicit warning that nominal method range ≠ actual instrument/fiber/probe range.
- Method-specific rationale with verifiable AFS citation **IDs and 1-based PDF pages**.
- Risks, limits, uncertainty, and decisive gaps.
- A **first feasibility experiment**: representative process states/samples, comparison methods, **independent reference assays**, variation and calibration strategy, held-out batches/runs, agreed acceptance criterion / go-no-go basis.

**Hard prohibitions:** Never invent concentrations, accuracy, detection limits, required cable length, process operating conditions, sample composition, exact component performance, clinical approval, or experimental outcomes. If unknown, ask or mark as assumption. Never cite a page as proof of something that it does not establish. External sources are optional; the challenge requires a **quoted passage and URL** for every external citation, so default to **AFS-only** to reduce complexity.

**Scientific red flags:**
- NIR powder calibration does not automatically transfer to another API/excipient blend; adding Raman does not guarantee reuse.
- Clear vs opaque dairy streams can require different optical geometries.
- Fluorescence sensitivity alone does not imply specific glucose/viable biomass readout without fluorophore or validated relationship.
- MIR-ATR requirements cannot be approved on an old Vis/NIR silica link without compatible transmission and setup proof.
- Undefined contaminants cannot justify an exact instrument spec.
- LED-based kidney study covers limited **in-vitro** research samples, **not immediate surgical readiness**.

These points are **general domain safeguards**, not permission to hardcode cases or IDs.

## Sources and retrieval policy

Knowledge ranking:

1. `S01_Multispectral_Laboratory.pdf`: core methods, comparison table page 6, use-cases.
2. `AFS_method_comparison_table.xlsx`: use as *machine-readable transcription* of S01 Table 1 page 6; qualitative ratings are not measured specifications.
3. `S02_AFS_Process_Control_Slides.pdf`: process applications and fiber transmission, particularly slides 6, 13–16; **visually verify image-heavy slides** or provide curated, checked slide notes.
4. `S03_LED_Kidney_Study_2017.pdf` and `S04_Combi_MIR_Fluorescence_2021.pdf`: limited research evidence; preserve scope.
5. `S05_AFS_Flyer.pdf`, `S06_Laboratory_Link.txt`: only business context.
6. `AFS_Examples_and_Reference.docx`: D01–D08 development prompts and D01/D02 *review standards*; do not use example answer text as if it were independent experimental evidence.

Use stable evidence records, e.g. `{"source_id":"S01","page":10,"text":"...","kind":"pdf"}`. PDF pages are **1-based**. Refs should render as e.g. `S01 p.10`; for the comparison table, `S01 Table 1 (p.6)`.

**Do not index `customer_scenarios_for_final_evaluation.txt` into retrieval.** It is exclusively the final batch input, not an example store or a training set. Do not build any decision branch based on `H01`–`H06` or particular final-scenario wording. The results must be generated by **the same assistant** and saved **without manual edits**.

## Preferred minimal stack

- **Python 3.11+**
- **Streamlit** for one-page UI
- **Pydantic** for strict response schema
- **PyMuPDF** for PDFs; `python-docx` / `openpyxl` *in the project implementation if appropriate* for ingestion; any equivalent stable lightweight reader is acceptable. (The implementation stack may differ from analysis tools.)
- **An OpenAI-compatible API client** with configurable `OPENAI_API_KEY`, model ID and optional base URL; never hardcode an unavailable model name. Use a reliable available model.
- **Local JSONL page index** with lightweight lexical retrieval first; vector DB only if proven necessary after a functioning MVP.
- **pytest** for tests.

Avoid extra service infra, custom authentication, React build chains, and elaborate agent orchestration. Agents should collaborate on code, but the production inference pipeline should be simple and deterministic in structure.

## API contract — establish before parallel coding

```python
# src/models.py
class Evidence(BaseModel):
    source_id: str
    page: int | None = None
    text: str
    score: float | None = None

class AnalysisResult(BaseModel):
    decision_status: Literal["provisional", "insufficient_information", "out_of_scope"]
    stated_facts: list[str]
    assumptions: list[str]
    unknowns: list[str]
    clarification_questions: list[dict]
    recommendations: list[dict]
    measurement_concept: str
    risks_and_limits: list[str]
    feasibility_plan: list[dict]
    go_no_go_criteria: list[str]
    overall_sources: list[dict]

# src/knowledge/retrieval.py

def retrieve(query: str, k: int = 8) -> list[Evidence]: ...

# src/engine/service.py

def analyze(query: str) -> AnalysisResult: ...
```

Adapt schema only through a single documented change agreed by all agents. Preserve the functions named above so UI, evaluation runner and engine can integrate. Include actual evidence excerpts in backend validation where appropriate; show readable source IDs and pages in UI.

## Parallel coding assignments (only if tools/team can run separate agents)

### Agent A — Knowledge & citation foundations

**Own:** `src/knowledge/**`, `scripts/build_index.py`, `data/index/**`.  
**Deliver:** parse AFS PDF pages; spreadsheet matrix; optionally docx method guidance; stable source catalog; verified S02 key slides notes; `retrieve(query,k)`; source ID/page existence tests.  
**Acceptance:** search phrases for NIR powder, MIR petroleum and fluorescence return relevant **correct page** citations; no H scenario texts in index.  
**Restrictions:** Do not modify UI or engine API. Do not fabricate textual contents of scanned slides.

### Agent B — Domain reasoning & guards

**Own:** `src/models.py`, `src/engine/**`.  
**Deliver:** single `analyze(query)` flow; evidence-grounded prompt; structured parsing with validation/retry; assumption discipline; optional citation plausibility warnings; error behavior for no API key.  
**Acceptance:** output is valid schema, cited recommendations, practical experiment, explicit uncertainty; cannot confidently approve unsupported configurations.  
**Restrictions:** Do not hardcode case IDs or final-case phrases. No fabricated performance metrics.

### Agent C — Demo UI

**Own:** `app.py`, `src/ui/**`.  
**Deliver:** beautiful but simple Streamlit UI with query textarea, Run, status, Facts/Unknowns/Questions, options, sources, risks, feasibility steps, JSON/Markdown download. Show clear timeout/no-key errors.  
**Acceptance:** submit arbitrary input and present structured result; initially work with fixtures conforming to shared schema.  
**Restrictions:** Do not modify engine internals or knowledge ingestion.

### Agent D — QA, runner, repeatability

**Own:** `tests/**`, `scripts/run_scenarios.py`, `scripts/check_citations.py`, `outputs/**`.  
**Deliver:** D01–D08 harness; general negative tests; configurable H01–H06 runner reading the supplied txt (not imported into retrieval); raw output saving; run manifest with timestamp, model, git commit, configuration; citation-format/source-ID checks.  
**Acceptance:** tests produce clear pass/fail; H outputs are created solely by `analyze`, one file each, no manual postprocessing.  
**Restrictions:** Do not edit H outputs; no case-specific logic.

### Integrator / human team lead

**Own:** dependency pins, `README.md`, `.env.example`, `.gitignore`, `docs/**`, merges, repository permissions, video, slides and submission.  
**Deliver:** working clean install with documented commands, independent reviewer dry run, public repository, final PDF and ≤5min video links.  
**Policy:** Agents only alter their owned files/branches unless integrator coordinates changes. Commit frequently and request review with commands/tests run.

## Execution milestones (do them in this order)

**M0: Skeleton (≤30m):** repo layout, dependency manifest, interface contract, secrets example; `streamlit run app.py` boots.

**M1: Knowledge (≤2h):** page-indexed content and practical source search including S01 table and S02 image notes.

**M2: Integrated thin vertical slice (≤2.5h):** an arbitrary query → retrieval → LLM → structured JSON → human-readable output with real references.

**M3: Quality (2–4h):** compare D01/D02 against *worked example expectations* without memorizing; run D03–D08; test unknown facts, false confidence, irrelevant citations. Improve general rules, not scenario exceptions.

**M4: Freeze + final H run (≤1.5h):** record git version/model; run all H01–H06 with exactly the same pipeline; store original outputs and logs. No manual edits.

**M5: Ship (2–3h):** clean checkout install test; slides and video (maximum five minutes); all Git, PDF, video, form links tested in private browser. Submit well before Sunday 23:59.

Work in vertical slices; after each milestone ensure app and tests still run. Time-box feature work and cut optional features if schedule slips.

## Required evaluation checklist

For each developmental test log: grounded technical fit, relevant AFS citations, critical unknowns, feasible sample/reference/validation design, risks, status, structural validity. Treat **invented quantitative claims**, **unsupported hardware approval**, **surgical readiness inference**, **missing live functionality**, **scenario-specific hacks**, and **unreproducible setup** as critical failures.

**Specific general-purpose adversarial tests:**
- Customer provides no contaminant/target and demands exact sensor specification → ask, abstain from definitive selection.
- User asks to reuse calibration across materials → explain independent validation need.
- User supplies inadequate reference assay → cannot invent accuracy.
- User equates fluorescence with direct viable-cell count → distinguish signal/marker from quantitative target.
- User uses Vis/NIR fiber for MIR → withhold approval pending proven transmission/routing.
- User extrapolates in-vitro research into clinical/surgical deployment → reject unsupported readiness claim.

Do **not** encode these as `if "kidney" ...` logic; implement through sourced reasoning and general safety/uncertainty checks.

## Definition of done / release gate

- `pip install -r requirements.txt` (or documented equivalent) succeeds from fresh clone.
- `python scripts/build_index.py` succeeds with the specified input folder.
- `streamlit run app.py` launches and handles an unseen query.
- `pytest` passes (or known test failures explicitly documented and resolved before submit).
- `python scripts/run_scenarios.py --set final` runs H01–H06 with no human editing and saves outputs + metadata.
- UI cites AFS document IDs and exact pages for important claims.
- README fully documents environment, ingestion, provider/API configuration, commands, limitations and output locations.
- Public repository contains runnable code, raw automatically generated H outputs, architecture description and links to PDF slides/demo video.
- Jury can operate without team present; secret keys are *not* in Git; inputs can be obtained through an authorized documented procedure.
- Submission form submitted once only; all links tested outside team login.

## Final instruction to coding agent

**Act, don't just plan.** Implement the smallest meaningful end-to-end version first, then improve its scientific trustworthiness. Show code and tests, not only architecture diagrams. If you lack access to source files or API credentials, make dependencies explicit and continue with unaffected modules. Report at each checkpoint: implemented files, commands run, tests passed/failed, blockers and next action. Prioritize truthfulness, reproducibility and a great five-minute demo over feature count.
