"""Tests for the parse module — schema models and validation."""

import pytest

from herald_cli.parse import (
    Branch,
    Condition,
    DecisionNode,
    GuidelineDecisionTree,
    GuidelineMeta,
    PatientField,
    Recommendation,
    _validate_references,
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
        assert len(data["decisions"]) == 1
        assert data["decisions"][0]["id"] == "root"


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
