"""Tests for the diff module — guideline version comparison."""

from herald_cli.diff import diff_guidelines, format_markdown


def _make_guideline(decisions, meta=None, patient_fields=None):
    g = {
        "guideline": meta or {"title": "Test", "source": "Test", "version": "1.0"},
        "decisions": decisions,
    }
    if patient_fields is not None:
        g["patient_fields"] = patient_fields
    return g


def _node(id, action="Do something", grade="A", strength="strong",
          conditions=None, branches=None):
    n = {
        "id": id,
        "description": f"Node {id}",
        "recommendation": {
            "action": action,
            "evidence_grade": grade,
            "strength": strength,
            "source_section": "1.0",
            "source_text": "Some source text.",
        },
    }
    if conditions:
        n["conditions"] = conditions
    if branches:
        n["branches"] = branches
    return n


class TestDiffGuidelines:
    """Tests for diff_guidelines comparison logic."""

    def test_identical_guidelines_show_no_changes(self):
        g = _make_guideline([_node("a"), _node("b")])
        result = diff_guidelines(g, g)
        s = result["summary"]
        assert s["nodes_added"] == 0
        assert s["nodes_removed"] == 0
        assert s["nodes_modified"] == 0
        assert s["nodes_unchanged"] == 2
        assert result["added"] == []
        assert result["removed"] == []
        assert result["modified"] == []

    def test_added_node_detected(self):
        old = _make_guideline([_node("a")])
        new = _make_guideline([_node("a"), _node("b")])
        result = diff_guidelines(old, new)
        assert result["summary"]["nodes_added"] == 1
        assert result["summary"]["nodes_unchanged"] == 1
        assert len(result["added"]) == 1
        assert result["added"][0]["id"] == "b"

    def test_removed_node_detected(self):
        old = _make_guideline([_node("a"), _node("b")])
        new = _make_guideline([_node("a")])
        result = diff_guidelines(old, new)
        assert result["summary"]["nodes_removed"] == 1
        assert len(result["removed"]) == 1
        assert result["removed"][0]["id"] == "b"

    def test_modified_action_text(self):
        old = _make_guideline([_node("a", action="Start drug X")])
        new = _make_guideline([_node("a", action="Start drug Y")])
        result = diff_guidelines(old, new)
        assert result["summary"]["nodes_modified"] == 1
        assert result["summary"]["nodes_unchanged"] == 0
        mod = result["modified"][0]
        assert mod["id"] == "a"
        actions = [c for c in mod["changes"] if c["field"] == "recommendation.action"]
        assert len(actions) == 1
        assert actions[0]["old"] == "Start drug X"
        assert actions[0]["new"] == "Start drug Y"

    def test_modified_evidence_grade(self):
        old = _make_guideline([_node("a", grade="B")])
        new = _make_guideline([_node("a", grade="A")])
        result = diff_guidelines(old, new)
        assert result["summary"]["nodes_modified"] == 1
        grades = [c for c in result["modified"][0]["changes"]
                  if c["field"] == "recommendation.evidence_grade"]
        assert grades[0]["old"] == "B"
        assert grades[0]["new"] == "A"

    def test_modified_strength(self):
        old = _make_guideline([_node("a", strength="conditional")])
        new = _make_guideline([_node("a", strength="strong")])
        result = diff_guidelines(old, new)
        strengths = [c for c in result["modified"][0]["changes"]
                     if c["field"] == "recommendation.strength"]
        assert strengths[0]["old"] == "conditional"
        assert strengths[0]["new"] == "strong"

    def test_modified_conditions(self):
        old = _make_guideline([_node("a", conditions=[
            {"field": "age", "operator": "gt", "value": 18}
        ])])
        new = _make_guideline([_node("a", conditions=[
            {"field": "age", "operator": "gt", "value": 12}
        ])])
        result = diff_guidelines(old, new)
        conds = [c for c in result["modified"][0]["changes"]
                 if c["field"] == "conditions"]
        assert len(conds) == 1

    def test_modified_branches(self):
        old = _make_guideline([_node("a", branches=[
            {"condition": {"field": "x", "operator": "eq", "value": "y"},
             "next_decision": "b"}
        ])])
        new = _make_guideline([_node("a", branches=[])])
        result = diff_guidelines(old, new)
        br = [c for c in result["modified"][0]["changes"]
              if c["field"] == "branches"]
        assert br[0]["old_count"] == 1
        assert br[0]["new_count"] == 0

    def test_metadata_changes_detected(self):
        old = _make_guideline([], meta={"title": "V1", "version": "1.0"})
        new = _make_guideline([], meta={"title": "V2", "version": "2.0"})
        result = diff_guidelines(old, new)
        fields_changed = {c["field"] for c in result["metadata_changes"]}
        assert "title" in fields_changed
        assert "version" in fields_changed

    def test_no_metadata_changes_when_identical(self):
        meta = {"title": "Same", "version": "1.0"}
        old = _make_guideline([], meta=meta)
        new = _make_guideline([], meta=meta)
        result = diff_guidelines(old, new)
        assert result["metadata_changes"] == []

    def test_patient_fields_added(self):
        old = _make_guideline([], patient_fields=[
            {"field": "age", "type": "number"}
        ])
        new = _make_guideline([], patient_fields=[
            {"field": "age", "type": "number"},
            {"field": "sex", "type": "enum"},
        ])
        result = diff_guidelines(old, new)
        assert result["summary"]["fields_added"] == 1
        assert "sex" in result["fields_added"]

    def test_patient_fields_removed(self):
        old = _make_guideline([], patient_fields=[
            {"field": "age", "type": "number"},
            {"field": "sex", "type": "enum"},
        ])
        new = _make_guideline([], patient_fields=[
            {"field": "age", "type": "number"},
        ])
        result = diff_guidelines(old, new)
        assert result["summary"]["fields_removed"] == 1
        assert "sex" in result["fields_removed"]

    def test_complex_diff_add_remove_modify(self):
        old = _make_guideline([
            _node("keep", action="Same"),
            _node("change", action="Old action"),
            _node("drop", action="Removed"),
        ])
        new = _make_guideline([
            _node("keep", action="Same"),
            _node("change", action="New action"),
            _node("new_node", action="Brand new"),
        ])
        result = diff_guidelines(old, new)
        assert result["summary"]["nodes_added"] == 1
        assert result["summary"]["nodes_removed"] == 1
        assert result["summary"]["nodes_modified"] == 1
        assert result["summary"]["nodes_unchanged"] == 1

    def test_empty_guidelines(self):
        old = _make_guideline([])
        new = _make_guideline([])
        result = diff_guidelines(old, new)
        assert result["summary"]["nodes_added"] == 0
        assert result["summary"]["nodes_removed"] == 0


class TestFormatMarkdown:
    """Tests for markdown diff formatting."""

    def test_contains_title_with_filenames(self):
        result = diff_guidelines(
            _make_guideline([_node("a")]),
            _make_guideline([_node("a")]),
        )
        md = format_markdown(result, "old.json", "new.json")
        assert "old.json" in md
        assert "new.json" in md

    def test_shows_added_nodes(self):
        old = _make_guideline([])
        new = _make_guideline([_node("new_rec")])
        result = diff_guidelines(old, new)
        md = format_markdown(result)
        assert "new_rec" in md
        assert "New Recommendations" in md

    def test_shows_removed_nodes(self):
        old = _make_guideline([_node("old_rec")])
        new = _make_guideline([])
        result = diff_guidelines(old, new)
        md = format_markdown(result)
        assert "old_rec" in md
        assert "Removed Recommendations" in md

    def test_shows_modified_nodes(self):
        old = _make_guideline([_node("x", action="Before")])
        new = _make_guideline([_node("x", action="After")])
        result = diff_guidelines(old, new)
        md = format_markdown(result)
        assert "Modified Recommendations" in md
        assert "Before" in md
        assert "After" in md

    def test_shows_metadata_changes(self):
        old = _make_guideline([], meta={"title": "Old Title"})
        new = _make_guideline([], meta={"title": "New Title"})
        result = diff_guidelines(old, new)
        md = format_markdown(result)
        assert "Metadata Changes" in md
        assert "Old Title" in md
        assert "New Title" in md

    def test_shows_field_changes(self):
        old = _make_guideline([], patient_fields=[])
        new = _make_guideline([], patient_fields=[{"field": "bmi", "type": "number"}])
        result = diff_guidelines(old, new)
        md = format_markdown(result)
        assert "bmi" in md

    def test_summary_counts_in_output(self):
        old = _make_guideline([_node("a")])
        new = _make_guideline([_node("a"), _node("b")])
        result = diff_guidelines(old, new)
        md = format_markdown(result)
        assert "**1**" in md  # 1 added
