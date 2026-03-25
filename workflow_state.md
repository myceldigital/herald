# Workflow State

## Current Role

Judge

## Active Objective

Refresh Herald's repo-facing presentation so the README and supporting docs clearly communicate the real shipped product, trust model, and highest-value use cases, and add a stronger acute-care demo asset that matches the thesis.

## Task Packet

1. Rewrite the repo front door:
   - Replace the README top section with a stronger product pitch, 30-second demo, trust model, serious use cases, current feature inventory, and explicit limits.
   - Remove shipped-vs-roadmap contradictions (for example FHIR export already exists).
2. Tighten supporting public docs:
   - Update `docs/adding_your_own.md`, `docs/supported_guidelines.md`, and `CONTRIBUTING.md` so they reinforce the README and reduce ambiguity for visitors.
   - Refresh package metadata in `pyproject.toml` where it affects public discovery.
3. Add a stronger demo artifact:
   - Create a synthetic acute-care guideline example that demonstrates the "3am citable answer" story.
   - Add a targeted test to ensure the example produces the expected recommendation path.
4. Update project records and verify:
   - Update `PROJECT_TECHNICAL_OVERVIEW.md` and `CHANGES_LOG.md`.
   - Run targeted lint/tests on the touched files.

## Success Criteria

- The README clearly explains what Herald is, why it is different from ChatGPT, why people should trust it, who it is for, and what ships today.
- Public docs no longer contradict the current CLI surface.
- The repo includes an acute-care example that makes the core value proposition obvious.
- Project overview/log/state reflect the documentation/demo refresh.
- Targeted tests and lint pass for touched files.

## Verification Plan

- `pytest tests/test_query.py -q`
- `ruff check README.md docs/ src/ tests/`
- Read lints for touched files after edits

## Judge Outcome

- `stop`: the repo-surface refresh landed cleanly and meets the bounded packet.
- `README.md` now leads with the deterministic trust model, stronger acute-care demo, shipped feature inventory, and clearer boundaries.
- GitHub repo metadata now matches the new positioning more closely via an updated description and broader discovery topics.
- `docs/adding_your_own.md`, `docs/supported_guidelines.md`, `CONTRIBUTING.md`, and `pyproject.toml` now align with the actual product surface and public positioning.
- A new shipped acute-care example was added in `examples/synthetic_meningitis_guideline.{md,json}` and the demo script now showcases both acute-care and chronic-care paths.
- Targeted verification passed: `pytest tests/test_query.py -q`, `ruff check src/ tests/`, and `PYTHONPATH=src python3 examples/demo.py`.
