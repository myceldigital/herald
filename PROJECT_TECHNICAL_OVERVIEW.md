# Herald — Project Technical Overview

## What It Is

Herald is a Python CLI tool that converts clinical practice guideline PDFs into queryable decision engines. Three-stage pipeline: **convert** (PDF → markdown), **parse** (markdown → decision tree JSON via LLM), **query** (deterministic tree traversal, no LLM needed).

Package name: `herald-cpg` (PyPI). Module name: `herald_cli`. Entry point: `herald`.

## Architecture

```
src/herald_cli/
├── __init__.py       # Version string (0.1.0)
├── cli.py            # Click CLI — groups: convert, parse, query, validate, diff, export
├── convert.py        # PDF → markdown via Microsoft markitdown
├── parse.py          # Markdown → decision tree JSON via Anthropic/OpenAI LLM
├── validate.py       # Verify parsed tree source_text against original markdown
├── query.py          # Deterministic query engine — traverses decision tree given patient profile
├── diff.py           # Compare two guideline versions, produce structured diff
└── export.py         # Export decision tree to FHIR PlanDefinition (CPG-on-FHIR)

tests/
├── test_convert.py   # Markdown normalization (5 tests)
├── test_cli.py       # CLI error handling (3 tests)
├── test_parse.py     # Schema models + chunk split/merge + requiredness demotion + reference validation
├── test_query.py     # Query engine + NLP patient parser + scoped field extraction/normalization
├── test_validate.py  # Source text verification (5 tests)
├── test_diff.py      # Guideline version diffing (21 tests)
└── test_export.py    # FHIR PlanDefinition export (40 tests)

examples/
├── synthetic_adhd_guideline.json   # Pre-parsed synthetic guideline for demo/testing
├── synthetic_adhd_guideline.md     # Source markdown for the synthetic guideline
└── demo.py                         # Example usage script
```

## Key Modules

### `query.py` — The Core Engine

- `QueryEngine`: Loads a decision tree, traverses it deterministically given a patient dict. Supports entry points, branching, sequence nodes, contraindication blocking, priority sorting.
- `MultiQueryEngine`: Queries multiple guidelines simultaneously with conflict detection.
- `parse_patient_description()`: NLP parser that converts natural language ("34F ADHD, comorbid anxiety") into structured patient dicts. Handles age/sex extraction, medical abbreviations, negation detection, vital signs, medication history, and guideline-driven dynamic field extraction via synonyms.
- `parse_csv_patients()`: Batch processing from CSV.
- Query extraction now tolerates `values: null` / `known_values: null` in parsed `patient_fields`.
- Condition matching now treats `any_match` with a scalar patient value plus a list of expected enum values as membership, which makes the engine more resilient to imperfect LLM condition encoding.
- Query-time field extraction is now diagnosis-first and scope-aware: Herald extracts the top-level diagnosis/context first, then limits additional extraction and missing-required reporting to fields used by relevant decisions instead of the entire merged guideline.
- Enum extraction now matches canonical values with underscores normalized to spaces (for example `bipolar_disorder` ↔ `bipolar disorder`), aligns derived enum values to guideline vocab (`adult` ↔ `young_adult` / `adults`, synonyms back to canonical enums like `attention deficit hyperactivity disorder` → `ADHD`), and treats composite values like `children_and_adolescents` as matching child/adolescent patients.
- Derived aliases now bridge common parse/runtime mismatches such as `age -> age_years`, `episode_type -> bipolar_episode_type`, and a targeted bipolar composite condition phrase (`bipolar disorder current episode mania`) when the query text makes that intent explicit.

### `cli.py` — User-Facing Command Layer

- Wraps expected runtime/data failures (`RuntimeError`, `ValueError`, `OSError`, JSON decode errors) as `click.ClickException`, so the CLI prints clean `Error: ...` messages instead of Python tracebacks.
- Manual CLI coverage now includes `--help`, `--version`, `convert`, `parse` missing-key failure path, `query`, `validate`, `diff`, `export`, batch query, audit logging, and multi-guideline query.

### `parse.py` — LLM Extraction

- Pydantic models: `GuidelineDecisionTree`, `DecisionNode`, `Condition`, `Recommendation`, `Branch`, `PatientField`, `GuidelineMeta`.
- Supports Anthropic (claude-sonnet-4-20250514 default) and OpenAI (gpt-4o default).
- `_validate_references()`: Ensures all branch `next_decision` IDs point to valid nodes.
- Provider dependency/install error strings now reference the correct package extras: `herald-cpg[anthropic]` and `herald-cpg[openai]`.
- Parsed trees now preserve `field_synonyms`, matching the documented schema and what `query.py` expects.
- The parser now strips common LLM wrapper text and extracts fenced/embedded JSON payloads before `json.loads()`.
- Default output budget for LLM parse calls is now `20000` tokens so large real-world guideline parses are less likely to truncate mid-JSON.
- Large guidelines now automatically switch to chunked parsing:
  - tries to narrow to a recommendations chapter when one is clearly present
  - splits by numbered subsection headings (fallback: markdown headings, then paragraph-size chunks)
  - sends each chunk with shared top-of-document metadata context
  - merges guideline metadata, patient fields, synonyms, and decisions deterministically
  - demotes `patient_fields.required` after merge when that requirement only came from a narrow subset of chunks, so subgroup-only requirements do not become whole-guideline required fields
  - renames conflicting decision IDs safely and validates references after merge
- Before schema validation, parse output is sanitized to clean up common LLM shape mistakes seen in real runs (for example `bool` fields incorrectly carrying `[true, false]` value arrays, or nullable recommendation string fields arriving as `null`).

### `convert.py` — PDF Conversion

- Uses Microsoft `markitdown`, then post-processes output with `_normalize_markdown()`.
- Normalization now strips embedded form-feed/page-break characters before collapsing whitespace so real PDF conversions do not leak `\f` artifacts into downstream parse input.

### `export.py` — FHIR Export

- Maps Herald schema → CPG-on-FHIR PlanDefinition.
- Decisions → `action[]`, conditions → `action.condition[]` (applicability), branches → `action.relatedAction[]`.
- Strips None/empty values via `_clean_none()`.

### `diff.py` — Version Comparison

- Compares two guideline trees: added/removed/modified nodes, metadata changes, patient field changes.
- `format_markdown()`: Produces markdown diff suitable for email distribution.

## Build & Test

```bash
pip install -e ".[dev]"        # Install with dev deps (pytest, ruff, pytest-cov)
ruff check src/ tests/         # Lint
pytest tests/ -v --tb=short    # Run tests (121 tests)
pytest tests/ --cov=herald_cli # Coverage report
```

## Workflow Discipline

- `workflow_state.md` tracks the active Planner-owned task packet, success criteria, and verification steps for non-trivial work.
- Real-system validation matters for this project because the highest-risk paths are CLI execution, PDF conversion fidelity, and LLM-backed parsing behavior against real guideline documents.

## Schema

Decision trees follow Herald Schema v0.1 (see `SCHEMA.md`). Every recommendation traces back to `source_section`, `source_page`, and `source_text` for auditability.

## Dependencies

- **click** — CLI framework
- **pydantic** — Schema validation
- **rich** — Terminal output formatting
- **markitdown** — PDF → markdown conversion (Microsoft)
- **anthropic** / **openai** — LLM providers for parse stage (optional)

## Known Issues

- Repo state: `Desktop/herald` has source files deleted from HEAD. Full project only in Downloads copies.
- `query.py` coverage is still relatively low for the full NLP extraction surface and multi-guideline behavior.
- Real WHO PDF conversion still includes repeated running headers/page numbers and some OCR-style spacing artifacts such as `E xecutive summar y`, even though form-feed control characters are now stripped.
- Multi-guideline queries return duplicate recommendations if equivalent guidelines are loaded more than once; no deduplication layer exists yet.
- After chunked parsing, the saved WHO mhGAP parse now contains 96 decision nodes and representative queries for anxiety, ADHD, bipolar mania, and canonical-phrase depression return recommendations. The main remaining limitation is extraction fidelity, not parser/runtime stability.
- Real-world large-guideline extraction still depends heavily on the model producing good local condition vocab. For example, some WHO diagnoses/age buckets were emitted in awkward canonical forms (`moderate_to_severe_depression`, `children_and_adolescents`) that required extra query normalization.
- Chunk merge now down-ranks subgroup-only required fields for future merged parses. A fresh WHO mhGAP rerun confirmed the effect in practice: global required fields dropped from 20 in the older merged JSON to 1 (`diagnosis`) in the rerun output, and old whole-guideline required flags such as `age_group`, `age_years`, `sex`, `childbearing_potential`, `phase`, `condition`, and `seizure_type` disappeared.
- Even with the merge demotion heuristic, some module-specific required fields can still remain noisy if the underlying LLM marks them required broadly across many chunks rather than only in one narrow subsection.
- The fully chunked WHO rerun currently requires more than five minutes for the complete 23-chunk pass. Under the current workflow rules, that means it must be treated as a long-running operation and discussed before retrying.
