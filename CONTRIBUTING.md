# Contributing to herald

Thanks for your interest. This project makes clinical practice guidelines computable — contributions from both developers and clinicians are valuable.

## Getting started

```bash
git clone https://github.com/myceldigital/herald.git
cd herald
pip install -e ".[dev]"
pytest tests/ -v
```

## High-impact contributions

1. **Testing against real guideline formats** — does `herald convert` handle your guideline's PDF structure?
2. **Schema improvements** — edge cases in clinical decision logic the schema doesn't cover yet
3. **Query engine features** — new operators, better NL parsing, multi-guideline queries
4. **Synthetic guidelines** — new conditions (depression, hypertension, diabetes)

## Code style

Python 3.10+, ruff for linting, type hints on all functions, tests for all new code.

## Clinical accuracy

Synthetic guidelines must be clearly labelled as fictional. Do not copy copyrighted guideline text. Clinical logic should be evidence-informed but marked as demonstration, not clinical advice.
