# Workflow State

## Current Role

Judge

## Active Objective

Rerun the live WHO chunked parse with the new merge heuristic and compare the new merged `patient_fields` against the old output to verify which inflated `required` flags disappear in practice.

## Task Packet

1. Verify live parse prerequisites:
   - Confirm the WHO normalized markdown input exists.
   - Confirm the Anthropic API environment is available for a real rerun.
2. Rerun the chunked WHO parse:
   - Write a fresh output file instead of overwriting the old JSON.
   - Allow a long runtime and monitor until completion.
3. Compare old vs new merged patient fields:
   - Diff required flags, added/removed fields, and any notable vocabulary/type shifts.
   - Highlight which previously inflated required fields disappeared.
4. Judge the outcome:
   - Distinguish merge-heuristic wins from remaining LLM extraction noise.
5. Update docs/logs/state with the rerun result.

## Success Criteria

- A fresh WHO chunked parse completes successfully with the new merge logic.
- We can enumerate which `patient_fields.required` flags changed between old and new outputs.
- The comparison shows real-world reduction of inflated required fields.
- Docs/logs reflect the rerun and comparison result.

## Verification Plan

- `python3 -m herald_cli.cli parse /tmp/who_mhgap_normalized.md -o /tmp/who_mhgap_chunked_rerun.json`
- Compare `/tmp/who_mhgap_chunked.json` vs `/tmp/who_mhgap_chunked_rerun.json` with a targeted Python diff
- If code changed during the turn, rerun targeted tests/lint

## Judge Outcome

- `stop`: the live WHO mhGAP chunked rerun completed successfully with the new merge heuristic.
- Rerun output: `/tmp/who_mhgap_chunked_rerun.json`, `strategy=chunked`, `chunk_count=23`, `94` decision nodes.
- Old merged WHO output had `95` patient fields and `20` globally required fields; the rerun has `78` patient fields and only `1` globally required field (`diagnosis`).
- Required flags that disappeared in practice include `age_group`, `age_years`, `benzodiazepine_response`, `childbearing_potential`, `condition`, `parental_mental_health_condition`, `patient_type`, `phase`, `seizure_type`, `sex`, and `use_pattern`.
- Runtime spot-checks against the rerun output showed materially cleaner query output with no old cross-module missing-required noise on representative anxiety and bipolar mania queries.
