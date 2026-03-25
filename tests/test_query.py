"""Tests for the query engine — deterministic tree traversal."""

import json
from pathlib import Path

import pytest

from herald_cli.query import QueryEngine, parse_patient_description

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


@pytest.fixture
def adhd_engine():
    """Load the synthetic ADHD guideline."""
    path = EXAMPLES_DIR / "synthetic_adhd_guideline.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return QueryEngine(data)


class TestQueryEngine:
    """Tests for deterministic decision tree traversal."""

    def test_any_match_supports_scalar_membership(self):
        engine = QueryEngine(
            {
                "guideline": {"title": "Test"},
                "decisions": [
                    {
                        "id": "root",
                        "entry_point": True,
                        "conditions": [
                            {
                                "field": "age_group",
                                "operator": "any_match",
                                "value": ["child", "adolescent"],
                            }
                        ],
                        "recommendation": {
                            "action": "Offer child pathway",
                            "source_section": "1",
                            "source_text": "Offer child pathway.",
                        },
                        "branches": [],
                    }
                ],
            }
        )

        results = engine.query({"age_group": "child"})

        assert len(results) == 1
        assert results[0]["recommendation"]["action"] == "Offer child pathway"

    def test_eq_supports_composite_enum_values(self):
        engine = QueryEngine(
            {
                "guideline": {"title": "Test"},
                "decisions": [
                    {
                        "id": "root",
                        "entry_point": True,
                        "conditions": [
                            {
                                "field": "age_group",
                                "operator": "eq",
                                "value": "children_and_adolescents",
                            }
                        ],
                        "recommendation": {
                            "action": "Offer ADHD pathway",
                            "source_section": "1",
                            "source_text": "Offer ADHD pathway.",
                        },
                        "branches": [],
                    }
                ],
            }
        )

        results = engine.query({"age_group": "children"})

        assert len(results) == 1
        assert results[0]["recommendation"]["action"] == "Offer ADHD pathway"

    def test_basic_adhd_adult_returns_first_line(self, adhd_engine):
        patient = {"diagnosis": "ADHD", "age_group": "adult"}
        results = adhd_engine.query(patient)
        assert len(results) >= 1
        actions = [r["recommendation"]["action"] for r in results]
        assert any("methylphenidate" in a.lower() for a in actions)

    def test_adhd_with_anxiety_routes_correctly(self, adhd_engine):
        patient = {
            "diagnosis": "ADHD",
            "age_group": "adult",
            "comorbidities": ["anxiety"],
        }
        results = adhd_engine.query(patient)
        assert len(results) >= 1
        actions = " ".join(r["recommendation"]["action"] for r in results)
        assert "atomoxetine" in actions.lower() or "ssri" in actions.lower()

    def test_adhd_with_substance_use_avoids_stimulants_first(self, adhd_engine):
        patient = {
            "diagnosis": "ADHD",
            "age_group": "adult",
            "comorbidities": ["substance_use"],
        }
        results = adhd_engine.query(patient)
        # Should recommend non-stimulant first
        top_action = results[0]["recommendation"]["action"]
        assert "atomoxetine" in top_action.lower()

    def test_adhd_cardiac_requires_screening(self, adhd_engine):
        patient = {
            "diagnosis": "ADHD",
            "age_group": "adult",
            "comorbidities": ["cardiac_history"],
        }
        results = adhd_engine.query(patient)
        actions = " ".join(r["recommendation"]["action"] for r in results)
        assert "ecg" in actions.lower() or "cardiol" in actions.lower()

    def test_pregnancy_contraindication(self, adhd_engine):
        patient = {
            "diagnosis": "ADHD",
            "age_group": "adult",
            "contraindications": ["pregnancy"],
        }
        results = adhd_engine.query(patient)
        actions = " ".join(r["recommendation"]["action"] for r in results)
        assert "discontinue" in actions.lower() or "pregnancy" in actions.lower()

    def test_treatment_failure_pathway(self, adhd_engine):
        patient = {
            "diagnosis": "ADHD",
            "age_group": "adult",
            "prior_treatments": [
                {"medication": "concerta", "class": "stimulant_mph", "response": "none"}
            ],
        }
        results = adhd_engine.query(patient)
        actions = " ".join(r["recommendation"]["action"] for r in results)
        assert "lisdexamfetamine" in actions.lower() or "amphetamine" in actions.lower()

    def test_all_recommendations_have_source_citations(self, adhd_engine):
        patient = {"diagnosis": "ADHD", "age_group": "adult"}
        results = adhd_engine.query(patient)
        for r in results:
            rec = r["recommendation"]
            assert rec.get("source_section"), f"Missing source_section in {r['decision_id']}"
            assert rec.get("source_text"), f"Missing source_text in {r['decision_id']}"

    def test_empty_patient_returns_no_results(self, adhd_engine):
        results = adhd_engine.query({})
        assert results == []

    def test_wrong_diagnosis_returns_no_results(self, adhd_engine):
        patient = {"diagnosis": "diabetes", "age_group": "adult"}
        results = adhd_engine.query(patient)
        assert results == []

    def test_results_sorted_by_specificity(self, adhd_engine):
        patient = {
            "diagnosis": "ADHD",
            "age_group": "adult",
            "comorbidities": ["anxiety"],
        }
        results = adhd_engine.query(patient)
        if len(results) >= 2:
            specificities = [r["specificity"] for r in results]
            assert specificities == sorted(specificities, reverse=True)

    def test_decision_path_tracked(self, adhd_engine):
        patient = {
            "diagnosis": "ADHD",
            "age_group": "adult",
            "comorbidities": ["anxiety"],
        }
        results = adhd_engine.query(patient)
        for r in results:
            assert "path" in r
            assert len(r["path"]) >= 1


class TestPatientDescriptionParser:
    """Tests for natural language patient description parsing."""

    def test_basic_demographics(self):
        patient = parse_patient_description("34F, ADHD confirmed")
        assert patient.get("age") == 34
        assert patient.get("sex") == "female"
        assert patient.get("age_group") == "adult"
        assert patient.get("diagnosis") == "ADHD"

    def test_male_shorthand(self):
        patient = parse_patient_description("28M ADHD")
        assert patient.get("sex") == "male"
        assert patient.get("age") == 28

    def test_comorbidities_extracted(self):
        patient = parse_patient_description("Adult with ADHD, comorbid anxiety and depression")
        assert "anxiety" in patient.get("comorbidities", [])
        assert "depression" in patient.get("comorbidities", [])

    def test_prior_treatment_extracted(self):
        patient = parse_patient_description("ADHD, tried methylphenidate with partial response")
        treatments = patient.get("prior_treatments", [])
        assert len(treatments) >= 1
        assert treatments[0]["medication"] == "methylphenidate"
        assert treatments[0]["response"] == "partial"
        assert treatments[0]["class"] == "stimulant_mph"

    def test_cardiac_contraindication(self):
        patient = parse_patient_description("ADHD with cardiac history")
        assert "cardiac_history" in patient.get("comorbidities", []) or \
               "cardiac_history" in patient.get("contraindications", [])

    def test_pregnancy(self):
        patient = parse_patient_description("29F ADHD, pregnant")
        assert "pregnancy" in patient.get("contraindications", [])

    def test_medication_classification(self):
        patient = parse_patient_description("tried concerta and elvanse")
        treatments = patient.get("prior_treatments", [])
        classes = {t["class"] for t in treatments}
        assert "stimulant_mph" in classes
        assert "stimulant_amp" in classes

    def test_elderly_age_group(self):
        patient = parse_patient_description("72M ADHD")
        assert patient.get("age_group") == "elderly"

    def test_child_age_group(self):
        patient = parse_patient_description("8M ADHD")
        assert patient.get("age_group") == "child"

    def test_guideline_parser_handles_null_known_values(self):
        guideline = {
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["adhd"],
                    "known_values": ["adhd"],
                },
                {
                    "field": "childbearing_potential",
                    "type": "bool",
                    "required": False,
                    "values": None,
                    "known_values": None,
                },
            ],
            "field_synonyms": {
                "adhd": ["attention deficit hyperactivity disorder"],
                "childbearing_potential": ["of childbearing potential"],
            },
        }

        patient = parse_patient_description(
            "8M attention deficit hyperactivity disorder",
            guideline=guideline,
        )

        assert patient.get("diagnosis") == "adhd"
        assert patient.get("age_group") == "child"

    def test_guideline_parser_aligns_enum_values_to_guideline_vocab(self):
        guideline = {
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["generalized_anxiety_disorder", "panic_disorder"],
                    "known_values": ["generalized_anxiety_disorder", "panic_disorder"],
                },
                {
                    "field": "age_group",
                    "type": "enum",
                    "required": True,
                    "values": ["children", "adolescents", "adults"],
                    "known_values": ["children", "adolescents", "adults"],
                },
            ],
            "field_synonyms": {
                "panic_disorder": ["panic attacks"],
            },
        }

        patient = parse_patient_description(
            "35F generalized anxiety disorder with panic attacks",
            guideline=guideline,
        )

        assert patient.get("diagnosis") == "generalized_anxiety_disorder"
        assert patient.get("age_group") == "adults"
