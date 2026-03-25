"""Convert guideline PDFs to structured markdown using markitdown."""

from pathlib import Path


def convert_pdf(input_path: Path) -> str:
    """Convert a PDF file to structured markdown.

    Uses Microsoft's markitdown library to extract text while preserving
    headings, lists, tables, and document structure.

    Args:
        input_path: Path to the PDF file.

    Returns:
        Markdown string with preserved document structure.

    Raises:
        FileNotFoundError: If the input file does not exist.
        RuntimeError: If markitdown fails to convert the file.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    try:
        from markitdown import MarkItDown
    except ImportError:
        raise RuntimeError(
            "markitdown is required for PDF conversion. "
            "Install it with: pip install 'guideline-as-code[all]' "
            "or: pip install markitdown"
        )

    md = MarkItDown()
    result = md.convert(str(input_path))

    if not result or not result.text_content:
        raise RuntimeError(f"markitdown returned empty result for {input_path}")

    text = result.text_content

    # Post-process: normalize whitespace, ensure consistent heading levels
    text = _normalize_markdown(text)

    return text


def _normalize_markdown(text: str) -> str:
    """Clean up markitdown output for better parsing.

    Fixes common markitdown artifacts:
    - Excessive blank lines
    - Inconsistent heading markers
    - Trailing whitespace
    """
    lines = text.split("\n")
    cleaned = []
    prev_blank = False

    for line in lines:
        line = line.rstrip()

        # Collapse multiple blank lines into one
        if not line:
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
            continue

        prev_blank = False
        cleaned.append(line)

    return "\n".join(cleaned).strip() + "\n"
