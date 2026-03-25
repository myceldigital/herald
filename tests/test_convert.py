"""Tests for the convert module (markitdown wrapper)."""

from herald_cli.convert import _normalize_markdown


class TestNormalizeMarkdown:
    """Tests for markdown post-processing."""

    def test_collapses_multiple_blank_lines(self):
        text = "Line 1\n\n\n\nLine 2"
        result = _normalize_markdown(text)
        assert "\n\n\n" not in result
        assert "Line 1\n\nLine 2" in result

    def test_strips_trailing_whitespace(self):
        text = "Line 1   \nLine 2  \n"
        result = _normalize_markdown(text)
        for line in result.split("\n"):
            assert line == line.rstrip()

    def test_preserves_single_blank_lines(self):
        text = "Line 1\n\nLine 2"
        result = _normalize_markdown(text)
        assert "Line 1\n\nLine 2" in result

    def test_ends_with_newline(self):
        text = "Some content"
        result = _normalize_markdown(text)
        assert result.endswith("\n")
