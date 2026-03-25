"""Tests for the validate module — source text verification."""

import json
import tempfile
from pathlib import Path

from herald_cli.validate import validate_tree


def _write_temp(content: str, suffix: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


class TestValidateTree:
    """Tests for decision tree validation against source markdown."""

    def test_verified_when_text_found(self):
        source_md = "# Section 4.1\n\nMethylphenidate is recommended as first-line treatment."
        tree = {
            "decisions": [
                {
                    "id": "test",
                    "recommendation": {
                        "action": "Start methylphenidate",
                        "source_section": "4.1",
                        "source_text": "Methylphenidate is recommended as first-line treatment.",
                    },
                }
            ]
        }
        source_path = _write_temp(source_md, ".md")
        tree_path = _write_temp(json.dumps(tree), ".json")

        results = validate_tree(tree_path, source_path)
        assert len(results) == 1
        assert results[0]["status"] == "verified"

    def test_not_found_when_text_missing(self):
        source_md = "# Section 4.1\n\nSome unrelated content here."
        tree = {
            "decisions": [
                {
                    "id": "test",
                    "recommendation": {
                        "action": "Start methylphenidate",
                        "source_section": "4.1",
                        "source_text": "Totally different text that is not in the source.",
                    },
                }
            ]
        }
        source_path = _write_temp(source_md, ".md")
        tree_path = _write_temp(json.dumps(tree), ".json")

        results = validate_tree(tree_path, source_path)
        assert len(results) == 1
        assert results[0]["status"] == "not_found"

    def test_missing_when_no_source_text(self):
        source_md = "# Content"
        tree = {
            "decisions": [
                {
                    "id": "test",
                    "recommendation": {
                        "action": "Do something",
                        "source_text": "",
                    },
                }
            ]
        }
        source_path = _write_temp(source_md, ".md")
        tree_path = _write_temp(json.dumps(tree), ".json")

        results = validate_tree(tree_path, source_path)
        assert results[0]["status"] == "missing"

    def test_partial_match(self):
        source_md = (
            "Methylphenidate is recommended as first-line "
            "treatment for adults with ADHD in most "
            "clinical settings."
        )
        tree = {
            "decisions": [
                {
                    "id": "test",
                    "recommendation": {
                        "action": "Start mph",
                        "source_text": (
                            "Methylphenidate is recommended as "
                            "first-line treatment for adults with "
                            "ADHD in most clinical settings and "
                            "also some other text that was "
                            "hallucinated."
                        ),
                    },
                }
            ]
        }
        source_path = _write_temp(source_md, ".md")
        tree_path = _write_temp(json.dumps(tree), ".json")

        results = validate_tree(tree_path, source_path)
        assert results[0]["status"] == "partial"

    def test_multiple_nodes_validated(self):
        source_md = "First-line is methylphenidate. Second-line is atomoxetine."
        tree = {
            "decisions": [
                {
                    "id": "first",
                    "recommendation": {
                        "action": "A",
                        "source_text": "First-line is methylphenidate.",
                    },
                },
                {
                    "id": "second",
                    "recommendation": {"action": "B", "source_text": "Second-line is atomoxetine."},
                },
            ]
        }
        source_path = _write_temp(source_md, ".md")
        tree_path = _write_temp(json.dumps(tree), ".json")

        results = validate_tree(tree_path, source_path)
        assert len(results) == 2
        assert all(r["status"] == "verified" for r in results)
