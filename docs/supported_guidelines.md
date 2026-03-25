# Supported Guideline Formats

`herald convert` uses [markitdown](https://github.com/microsoft/markitdown), so the main constraint is not the file extension, it is document structure.

## Best Fit

These tend to work well:

- text-based PDFs with selectable text
- guidelines with numbered sections and sub-sections
- recommendation chapters with explicit treatment statements
- documents that keep prose, tables, and evidence grades in the text layer

Typical examples:

- NICE
- WHO
- SIGN
- similar specialty-society guidelines with conventional section structure

## Usually Works, But Review Carefully

- two-column PDFs
- dense evidence tables
- algorithm-heavy documents where some logic lives in tables rather than prose
- long guidelines with repeated running headers or page footers

These often convert well enough to parse, but you should inspect the markdown before running `herald parse`.

## Weak Fit

- scanned PDFs without OCR
- documents where key logic only exists inside images
- slide decks exported to PDF
- heavily designed layouts where reading order is ambiguous
- password-protected PDFs

If you cannot highlight text in the original PDF, run OCR first.

## Publisher Notes

| Publisher | Expected quality | Notes |
|---|---|---|
| NICE (UK) | Excellent | Usually strong numbered structure and clear recommendations |
| WHO | Good | Often consistent, but long documents may include repeated headers/footers |
| SIGN (Scotland) | Good | Recommendation boxes usually survive conversion well |
| APA (USA) | Variable | Some documents are more narrative and less recommendation-structured |
| Local hospital protocols | Variable | Often excellent if they are plain text; weak if exported from slides |

## Practical Advice

Before parsing a real guideline:

1. Run `herald convert`.
2. Open the generated markdown.
3. Check whether recommendation sections, tables, and headings survived.
4. Delete obvious conversion junk if needed.
5. Parse only once the markdown looks readable by a human.

Herald is much more reliable on a cleaned markdown file than on a raw, noisy conversion.
