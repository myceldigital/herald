# Herald

**Turn any clinical practice guideline PDF into a queryable decision engine.**

Clinical practice guidelines are the operating system of medicine. NICE alone publishes 300+. The APA, WHO, SIGN — hundreds more. They contain the distilled evidence for how every condition should be diagnosed, treated, and monitored.

They're trapped in PDFs. Clinicians recall them from memory. Guideline adherence rates sit at 50–70%.

Herald fixes this in three commands:

```bash
herald convert guideline.pdf          # PDF → structured markdown
herald parse guideline.md             # markdown → decision tree (JSON)
herald query guideline.json           # ask clinical questions, get cited answers
```

## Try it now — no API key needed

```bash
pip install herald-cpg
herald query examples/synthetic_adhd_guideline.json
```

```
> Patient: 34F, ADHD confirmed, comorbid anxiety, no cardiac history

  Recommendation: First-line — atomoxetine OR SSRI + methylphenidate
  Evidence grade: A (strong)
  Conditions: anxiety comorbidity present, no cardiac contraindication
  Source: Section 4.2.1, p.23 — "When ADHD presents with comorbid anxiety..."
```

The answer traces back to a specific section and page of the source guideline. Every recommendation is auditable.

---

## What it does

Herald is a three-stage pipeline:

| Stage | Command | Input | Output | Needs LLM? |
|-------|---------|-------|--------|-------------|
| **Convert** | `herald convert` | Guideline PDF | Structured markdown | No |
| **Parse** | `herald parse` | Markdown | Decision tree JSON | Yes |
| **Query** | `herald query` | Decision tree JSON | Clinical recommendations | No |

**Convert** uses [markitdown](https://github.com/microsoft/markitdown) to extract text from PDFs while preserving headings, tables, and document structure.

**Parse** sends the markdown to an LLM with structured extraction prompts, identifying recommendation statements, conditional logic, evidence grades, and decision branching. The output is a machine-readable decision tree following the [Herald Schema](SCHEMA.md).

**Query** traverses the decision tree deterministically — no LLM required. You provide patient attributes (age, sex, comorbidities, prior treatments), and the engine walks the tree to return the guideline-concordant recommendation with full source citations.

## Install

```bash
pip install herald-cpg
```

Or from source:

```bash
git clone https://github.com/yourusername/herald.git
cd herald
pip install -e ".[dev]"
```

## Quick start

### 1. Try the demo (no API key)

The repo ships with pre-parsed synthetic guidelines. Query them immediately:

```bash
# Interactive query mode
herald query examples/synthetic_adhd_guideline.json

# Single question
herald query examples/synthetic_adhd_guideline.json \
  --ask "Adult male, tried methylphenidate with partial response and insomnia"
```

### 2. Convert your own guideline

```bash
herald convert path/to/guideline.pdf -o guideline.md
```

### 3. Parse into a decision tree

Requires an LLM API key (Anthropic recommended):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
herald parse guideline.md -o guideline.json
```

Or use OpenAI:

```bash
export OPENAI_API_KEY=sk-...
herald parse guideline.md -o guideline.json --provider openai
```

### 4. Validate the parse

Before trusting a parsed guideline clinically, validate it:

```bash
herald validate guideline.json --source guideline.md
```

This generates a diff showing every parsed recommendation alongside the exact source text it was extracted from. A clinician can review the mapping in minutes instead of months.

## The schema

The decision tree JSON follows a structured schema designed for clinical decision logic. See [SCHEMA.md](SCHEMA.md) for the full specification.

A minimal example:

```json
{
  "guideline": {
    "title": "Management of ADHD in Adults",
    "source": "Synthetic Example Guideline v1.0",
    "version": "1.0",
    "last_updated": "2026-03-24"
  },
  "decisions": [
    {
      "id": "first_line_treatment",
      "description": "First-line pharmacological treatment for adult ADHD",
      "conditions": [
        { "field": "diagnosis", "operator": "eq", "value": "ADHD" },
        { "field": "age_group", "operator": "eq", "value": "adult" }
      ],
      "recommendation": {
        "action": "Start methylphenidate (first-line stimulant)",
        "evidence_grade": "A",
        "strength": "strong",
        "source_section": "4.1",
        "source_page": 18,
        "source_text": "Methylphenidate is recommended as first-line..."
      },
      "branches": [
        {
          "condition": { "field": "comorbidity", "operator": "contains", "value": "anxiety" },
          "next_decision": "adhd_with_anxiety"
        }
      ]
    }
  ]
}
```

Every recommendation traces back to `source_section`, `source_page`, and `source_text` — the exact words from the original guideline.

## Important: licensing and content

**This repo ships the engine, not the content.** Clinical practice guidelines are copyrighted by their publishers (NICE, APA, WHO, etc.). The example guidelines in `examples/` are synthetic — written from scratch for demonstration purposes.

To use Herald with real guidelines:
1. Obtain the guideline PDF through legitimate channels
2. Check the publisher's reuse policy
3. Convert, parse, and query locally — your documents stay on your machine

## Roadmap

- [x] Core pipeline: convert → parse → query
- [x] Deterministic query engine (no LLM needed)
- [x] Validation diffs for clinical review
- [ ] MCP server for Claude Desktop / Cursor integration
- [ ] FHIR PlanDefinition export
- [ ] Community guideline registry
- [ ] Multi-language guideline support
- [ ] Batch processing for guideline libraries

## Why this matters

Every digital health company building clinical decision support manually encodes guidelines into software. Teams of clinicians spend months translating PDF recommendations into if/then logic. The output is proprietary and locked inside one product.

Herald automates the translation. One command converts months of manual work into a structured, auditable, queryable decision tree.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT
