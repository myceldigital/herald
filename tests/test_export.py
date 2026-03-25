"""Tests for the export module — FHIR PlanDefinition export."""

import json
from pathlib import Path

from herald_cli.export import (
    _build_action,
    _build_conditions,
    _build_inputs,
    _clean_none,
    _map_type,
    export_fhir,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _minimal_tree(**overrides):
    tree = {
        "guideline": {
            "title": "Test Guideline",
            "source": "Test Body",
            "version": "1.0",
            "last_updated": "2026-01-01",
            "condition": "ADHD",
            "population": "Adults",
        },
        "patient_fields": [
            {"field": "diagnosis", "type": "string", "description": "Primary diagnosis"},
            {"field": "age", "type": "number"},
        ],
        "decisions": [
            {
                "id": "first_line",
                "description": "First-line treatment",
                "conditions": [{"field": "diagnosis", "operator": "eq", "value": "ADHD"}],
                "recommendation": {
                    "action": "Start methylphenidate",
                    "evidence_grade": "A",
                    "strength": "strong",
                    "source_section": "4.1",
                    "source_text": "Methylphenidate is first-line.",
                },
                "branches": [
                    {
                        "condition": {"field": "anxiety", "operator": "eq", "value": True},
                        "next_decision": "anxiety_path",
                        "label": "Has anxiety",
                    }
                ],
            },
        ],
    }
    tree.update(overrides)
    return tree


class TestExportFhir:
    """Tests for the top-level FHIR export."""

    def test_resource_type_is_plan_definition(self):
        result = export_fhir(_minimal_tree())
        assert result["resourceType"] == "PlanDefinition"

    def test_metadata_mapped_correctly(self):
        result = export_fhir(_minimal_tree())
        assert result["title"] == "Test Guideline"
        assert result["publisher"] == "Test Body"
        assert result["version"] == "1.0"
        assert result["date"] == "2026-01-01"
        assert result["status"] == "active"
        assert result["experimental"] is True

    def test_type_coding_is_clinical_protocol(self):
        result = export_fhir(_minimal_tree())
        coding = result["type"]["coding"][0]
        assert coding["code"] == "clinical-protocol"

    def test_use_context_reflects_condition(self):
        result = export_fhir(_minimal_tree())
        ctx = result["useContext"][0]
        assert ctx["valueCodeableConcept"]["text"] == "ADHD"

    def test_actions_match_decisions_count(self):
        result = export_fhir(_minimal_tree())
        assert len(result["action"]) == 1

    def test_inputs_match_patient_fields(self):
        result = export_fhir(_minimal_tree())
        assert len(result["input"]) == 2
        ids = [i["id"] for i in result["input"]]
        assert "diagnosis" in ids
        assert "age" in ids

    def test_no_none_values_in_output(self):
        result = export_fhir(_minimal_tree())
        _assert_no_nones(result)

    def test_full_example_guideline_exports(self):
        path = EXAMPLES_DIR / "synthetic_adhd_guideline.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        result = export_fhir(data)
        assert result["resourceType"] == "PlanDefinition"
        assert len(result["action"]) == len(data["decisions"])
        _assert_no_nones(result)

    def test_empty_decisions_strips_actions_key(self):
        tree = _minimal_tree(decisions=[])
        result = export_fhir(tree)
        assert "action" not in result  # _clean_none removes empty lists


class TestBuildAction:
    """Tests for individual action construction."""

    def test_action_id_and_title(self):
        decision = {
            "id": "test_node",
            "description": "Test description",
            "conditions": [],
            "recommendation": {"action": "Do X", "source_text": "Quote here."},
        }
        action = _build_action(decision, [])
        assert action["id"] == "test_node"
        assert action["title"] == "Test description"
        assert action["description"] == "Do X"

    def test_documentation_citation(self):
        decision = {
            "id": "n",
            "description": "",
            "conditions": [],
            "recommendation": {
                "action": "A",
                "source_text": "Exact quote",
                "source_section": "3.2",
            },
        }
        action = _build_action(decision, [])
        docs = action["documentation"]
        assert len(docs) == 1
        assert docs[0]["type"] == "citation"
        assert docs[0]["citation"] == "Exact quote"
        assert docs[0]["label"] == "3.2"

    def test_no_documentation_when_no_source_text(self):
        decision = {
            "id": "n",
            "description": "",
            "conditions": [],
            "recommendation": {"action": "A"},
        }
        action = _build_action(decision, [])
        assert action["documentation"] == []

    def test_evidence_grade_extension(self):
        decision = {
            "id": "n",
            "description": "",
            "conditions": [],
            "recommendation": {
                "action": "A",
                "evidence_grade": "A",
                "strength": "strong",
            },
        }
        action = _build_action(decision, [])
        ext = action["extension"][0]
        assert "strengthOfRecommendation" in ext["url"]
        assert "strong" in ext["valueCodeableConcept"]["text"]
        assert "A" in ext["valueCodeableConcept"]["text"]

    def test_branches_mapped_to_related_actions(self):
        decision = {
            "id": "n",
            "description": "",
            "conditions": [],
            "recommendation": {"action": "A"},
            "branches": [
                {
                    "condition": {"field": "x", "operator": "eq", "value": "y"},
                    "next_decision": "target_node",
                    "label": "If x is y",
                }
            ],
        }
        action = _build_action(decision, [])
        ra = action["relatedAction"]
        assert len(ra) == 1
        assert ra[0]["actionId"] == "target_node"
        assert ra[0]["relationship"] == "before-start"

    def test_sequence_mapped_to_grouped_actions(self):
        decision = {
            "id": "seq",
            "description": "",
            "conditions": [],
            "recommendation": {"action": "A"},
            "sequence": ["step_1", "step_2"],
        }
        action = _build_action(decision, [])
        assert action["groupingBehavior"] == "sequential-group"
        assert action["selectionBehavior"] == "all"
        assert len(action["action"]) == 2

    def test_conditions_mapped_to_applicability(self):
        decision = {
            "id": "n",
            "description": "",
            "conditions": [
                {"field": "diagnosis", "operator": "eq", "value": "ADHD"},
                {"field": "age", "operator": "gt", "value": 18},
            ],
            "recommendation": {"action": "A"},
        }
        action = _build_action(decision, [])
        assert len(action["condition"]) == 2
        assert all(c["kind"] == "applicability" for c in action["condition"])


class TestBuildConditions:
    """Tests for FHIR condition expression building."""

    def test_eq_operator(self):
        result = _build_conditions([{"field": "diagnosis", "operator": "eq", "value": "ADHD"}])
        assert len(result) == 1
        expr = result[0]["expression"]
        assert expr["language"] == "text/herald-condition"
        assert "diagnosis = ADHD" in expr["expression"]

    def test_gt_operator(self):
        result = _build_conditions([{"field": "age", "operator": "gt", "value": 18}])
        assert "> 18" in result[0]["expression"]["expression"]

    def test_contains_operator(self):
        cond = [{"field": "comorbidities", "operator": "contains", "value": "anxiety"}]
        result = _build_conditions(cond)
        assert "contains" in result[0]["expression"]["expression"]

    def test_in_operator_with_list_value(self):
        result = _build_conditions([
            {"field": "status", "operator": "in", "value": ["active", "remission"]}
        ])
        expr_text = result[0]["expression"]["expression"]
        assert "in" in expr_text
        assert '["active", "remission"]' in expr_text

    def test_exists_operator(self):
        result = _build_conditions([{"field": "allergy", "operator": "exists", "value": True}])
        assert "exists" in result[0]["expression"]["expression"]

    def test_empty_conditions(self):
        assert _build_conditions([]) == []


class TestBuildInputs:
    """Tests for patient field → FHIR input mapping."""

    def test_basic_field_mapping(self):
        fields = [{"field": "age", "type": "number", "description": "Patient age"}]
        result = _build_inputs(fields)
        assert len(result) == 1
        assert result[0]["id"] == "age"
        assert result[0]["type"] == "decimal"
        assert result[0]["profile"] == ["Patient age"]

    def test_code_filter_when_code_present(self):
        fields = [{
            "field": "diagnosis",
            "type": "string",
            "code": {"system": "http://snomed.info/sct", "code": "406506008", "display": "ADHD"},
        }]
        result = _build_inputs(fields)
        cf = result[0]["codeFilter"]
        assert len(cf) == 1
        assert cf[0]["code"][0]["system"] == "http://snomed.info/sct"
        assert cf[0]["code"][0]["code"] == "406506008"

    def test_no_code_filter_without_code(self):
        fields = [{"field": "age", "type": "number"}]
        result = _build_inputs(fields)
        assert "codeFilter" not in result[0]

    def test_empty_fields(self):
        assert _build_inputs([]) == []


class TestMapType:
    """Tests for Herald → FHIR type mapping."""

    def test_string(self):
        assert _map_type("string") == "string"

    def test_enum(self):
        assert _map_type("enum") == "code"

    def test_bool(self):
        assert _map_type("bool") == "boolean"

    def test_number(self):
        assert _map_type("number") == "decimal"

    def test_list_string(self):
        assert _map_type("list[string]") == "string"

    def test_list_object(self):
        assert _map_type("list[object]") == "BackboneElement"

    def test_unknown_falls_back_to_string(self):
        assert _map_type("complex_custom_type") == "string"


class TestCleanNone:
    """Tests for recursive None/empty removal."""

    def test_removes_none_values(self):
        assert _clean_none({"a": 1, "b": None}) == {"a": 1}

    def test_removes_empty_lists(self):
        assert _clean_none({"a": [], "b": [1]}) == {"b": [1]}

    def test_removes_empty_dicts(self):
        assert _clean_none({"a": {}, "b": {"x": 1}}) == {"b": {"x": 1}}

    def test_removes_none_from_lists(self):
        assert _clean_none([1, None, 3]) == [1, 3]

    def test_nested_cleaning(self):
        data = {"a": {"b": None, "c": {"d": None, "e": 5}}, "f": []}
        result = _clean_none(data)
        assert result == {"a": {"c": {"e": 5}}}

    def test_preserves_falsy_but_valid_values(self):
        result = _clean_none({"a": 0, "b": False, "c": ""})
        assert result == {"a": 0, "b": False, "c": ""}

    def test_scalar_passthrough(self):
        assert _clean_none(42) == 42
        assert _clean_none("hello") == "hello"


def _assert_no_nones(obj, path="root"):
    """Recursively assert no None values exist."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert v is not None, f"None found at {path}.{k}"
            _assert_no_nones(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            assert item is not None, f"None found at {path}[{i}]"
            _assert_no_nones(item, f"{path}[{i}]")
