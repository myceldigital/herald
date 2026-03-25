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
├── test_convert.py   # Markdown normalization (4 tests)
├── test_parse.py     # Schema models + reference validation (8 tests)
├── test_query.py     # Query engine + NLP patient parser (20 tests)
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

### `parse.py` — LLM Extraction

- Pydantic models: `GuidelineDecisionTree`, `DecisionNode`, `Condition`, `Recommendation`, `Branch`, `PatientField`, `GuidelineMeta`.
- Supports Anthropic (claude-sonnet-4-20250514 default) and OpenAI (gpt-4o default).
- `_validate_references()`: Ensures all branch `next_decision` IDs point to valid nodes.

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
pytest tests/ -v --tb=short    # Run tests (98 tests)
pytest tests/ --cov=herald_cli # Coverage report
```

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
- Coverage: `cli.py` at 0% (no CLI integration tests). `query.py` at 47% — many extractors and batch/multi-engine paths uncovered.
