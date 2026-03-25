# Workflow State

## Current Role

Judge

## Active Objective

Completed: reran the full WHO chunked parse with an explicitly approved longer-than-5-minute runtime budget, then validated and summarized the output quality.

## Task Packet

1. Implement chunking strategy for large guidelines:
   - Detect large markdown inputs that should not be parsed in one monolithic LLM call.
   - Split recommendation-heavy documents into section/module chunks using headings and safe fallbacks.
2. Implement deterministic merge:
   - Merge chunk-level metadata, patient fields, field synonyms, and decisions.
   - Handle duplicate decision IDs safely and keep branch references valid.
3. Add regression coverage:
   - Unit-test chunk splitting, merge behavior, and chunked parse orchestration without live API calls.
4. Rerun the WHO test:
   - Parse the WHO guideline with the new chunked strategy.
   - Validate fidelity and run representative WHO queries.
5. Judge the outcome:
   - Distinguish runtime bugs from remaining extraction-quality limitations.
   - Update `PROJECT_TECHNICAL_OVERVIEW.md` and `CHANGES_LOG.md`.

## Success Criteria

- Large markdown inputs are parsed via chunking automatically.
- Chunk merge preserves valid schema output and branch references.
- New tests cover chunk split/merge behavior and pass locally.
- WHO parse completes under the new strategy and yields materially better completeness/fidelity than the prior single-pass run.
- Any code changes are accompanied by updates to `PROJECT_TECHNICAL_OVERVIEW.md` and `CHANGES_LOG.md`.

## Verification Plan

- `python3 -m pytest tests/test_parse.py tests/test_query.py tests/test_cli.py tests/test_convert.py -q`
- `python3 -m ruff check src tests`
- `herald parse /tmp/who_mhgap_normalized.md -o /tmp/who_mhgap_chunked.json`
- `herald validate /tmp/who_mhgap_chunked.json --source /tmp/who_mhgap_normalized.md`
- Representative WHO queries against the chunked parse output

## Judge Outcome

- `stop`: the full WHO chunked parse completed successfully and was evaluated.
- Output scale improved materially versus the earlier single-pass parse (96 decision nodes instead of 14), and the saved parse metadata confirms `strategy = chunked` with `chunk_count = 23`.
- Remaining limitations are extraction-quality issues in the merged WHO tree (many partial citation matches and noisy/over-required patient fields), not parser runtime stability.
