# Changes Log

## 2026-03-25

- **Fix**: `herald --version` crashed with `RuntimeError: 'herald_cli' is not installed`. Root cause: `@click.version_option()` inferred package name from module (`herald_cli`) instead of the installed package (`herald-cpg`). Fixed by passing `package_name="herald-cpg"`.

- **Add**: `tests/test_diff.py` — 21 tests covering `diff_guidelines()` (identical, added, removed, modified nodes/metadata/fields, complex mixed diffs) and `format_markdown()` (all output sections). `diff.py` now at 99% coverage.

- **Add**: `tests/test_export.py` — 40 tests covering `export_fhir()` (metadata mapping, action generation, full example guideline, empty input), `_build_action()` (citations, extensions, branches, sequences, conditions), `_build_conditions()` (all operators), `_build_inputs()` (with/without SNOMED codes), `_map_type()` (all type mappings), `_clean_none()` (nested cleaning, edge cases). `export.py` now at 100% coverage.

- **Add**: `PROJECT_TECHNICAL_OVERVIEW.md` and `CHANGES_LOG.md`.
