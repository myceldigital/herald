# Changes Log

## 2026-03-25

- **Add**: automatic chunked parsing for large guidelines in `parse.py`. Herald now narrows to recommendation-heavy sections, splits by subsection headings, parses chunks independently, and merges metadata/fields/synonyms/decisions with deterministic ID conflict handling.
- **Fix**: chunk parsing now prefers the longest real recommendations chapter instead of the table-of-contents hit, and sanitizes common LLM schema-shape errors before validation (for example bool field value arrays and `null` recommendation strings). Rationale: the first real WHO chunked runs exposed TOC mis-detection and predictable malformed field shapes.
- **Fix**: query normalization now handles canonical enum values with underscores, pluralized guideline vocab (`adult` ↔ `adults`), null enum vocab lists, and composite values like `children_and_adolescents`. Rationale: the WHO chunked parse exposed valid recommendations that were being missed at query time due to vocab-shape mismatches.
- **Fix**: `parse.py` now preserves `field_synonyms`, extracts JSON from common LLM wrapper text, and raises the default LLM output budget to `20000` tokens. Rationale: the real WHO mhGAP parse exposed dropped synonyms, prose-before-JSON responses, and mid-JSON truncation.
- **Fix**: `query.py` now handles parsed `patient_fields` with `values: null` / `known_values: null`, and `any_match` now supports scalar membership against expected enum lists. Rationale: the WHO parse produced these shapes and they broke or suppressed valid queries.
- **Fix**: CLI commands now surface expected runtime/data failures as clean `Error: ...` messages instead of raw Python tracebacks. Added `tests/test_cli.py` to lock in missing-API-key and invalid-JSON behavior.
- **Fix**: `convert.py` now strips form-feed page-break characters from `markitdown` output before whitespace normalization. This reduces real-PDF ingestion noise from the WHO mhGAP guideline. Also corrected stale install hints from `guideline-as-code[...]` to `herald-cpg[...]`.
- **Add**: `workflow_state.md` — bounded Planner packet for a repo-wide quality pass using the WHO mhGAP guideline PDF; keeps execution and judging disciplined.
- **Fix**: `herald --version` crashed with `RuntimeError: 'herald_cli' is not installed`. Root cause: `@click.version_option()` inferred package name from module (`herald_cli`) instead of the installed package (`herald-cpg`). Fixed by passing `package_name="herald-cpg"`.

- **Add**: `tests/test_diff.py` — 21 tests covering `diff_guidelines()` (identical, added, removed, modified nodes/metadata/fields, complex mixed diffs) and `format_markdown()` (all output sections). `diff.py` now at 99% coverage.

- **Add**: `tests/test_export.py` — 40 tests covering `export_fhir()` (metadata mapping, action generation, full example guideline, empty input), `_build_action()` (citations, extensions, branches, sequences, conditions), `_build_conditions()` (all operators), `_build_inputs()` (with/without SNOMED codes), `_map_type()` (all type mappings), `_clean_none()` (nested cleaning, edge cases). `export.py` now at 100% coverage.

- **Add**: `PROJECT_TECHNICAL_OVERVIEW.md` and `CHANGES_LOG.md`.
