# data/examples/ — few-shot development examples D01-D08 (T05)

Curated development scenarios used to calibrate the **tone and structure** of
the assistant's answers. The loader and selector live in
`src/knowledge/examples.py`.

## Purpose

- `dev_examples.yaml` holds the **eight** development cases D01-D08 from
  `materials/AFS_Examples_and_Reference.docx` (section 1), with the two worked
  reference answers for **D01 and D02** (section 2) taken verbatim.
- These examples show the expected answer **structure** (requirements, key
  unknowns, clarification questions, recommendation, measurement concept,
  spectral range, risks, feasibility plan, sources) and the **level of caution**
  (provisional, honest about unknowns, no invented figures).

## This is NOT citable technical evidence

- The examples are a **development reference**, separate from citable
  spectroscopy literature. Citable technical evidence lives in `data/index/`
  (`evidence.jsonl`), built by T02 from the S01-S06 sources.
- The selector reads **only** `data/examples/dev_examples.yaml`. It never reads
  `data/index/evidence.jsonl`, and the examples are never emitted as retrieval
  evidence or mixed into it.
- The D01/D02 worked answers are a **tone/structure template prepared by the
  organizers**, not independent proof of any method's performance. They must
  never be cited as evidence and **do not justify any technical performance
  claim**. Their `provenance` records this explicitly.

## Only real reference answers

- Exactly **D01 and D02** have a `reference_answer`. **D03-D08** have `null` — no
  answer is invented for them. `load_examples` enforces this on load and raises
  `ExampleConfigError` if it drifts.

## H01-H06 are excluded (three ways)

The final evaluation scenarios H01-H06 (in
`materials/customer_scenarios_for_final_evaluation.txt`) never appear here:

1. the contract regex `^D0[1-8]$` on `FewShotExample.example_id`
   (`src/models.py`) makes any `H0x`/`D09`/etc. id structurally impossible;
2. this file contains only D01-D08;
3. a test (`tests/test_examples.py`) forbids any `H0x` string in the file.

There is **no scenario-id branching** in the data or the code. Selection is a
generic lexical match over the example text; no customer names or per-scenario
conditionals exist anywhere.

## Selection and limit rules

`select_examples(query, k=2) -> list[FewShotExample]`
(the `src.contracts.ExampleSelector` adapter):

- **Default `k = 2`**, valid range **`1..8`** (8 = number of development cases).
  `query` must be a non-empty string; `k` must be an `int` in range (a `bool` is
  rejected). Otherwise `ValueError`.
- Ranking is **generic and deterministic**: lexical relevance (NFC + casefold +
  whitespace-normalized token overlap, pure Python) of the caller's `query`
  against each example's own `query` text.
- **Tie-break:** on an exact score tie, examples that **carry a
  `reference_answer`** (D01/D02, the calibration template) are preferred, then
  ordering is stable by `example_id`. This is a generic "has reference_answer"
  weighting, not scenario-id logic.

## Handover to T09 / T11 (Jakob)

- `select_examples` returns `list[FewShotExample]` (contract), with
  `reference_answer=None` where no worked answer exists, ordered by relevance.
- Integration into the prompts / synthesis (`src/engine/prompts.py`, T09/T11)
  is Jakob's; T05 does **not** modify those files. The handover format is the
  `FewShotExample` contract object. The `state.examples` field is already
  reserved; the selector docks onto it without changing `graph.py`/`prompts.py`.
- Reminder for integration: the D01/D02 worked answers are a **structure/tone
  model**, not independent evidence — do not cite them as a source.
