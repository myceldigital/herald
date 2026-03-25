"""CLI integration tests for user-facing error handling."""

from click.testing import CliRunner

from herald_cli.cli import cli


def test_parse_missing_api_key_returns_clean_click_error(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    input_file = tmp_path / "guideline.md"
    input_file.write_text("# Test guideline\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["parse", str(input_file)])

    assert result.exit_code == 1
    assert "Error: ANTHROPIC_API_KEY environment variable not set." in result.output
    assert "Traceback" not in result.output


def test_parse_openai_missing_api_key_returns_clean_click_error(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    input_file = tmp_path / "guideline.md"
    input_file.write_text("# Test guideline\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["parse", str(input_file), "--provider", "openai"])

    assert result.exit_code == 1
    assert "Error: OPENAI_API_KEY environment variable not set." in result.output
    assert "Traceback" not in result.output


def test_diff_invalid_json_returns_clean_click_error(tmp_path):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text("{not valid json", encoding="utf-8")
    right.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(cli, ["diff", str(left), str(right)])

    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Traceback" not in result.output
