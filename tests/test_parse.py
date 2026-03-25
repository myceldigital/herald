"""Tests for the parse module — schema models and validation."""

import json

import pytest

from herald_cli.parse import (
    Branch,
    Condition,
    DecisionNode,
    GuidelineDecisionTree,
    GuidelineMeta,
    PatientField,
    Recommendation,
    _extract_json_payload,
    _merge_chunk_trees,
    _sanitize_llm_tree_data,
    _split_guideline_into_chunks,
    _validate_references,
    parse_guideline,
)


class TestSchemaModels:
    """Tests for Pydantic schema models."""

    def test_minimal_decision_node(self):
        node = DecisionNode(
            id="test_node",
            recommendation=Recommendation(action="Do something"),
        )
        assert node.id == "test_node"
        assert node.entry_point is False
        assert node.conditions == []
        assert node.branches == []

    def test_full_decision_node(self):
        node = DecisionNode(
            id="full_node",
            description="A complete node",
            entry_point=True,
            conditions=[Condition(field="diagnosis", operator="eq", value="ADHD")],
            recommendation=Recommendation(
                action="Start treatment",
                evidence_grade="A",
                strength="strong",
                monitoring="Check BP weekly",
                source_section="4.1",
                source_page=18,
                source_text="Treatment should be started...",
            ),
            branches=[
                Branch(
                    condition=Condition(field="age_group", operator="eq", value="child"),
                    next_decision="child_pathway",
                    label="Patient is a child",
                )
            ],
        )
        assert node.entry_point is True
        assert len(node.conditions) == 1
        assert node.recommendation.evidence_grade == "A"
        assert len(node.branches) == 1

    def test_patient_field_enum(self):
        field = PatientField(
            field="age_group",
            type="enum",
            required=True,
            description="Age category",
            values=["child", "adolescent", "adult", "elderly"],
        )
        assert field.required is True
        assert len(field.values) == 4

    def test_guideline_meta(self):
        meta = GuidelineMeta(
            title="Test Guideline",
            source="Test Body",
            condition="ADHD",
            population="Adults",
        )
        assert meta.title == "Test Guideline"

    def test_full_tree_serialization(self):
        tree = GuidelineDecisionTree(
            guideline=GuidelineMeta(title="Test", source="Test"),
            patient_fields=[
                PatientField(field="diagnosis", type="string", required=True)
            ],
            field_synonyms={"adhd": ["attention deficit hyperactivity disorder"]},
            decisions=[
                DecisionNode(
                    id="root",
                    entry_point=True,
                    conditions=[Condition(field="diagnosis", operator="eq", value="ADHD")],
                    recommendation=Recommendation(action="Treat"),
                )
            ],
        )
        data = tree.model_dump(mode="json")
        assert data["schema_version"] == "0.1"
        assert data["field_synonyms"]["adhd"] == ["attention deficit hyperactivity disorder"]
        assert len(data["decisions"]) == 1
        assert data["decisions"][0]["id"] == "root"


class TestJsonExtraction:
    """Tests for cleaning model responses down to JSON."""

    def test_extracts_fenced_json_after_preamble(self):
        payload = (
            "{\"schema_version\": \"0.1\", "
            "\"guideline\": {\"title\": \"Test\", \"source\": \"WHO\"}, "
            "\"patient_fields\": [], "
            "\"field_synonyms\": {}, "
            "\"decisions\": []}"
        )
        raw = (
            "I will now return the parsed structure.\n\n"
            "```json\n"
            f"{payload}\n"
            "```"
        )
        cleaned = _extract_json_payload(raw)
        assert cleaned.startswith("{")
        assert cleaned.endswith("}")
        assert "\"schema_version\": \"0.1\"" in cleaned

    def test_extracts_outer_json_without_fence(self):
        payload = (
            "{\"schema_version\": \"0.1\", "
            "\"guideline\": {\"title\": \"Test\", \"source\": \"WHO\"}, "
            "\"patient_fields\": [], "
            "\"field_synonyms\": {}, "
            "\"decisions\": []}"
        )
        raw = (
            "Here is the JSON you asked for:\n"
            f"{payload}\n"
            "Thanks."
        )
        cleaned = _extract_json_payload(raw)
        assert cleaned.startswith("{")
        assert cleaned.endswith("}")
        assert "\"decisions\": []" in cleaned


class TestSanitization:
    """Tests for pre-validation cleanup of common LLM output mistakes."""

    def test_bool_patient_fields_drop_values_arrays(self):
        data = {
            "schema_version": "0.1",
            "guideline": {"title": "Test", "source": "WHO"},
            "patient_fields": [
                {
                    "field": "specialist_available",
                    "type": "bool",
                    "required": False,
                    "values": [True, False],
                    "known_values": [True, False],
                }
            ],
            "field_synonyms": {},
            "decisions": [],
        }

        cleaned = _sanitize_llm_tree_data(data)

        assert cleaned["patient_fields"][0]["values"] is None
        assert cleaned["patient_fields"][0]["known_values"] is None

    def test_recommendation_string_fields_default_from_null(self):
        data = {
            "schema_version": "0.1",
            "guideline": {"title": "Test", "source": "WHO"},
            "patient_fields": [],
            "field_synonyms": {},
            "decisions": [
                {
                    "id": "node",
                    "description": None,
                    "conditions": [],
                    "recommendation": {
                        "action": "Do thing",
                        "evidence_grade": None,
                        "strength": None,
                        "source_section": None,
                        "source_text": None,
                    },
                    "branches": [],
                }
            ],
        }

        cleaned = _sanitize_llm_tree_data(data)
        rec = cleaned["decisions"][0]["recommendation"]

        assert cleaned["decisions"][0]["description"] == ""
        assert rec["evidence_grade"] == ""
        assert rec["strength"] == ""
        assert rec["source_section"] == ""
        assert rec["source_text"] == ""


class TestChunkingAndMerge:
    """Tests for large-guideline chunk parsing helpers."""

    def test_split_guideline_into_recommendation_chunks(self):
        markdown = """
Title

1. Introduction

Background text

3. Recommendations

3.1 Anxiety

Recommendation A.

3.2 Depression

Recommendation B.

4. Publication

Administrative appendix
""".strip()

        chunks = _split_guideline_into_chunks(markdown)

        assert len(chunks) == 2
        assert chunks[0][0] == "3.1 Anxiety"
        assert "Recommendation A." in chunks[0][1]
        assert chunks[1][0] == "3.2 Depression"
        assert "4. Publication" not in chunks[1][1]

    def test_merge_chunk_trees_renames_conflicting_decision_ids(self):
        chunk_a = {
            "guideline": {"title": "Test", "source": "WHO"},
            "patient_fields": [{"field": "diagnosis", "type": "enum", "values": ["anxiety"]}],
            "field_synonyms": {"anxiety": ["gad"]},
            "decisions": [
                {
                    "id": "first_line",
                    "description": "Chunk A root",
                    "entry_point": True,
                    "conditions": [{"field": "diagnosis", "operator": "eq", "value": "anxiety"}],
                    "recommendation": {
                        "action": "A",
                        "source_section": "3.1",
                        "source_text": "A text",
                    },
                    "branches": [],
                },
                {
                    "id": "follow_up",
                    "description": "Chunk A follow up",
                    "entry_point": False,
                    "conditions": [{"field": "diagnosis", "operator": "eq", "value": "anxiety"}],
                    "recommendation": {
                        "action": "A2",
                        "source_section": "3.1",
                        "source_text": "A2 text",
                    },
                    "branches": [],
                },
            ],
        }
        chunk_b = {
            "guideline": {"title": "Test", "source": "WHO"},
            "patient_fields": [{"field": "severity", "type": "enum", "values": ["moderate"]}],
            "field_synonyms": {"moderate": ["mid"]},
            "decisions": [
                {
                    "id": "first_line",
                    "description": "Chunk B root",
                    "entry_point": True,
                    "conditions": [{"field": "severity", "operator": "eq", "value": "moderate"}],
                    "recommendation": {
                        "action": "B",
                        "source_section": "3.2",
                        "source_text": "B text",
                    },
                    "branches": [
                        {
                            "condition": {
                                "field": "severity",
                                "operator": "eq",
                                "value": "moderate",
                            },
                            "next_decision": "follow_up",
                            "label": "continue",
                        }
                    ],
                },
                {
                    "id": "follow_up",
                    "description": "Chunk B follow up",
                    "entry_point": False,
                    "conditions": [{"field": "severity", "operator": "eq", "value": "moderate"}],
                    "recommendation": {
                        "action": "B2",
                        "source_section": "3.2",
                        "source_text": "B2 text",
                    },
                    "branches": [],
                },
            ],
        }

        merged = _merge_chunk_trees([chunk_a, chunk_b])
        decision_ids = {d["id"] for d in merged["decisions"]}

        assert "first_line" in decision_ids
        assert "follow_up" in decision_ids
        renamed_first = next(d for d in merged["decisions"] if d["recommendation"]["action"] == "B")
        renamed_follow = next(
            d for d in merged["decisions"] if d["recommendation"]["action"] == "B2"
        )
        assert renamed_first["id"] != "first_line"
        assert renamed_follow["id"] != "follow_up"
        assert renamed_first["branches"][0]["next_decision"] == renamed_follow["id"]
        assert merged["field_synonyms"]["moderate"] == ["mid"]

    def test_merge_chunk_trees_demotes_subgroup_only_required_fields(self):
        chunk_a = {
            "guideline": {"title": "Test", "source": "WHO"},
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["anxiety"],
                },
                {
                    "field": "age_group",
                    "type": "enum",
                    "required": True,
                    "values": ["adult"],
                },
            ],
            "field_synonyms": {},
            "decisions": [
                {
                    "id": "anxiety_root",
                    "description": "Chunk A root",
                    "entry_point": True,
                    "conditions": [{"field": "diagnosis", "operator": "eq", "value": "anxiety"}],
                    "recommendation": {
                        "action": "A",
                        "source_section": "3.1",
                        "source_text": "A text",
                    },
                    "branches": [],
                }
            ],
        }
        chunk_b = {
            "guideline": {"title": "Test", "source": "WHO"},
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["bipolar_disorder"],
                },
                {
                    "field": "sex",
                    "type": "enum",
                    "required": True,
                    "values": ["female", "male"],
                },
                {
                    "field": "childbearing_potential",
                    "type": "bool",
                    "required": True,
                    "values": None,
                },
            ],
            "field_synonyms": {},
            "decisions": [
                {
                    "id": "bipolar_root",
                    "description": "Chunk B root",
                    "entry_point": True,
                    "conditions": [
                        {"field": "diagnosis", "operator": "eq", "value": "bipolar_disorder"},
                        {"field": "sex", "operator": "eq", "value": "female"},
                        {"field": "childbearing_potential", "operator": "eq", "value": True},
                    ],
                    "recommendation": {
                        "action": "B",
                        "source_section": "3.2",
                        "source_text": "B text",
                    },
                    "branches": [],
                }
            ],
        }

        merged = _merge_chunk_trees([chunk_a, chunk_b])
        by_name = {field["field"]: field for field in merged["patient_fields"]}

        assert by_name["diagnosis"]["required"] is True
        assert by_name["sex"]["required"] is False
        assert by_name["childbearing_potential"]["required"] is False

    def test_merge_chunk_trees_keeps_broadly_shared_required_fields(self):
        chunk_a = {
            "guideline": {"title": "Test", "source": "WHO"},
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["anxiety"],
                },
                {
                    "field": "age_group",
                    "type": "enum",
                    "required": True,
                    "values": ["adult"],
                },
            ],
            "field_synonyms": {},
            "decisions": [],
        }
        chunk_b = {
            "guideline": {"title": "Test", "source": "WHO"},
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["depression"],
                },
                {
                    "field": "age_group",
                    "type": "enum",
                    "required": True,
                    "values": ["adult"],
                },
            ],
            "field_synonyms": {},
            "decisions": [],
        }
        chunk_c = {
            "guideline": {"title": "Test", "source": "WHO"},
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["bipolar_disorder"],
                },
                {
                    "field": "age_group",
                    "type": "enum",
                    "required": True,
                    "values": ["adult"],
                },
            ],
            "field_synonyms": {},
            "decisions": [],
        }

        merged = _merge_chunk_trees([chunk_a, chunk_b, chunk_c])
        by_name = {field["field"]: field for field in merged["patient_fields"]}

        assert by_name["diagnosis"]["required"] is True
        assert by_name["age_group"]["required"] is True

    def test_parse_guideline_uses_chunked_strategy_for_large_input(self, monkeypatch):
        markdown = """
Title

3. Recommendations

3.1 Anxiety

SSRIs should be considered for adults with anxiety.

3.2 Depression

Structured psychological interventions should be offered for adults with depression.
""".strip()

        monkeypatch.setattr("herald_cli.parse.CHUNK_PARSE_CHAR_THRESHOLD", 1)
        monkeypatch.setattr("herald_cli.parse.CHUNK_TARGET_CHARS", 80)

        def fake_call_provider(payload, provider, model):
            if "SECTION TO PARSE: 3.1 Anxiety" in payload:
                return json.dumps(
                    {
                        "schema_version": "0.1",
                        "guideline": {"title": "Test", "source": "WHO"},
                        "patient_fields": [
                            {
                                "field": "diagnosis",
                                "type": "enum",
                                "required": True,
                                "values": ["anxiety"],
                                "known_values": ["anxiety"],
                            }
                        ],
                        "field_synonyms": {"anxiety": ["gad"]},
                        "decisions": [
                            {
                                "id": "first_line",
                                "description": "Anxiety treatment",
                                "entry_point": True,
                                "conditions": [
                                    {"field": "diagnosis", "operator": "eq", "value": "anxiety"}
                                ],
                                "recommendation": {
                                    "action": "Use SSRIs",
                                    "source_section": "3.1",
                                    "source_text": "SSRIs should be considered.",
                                },
                                "branches": [],
                            }
                        ],
                    }
                )
            if "SECTION TO PARSE: 3.2 Depression" in payload:
                return json.dumps(
                    {
                        "schema_version": "0.1",
                        "guideline": {"title": "Test", "source": "WHO"},
                        "patient_fields": [
                            {
                                "field": "diagnosis",
                                "type": "enum",
                                "required": True,
                                "values": ["depression"],
                                "known_values": ["depression"],
                            }
                        ],
                        "field_synonyms": {"depression": ["low mood"]},
                        "decisions": [
                            {
                                "id": "first_line",
                                "description": "Depression treatment",
                                "entry_point": True,
                                "conditions": [
                                    {"field": "diagnosis", "operator": "eq", "value": "depression"}
                                ],
                                "recommendation": {
                                    "action": "Offer CBT",
                                    "source_section": "3.2",
                                        "source_text": (
                                            "Structured psychological interventions "
                                            "should be offered."
                                        ),
                                },
                                "branches": [],
                            }
                        ],
                    }
                )
            raise AssertionError(f"Unexpected payload: {payload[:120]}")

        monkeypatch.setattr("herald_cli.parse._call_provider", fake_call_provider)

        result = parse_guideline(markdown, provider="anthropic")

        assert result["parse_metadata"]["strategy"] == "chunked"
        assert result["parse_metadata"]["chunk_count"] == 2
        assert len(result["decisions"]) == 2
        assert result["field_synonyms"]["anxiety"] == ["gad"]
        assert result["field_synonyms"]["depression"] == ["low mood"]


class TestReferenceValidation:
    """Tests for internal reference validation."""

    def test_valid_references_pass(self):
        tree = GuidelineDecisionTree(
            guideline=GuidelineMeta(title="Test", source="Test"),
            decisions=[
                DecisionNode(
                    id="node_a",
                    recommendation=Recommendation(action="Do A"),
                    branches=[
                        Branch(
                            condition=Condition(field="x", operator="eq", value="y"),
                            next_decision="node_b",
                        )
                    ],
                ),
                DecisionNode(
                    id="node_b",
                    recommendation=Recommendation(action="Do B"),
                ),
            ],
        )
        _validate_references(tree)  # Should not raise

    def test_invalid_reference_raises(self):
        tree = GuidelineDecisionTree(
            guideline=GuidelineMeta(title="Test", source="Test"),
            decisions=[
                DecisionNode(
                    id="node_a",
                    recommendation=Recommendation(action="Do A"),
                    branches=[
                        Branch(
                            condition=Condition(field="x", operator="eq", value="y"),
                            next_decision="nonexistent_node",
                        )
                    ],
                ),
            ],
        )
        with pytest.raises(RuntimeError, match="nonexistent_node"):
            _validate_references(tree)

    def test_no_branches_passes(self):
        tree = GuidelineDecisionTree(
            guideline=GuidelineMeta(title="Test", source="Test"),
            decisions=[
                DecisionNode(
                    id="leaf",
                    recommendation=Recommendation(action="Terminal"),
                ),
            ],
        )
        _validate_references(tree)  # Should not raise
