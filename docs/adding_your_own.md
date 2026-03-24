# Adding your own guidelines

## Before you start

1. **Check the licence.** NICE requires a separate AI licence. WHO publishes some under CC BY-NC-SA. Check before converting.
2. **Get the full PDF.** Use the complete guideline, not the summary version.
3. **Ensure selectable text.** If you can't highlight text in the PDF, run OCR first (e.g., `ocrmypdf`).

## The pipeline

```bash
# Step 1: Convert PDF → markdown (no LLM needed)
herald convert your-guideline.pdf -o your-guideline.md

# Step 2: Review the markdown — fix any formatting issues

# Step 3: Parse markdown → decision tree (needs API key)
export ANTHROPIC_API_KEY=sk-ant-...
herald parse your-guideline.md -o your-guideline.json

# Step 4: Validate the parse against the source
herald validate your-guideline.json --source your-guideline.md

# Step 5: Query
herald query your-guideline.json
```

## Improving parse quality

If the initial parse misses recommendations or gets decision logic wrong:

1. **Simplify the input.** Extract just the recommendation chapters and parse those.
2. **Try a stronger model.** `--model claude-opus-4-20250514` may handle complex guidelines better.
3. **Manual refinement.** The JSON is human-readable — edit nodes, fix conditions, add branches directly.
