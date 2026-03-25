# Adding Your Own Guidelines

Use this flow when you want to take a real guideline PDF and turn it into a local, queryable Herald artifact.

## Before You Start

1. Check the licence. NICE, WHO, specialty societies, and hospitals all have different reuse rules.
2. Get the full guideline PDF, not the executive summary.
3. Make sure the PDF has selectable text. If not, run OCR first, for example with `ocrmypdf`.
4. Expect to review the parse. Herald is designed for auditable extraction, not blind trust.

## Recommended Workflow

```bash
# 1. Convert PDF -> markdown
herald convert your-guideline.pdf -o your-guideline.md

# 2. Inspect the markdown
#    Check headings, tables, recommendation sections, and page/section structure

# 3. Parse markdown -> decision tree JSON
export ANTHROPIC_API_KEY=sk-ant-...
herald parse your-guideline.md -o your-guideline.json

# 4. Validate the extracted source text against the markdown
herald validate your-guideline.json --source your-guideline.md

# 5. Query the result locally
herald query your-guideline.json
```

## What Good Input Looks Like

Herald works best when the guideline has:

- clear numbered sections
- recommendation-heavy prose rather than image-only flowcharts
- explicit treatment statements
- stable clinical vocabulary

If the PDF is messy, fix the markdown before parsing. A cleaner `guideline.md` usually beats throwing a stronger model at a bad input.

## Improving Parse Quality

If the first parse is not good enough:

1. Narrow the markdown to recommendation chapters first.
2. Remove junk such as repeated headers, footers, and OCR artifacts.
3. Try a stronger model with `--model`.
4. Manually refine the JSON. Herald artifacts are meant to be inspectable and editable.
5. Re-run `herald validate` until the fidelity report is acceptable for your use case.

## Suggested Review Checklist

- Do the decision entry points match the guideline's main pathways?
- Do all important recommendations have `source_text` and `source_section`?
- Are required patient fields reasonable, or did the parse overfit to one subsection?
- Do high-risk recommendations have the right contraindications, urgency, and dosing details?
- Do representative patient queries return the expected path?

## Local-First By Design

Once you have a parsed JSON file, querying does not require an API key. That makes Herald useful for local review workflows, offline distribution, and controlled deployment environments where runtime LLM calls are unacceptable.
