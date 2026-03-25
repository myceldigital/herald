# Supported guideline formats

`herald convert` uses markitdown, which handles most PDF formats. Results vary by guideline structure.

## Works well

- Well-structured PDFs with clear headings and numbered sections (most NICE, WHO, SIGN guidelines)
- Text-based PDFs where text is selectable
- Guidelines with numbered recommendations and evidence grading tables

## Works with caveats

- Two-column PDFs — may occasionally merge columns
- Complex treatment algorithm tables — may lose some structure
- Embedded flowchart images — image content won't be extracted

## Does not work

- Scanned PDFs without OCR — run `ocrmypdf` first
- Password-protected PDFs — decrypt first
- Slide-deck format guidelines — insufficient continuous text

## Publisher notes

| Publisher | Quality | Notes |
|-----------|---------|-------|
| NICE (UK) | Excellent | Numbered sections, clear recommendation statements |
| WHO | Good | Consistent format, clear evidence grading |
| SIGN (Scotland) | Good | Clear recommendation boxes with evidence levels |
| APA (USA) | Variable | Some are text-heavy without clear recommendation markers |
