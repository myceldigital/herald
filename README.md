# Herald

[![PyPI version](https://img.shields.io/pypi/v/herald-cpg)](https://pypi.org/project/herald-cpg/)
[![CI](https://github.com/myceldigital/herald/actions/workflows/ci.yml/badge.svg)](https://github.com/myceldigital/herald/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://github.com/myceldigital/herald)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Clinical guidelines, as code.**

Turn a clinical practice guideline PDF into a deterministic, queryable decision engine with source citations.

Herald uses an LLM once during the parse step to extract decision logic from guideline text. After that, queries are deterministic: no LLM in the loop, no hallucinated answers at query time, and no API key required to run queries against an already parsed guideline.

```bash
herald convert guideline.pdf          # PDF -> structured markdown
herald parse guideline.md             # markdown -> decision tree JSON
herald query guideline.json           # deterministic recommendations with citations
```

## Try It In 30 Seconds

No API key required for the demo. The repo ships synthetic guidelines that are safe to run locally.

```bash
pip install herald-cpg
herald query examples/synthetic_meningitis_guideline.json \
  --ask "68F, suspected meningitis"
```

Example output:

```text
Recommendation [critical]: Start ceftriaxone plus vancomycin immediately and add ampicillin for Listeria coverage.
Evidence grade: A (strong)
Source: Section 2.2, p.14
"In adults aged 50 years or older, or in patients who are immunocompromised, add ampicillin to the empiric regimen to cover Listeria."
```

## Why This Exists

Clinical practice guidelines are some of the highest-value documents in healthcare. They encode treatment logic, evidence grading, and contraindications, but most of that logic is trapped in PDFs.

Herald turns those PDFs into infrastructure:

- queryable
- auditable
- versionable
- exportable
- usable without an LLM at runtime

## Why This Is Not ChatGPT

| Herald | Generic clinical chatbot |
|---|---|
| LLM used only during parse | LLM used at query time |
| Deterministic query engine | Non-deterministic generation |
| Structured JSON decision tree | Mostly unstructured answers |
| Citation metadata stored on recommendations | Citation quality varies |
| Local querying after parse | Ongoing service/API dependency |
| Diffable and exportable artifacts | Mostly chat transcripts |

## Why People Can Trust It

- Querying is deterministic once the guideline is parsed.
- Recommendations retain `source_section`, `source_page`, and `source_text`.
- `herald validate` checks extracted recommendations against the source markdown and reports a fidelity score.
- `herald diff` compares old and new guideline versions in text, JSON, or markdown.
- `herald export` emits FHIR `PlanDefinition` for downstream CDS pipelines.

Herald is not a bedside autopilot. It is tooling for turning guidelines into inspectable, reviewable clinical logic.

## Who It Is For

- Clinical informaticists building computable guideline logic
- Digital health teams distributing protocol logic offline
- Health services researchers measuring guideline adherence
- Guideline authors who want recommendations to be implementable
- Health-tech teams that need auditable CDS infrastructure

## What Ships Today

| Capability | Status | Notes |
|---|---|---|
| PDF -> markdown conversion | Shipped | Uses [markitdown](https://github.com/microsoft/markitdown) |
| Markdown -> decision tree parse | Shipped | Anthropic or OpenAI |
| Deterministic query engine | Shipped | No LLM required to query |
| Source-text validation | Shipped | Fidelity scoring included |
| Guideline diffing | Shipped | Text, JSON, or markdown |
| FHIR `PlanDefinition` export | Shipped | For downstream CDS workflows |
| Batch querying from CSV | Shipped | `herald query --batch` |
| Multi-guideline query support | Shipped | Includes conflict detection |
| Audit logging | Shipped | JSONL query/result log |

## Repo Navigation

- `README.md` - product overview and quick start
- `docs/adding_your_own.md` - run Herald on your own guideline
- `docs/supported_guidelines.md` - what converts cleanly and what does not
- `SCHEMA.md` - full decision-tree schema
- `CONTRIBUTING.md` - contribution workflow and standards

## Install

```bash
pip install herald-cpg
```

From source:

```bash
git clone https://github.com/myceldigital/herald.git
cd herald
pip install -e ".[dev]"
```

## Quick Start

### 1. Query a shipped example

```bash
herald query examples/synthetic_meningitis_guideline.json
```

Or ask a single question:

```bash
herald query examples/synthetic_meningitis_guideline.json \
  --ask "68F, suspected meningitis"
```

Other shipped examples:

```bash
herald query examples/synthetic_adhd_guideline.json \
  --ask "Adult male, tried methylphenidate with partial response and insomnia"
```

### 2. Convert your own guideline

```bash
herald convert path/to/guideline.pdf -o guideline.md
```

### 3. Parse to a decision tree

Anthropic:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
herald parse guideline.md -o guideline.json
```

OpenAI:

```bash
export OPENAI_API_KEY=sk-...
herald parse guideline.md -o guideline.json --provider openai
```

### 4. Validate before relying on the parse

```bash
herald validate guideline.json --source guideline.md
```

This checks whether `source_text` from each recommendation is actually present in the source markdown and reports a fidelity score.

### 5. Diff protocol updates

```bash
herald diff old_guideline.json new_guideline.json --format markdown
```

### 6. Export to FHIR

```bash
herald export guideline.json -o guideline.fhir.json
```

## Trust Model And Limits

- Herald is strongest when the source PDF has clean structure and selectable text.
- The parse step is probabilistic because it uses an LLM.
- The query step is deterministic because it traverses the saved decision tree.
- Parsed guidelines should be reviewed and validated before real clinical use.
- This repo ships the engine, not real clinical content. The examples in `examples/` are synthetic.

## Schema

Parsed guidelines conform to the Herald decision-tree schema in [SCHEMA.md](SCHEMA.md).

Every recommendation can retain:

- recommendation text
- evidence grade and strength
- source section
- source page
- exact supporting quote
- branching logic
- structured dosing and workflow fields

Minimal example:

```json
{
  "guideline": {
    "title": "Synthetic Acute Bacterial Meningitis Guideline",
    "source": "Synthetic Example Guideline Consortium (SEGC)",
    "version": "1.0",
    "last_updated": "2026-03-25"
  },
  "decisions": [
    {
      "id": "adult_empiric_therapy",
      "entry_point": true,
      "conditions": [
        { "field": "diagnosis", "operator": "eq", "value": "meningitis" }
      ],
      "recommendation": {
        "action": "Start ceftriaxone plus vancomycin immediately.",
        "source_section": "2.1",
        "source_page": 13,
        "source_text": "Administer ceftriaxone plus vancomycin immediately when acute bacterial meningitis is suspected in adults."
      }
    }
  ]
}
```

## Supported Inputs

See [docs/supported_guidelines.md](docs/supported_guidelines.md) for current conversion guidance.

Short version:

- best: text-based PDFs with numbered sections and explicit recommendations
- okay with caveats: two-column layouts, complex tables
- weak: scanned PDFs without OCR, image-heavy flowcharts, slide decks

## Try It With Real Guidelines

If you want to test Herald on real public guidelines, start with structured, text-based documents from major publishers:

- [NICE Guidance](https://www.nice.org.uk/guidance/)
- [WHO Guidelines](https://www.who.int/publications/guidelines/en/)
- [SIGN Guidelines](https://www.sign.ac.uk/guidelines/)
- [CDC Clinical Guidance](https://www.cdc.gov/flu/hcp/clinical-guidance/index.html)

Prefer guideline landing pages over random mirrored PDFs. Herald works best on documents with selectable text, numbered sections, and explicit recommendation statements.

## Licensing And Content

Clinical practice guidelines are usually copyrighted by their publishers. Herald is designed to let users convert and query guidelines locally, but you still need to respect each publisher's reuse policy.

To use Herald with a real guideline:

1. Obtain the PDF through legitimate channels.
2. Check the publisher's licence and reuse policy.
3. Convert, parse, validate, and query locally.

## Roadmap

### Now

- deterministic query engine
- validation with fidelity scoring
- diffing for guideline updates
- FHIR export
- batch and multi-guideline query support

### Next

- MCP server for editor and desktop integrations
- richer export targets beyond FHIR `PlanDefinition`
- community registry of openly shareable synthetic/example guidelines
- broader multilingual and publisher-format support

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
