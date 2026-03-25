# Contributing To Herald

Herald sits at the boundary between software engineering and clinical logic. Good contributions can come from either side, but they need to preserve the project's core properties:

- deterministic query behavior
- auditable source traceability
- clear public documentation
- synthetic or properly licensed content only

## Getting Started

```bash
git clone https://github.com/myceldigital/herald.git
cd herald
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
```

## Highest-Impact Contributions

1. Real-world PDF conversion hardening for guideline layouts that currently degrade in markdown.
2. Parse quality improvements that increase source fidelity without hiding uncertainty.
3. Query engine improvements for deterministic clinical logic traversal.
4. Better exports and interoperability for CDS workflows.
5. New synthetic examples that demonstrate realistic, high-value clinical scenarios.
6. Public-facing docs that make the trust model and limits clearer.

## Where To Open What

- GitHub Discussions: questions, design discussion, workflow ideas, and "would Herald support this?" conversations.
- Bug report issue: reproducible breakage in parsing, querying, conversion, CI, packaging, or docs.
- Feature request issue: concrete proposed change to Herald behavior.
- Guideline-compatibility issue: a real public guideline that currently converts or parses badly and would be a good target for improvement.
- Private vulnerability reporting: anything security-sensitive. See `SECURITY.md`.

## Ground Rules

- Keep runtime querying deterministic.
- Do not hide provenance. If a recommendation loses source traceability, that is a regression.
- Do not ship copyrighted clinical content into the repo.
- Label all demo/example content clearly when it is synthetic.
- Prefer simple, inspectable data structures over clever abstractions.

## Testing

- Add or update tests for every behavior change.
- Prefer real examples and concrete decision trees over mocked behavior.
- If you add a new example guideline, add a targeted query test that proves it works.

## Code Style

- Python 3.10+
- type hints on new/edited functions
- `ruff` clean
- readable CLI output
- docs updated when the public behavior changes

## Clinical Accuracy And Safety Boundary

Herald is open source infrastructure for computable guidelines. It is not a substitute for clinical review. Contributions should make that boundary clearer, not blur it.
