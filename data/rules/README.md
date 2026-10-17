# data/rules/ — deterministic rule matrix (T03)

Declarative, evidenced rules for the AFS spectroscopy assistant. The engine in
`src/knowledge/rules.py` is **generic**: it loads these YAML files and evaluates
them against an `ExtractionResult`. There is **no scenario-id branching** (no
`H0x` / `D0x`, no customer names, no scenario-specific conditionals) anywhere in
the data or the code.

## Files

- `rules_meta.yaml` — rule-set version and the **parameter-versioning gate**.
- `method_matrix.yaml` — sample-type → measurement-geometry candidates derived
  from the method comparison table (S01 Table 1, p.6, ingested as the XLSX
  transcription). Conditional hints only.
- `compatibility_rules.yaml` — the evidenced compatibility / caution rules.

## Outcome semantics (interface to T07/T08)

Every rule yields a `RuleFinding` with an `outcome` from exactly three values.
There is **no `approved`** outcome by design.

| outcome       | meaning                                                                 |
|---------------|-------------------------------------------------------------------------|
| `excluded`    | The stated situation rules a method / claim out on the cited evidence.  |
| `conditional` | Possible, but only after the stated condition is verified. Not a go.    |
| `unknown`     | A parameter the rule needs is missing/disputed → no decision, no go.    |

`unknown` is **never** a clearance. Missing data (a required parameter absent
from `stated_facts`, or present in `unknowns`) always produces `unknown`, never
a positive result. The engine applies this gate before it evaluates any
`when` conditions.

## Rule schema

Each rule in `method_matrix.yaml` / `compatibility_rules.yaml` is:

```yaml
- rule_id: stable_snake_case_id        # stable, unique
  when:                                 # AND-combined conditions
    - parameter: <ParameterName>        # must be one of the 16 ParameterName
      predicate: value_contains_any     # | parameter_present | parameter_absent
      keywords: ["..."]                 # for value_contains_any (case-insensitive)
      negate: false                     # optional
  requires: [<ParameterName>, ...]      # parameters that must be stated
  outcome: excluded | conditional | unknown
  reason: "why, in plain language"
  source_refs:                          # >= 1, real catalog pages
    - source_id: S01
      page: 6
```

### Predicates

- `value_contains_any` — the stated fact's raw quote `value` contains at least
  one keyword (case-insensitive substring match). No numeric comparison.
- `parameter_present` — a fact for this parameter exists in `stated_facts`.
- `parameter_absent` — no fact for this parameter exists in `stated_facts`
  (or it only appears in `unknowns`).

`negate: true` inverts the predicate result for that single condition.

## Design constraints (acceptance criteria)

- **Stable id + conditions + outcome + ≥1 source_ref** for every rule.
- **Qualitative stays qualitative.** The method table's
  sensitivity/selectivity/cost columns are `low/average/high` ratings. They may
  only be cited as qualitative words in a `reason`; they are never emitted as
  numbers or device specifications.
- **Nominal vs. fiber/instrument range are separate.** Nominal method ranges
  (NIR 780–2500 nm, MIR 4000–400 cm^-1) are never equated with the usable range
  of a concrete fiber or probe.
- **No invented sources.** Pages are cross-checked against
  `src.knowledge.catalog`. S06 has no page; S01–S05 require a 1-based page.
  XLSX ratings cite S01 Table 1 (p.6).

## Parameter-versioning gate

`rules_meta.yaml` carries `expected_parameter_names`: a verbatim copy of the 16
`ParameterName` literals (see `docs/parameters.md`). On load, the engine checks

```python
set(expected_parameter_names) == set(typing.get_args(src.models.ParameterName))
```

and raises `RuleConfigError` (a local subclass of `src.errors.AFSError`) listing
the missing/extra names if the sets differ. This makes a drifted parameter list
fail fast instead of letting rules match silently into the void.

**Interface note for T06 (Jakob):** a dedicated `PARAMETER_VERSION` marker next
to `ParameterName` in `src/models.py` (analogous to `extraction_version`) would
let T03 check against a version *number* instead of set equality. T03 does not
change `models.py` itself.

## T06 additive fields

The engine reads only `parameter`, `value` and `unknowns` from the extraction.
T06's additive fields (`ExtractedFact.numeric_value`,
`ExtractionResult.conflicts`) are read **optionally** (getattr-safe) and are
never required, because T06 is not merged yet. A required parameter that appears
in `conflicts` is treated as `unknown` ("scope disputed").
