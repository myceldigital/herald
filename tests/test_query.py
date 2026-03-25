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

    def test_hyphenated_year_old_age(self):
        patient = parse_patient_description("35-year-old adult with anxiety")
        assert patient.get("age") == 35

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

    def test_guideline_parser_prefers_canonical_enum_value_over_known_value(self):
        guideline = {
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["ADHD"],
                    "known_values": ["ADHD", "attention deficit hyperactivity disorder"],
                },
            ],
            "field_synonyms": {
                "ADHD": ["attention deficit hyperactivity disorder"],
            },
        }

        patient = parse_patient_description(
            "10-year-old child with attention deficit hyperactivity disorder",
            guideline=guideline,
        )

        assert patient.get("diagnosis") == "ADHD"

    def test_guideline_parser_scopes_missing_fields_to_relevant_module(self):
        guideline = {
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["generalized_anxiety_disorder", "bipolar_disorder"],
                    "known_values": ["generalized_anxiety_disorder", "bipolar_disorder"],
                },
                {
                    "field": "age_group",
                    "type": "enum",
                    "required": True,
                    "values": ["adult"],
                    "known_values": ["adult"],
                },
                {
                    "field": "bipolar_episode_type",
                    "type": "enum",
                    "required": True,
                    "values": ["manic", "depressive"],
                    "known_values": ["manic", "depressive"],
                },
                {
                    "field": "self_harm_history",
                    "type": "bool",
                    "required": True,
                    "values": None,
                    "known_values": None,
                },
            ],
            "field_synonyms": {
                "generalized_anxiety_disorder": ["generalized anxiety disorder"],
                "bipolar_disorder": ["bipolar disorder"],
            },
            "decisions": [
                {
                    "id": "anxiety_root",
                    "entry_point": True,
                    "conditions": [
                        {
                            "field": "diagnosis",
                            "operator": "eq",
                            "value": "generalized_anxiety_disorder",
                        },
                        {"field": "age_group", "operator": "eq", "value": "adult"},
                    ],
                    "recommendation": {
                        "action": "Treat anxiety",
                        "source_section": "1",
                        "source_text": "A",
                    },
                    "branches": [],
                },
                {
                    "id": "bipolar_root",
                    "entry_point": True,
                    "conditions": [
                        {"field": "diagnosis", "operator": "eq", "value": "bipolar_disorder"},
                        {"field": "bipolar_episode_type", "operator": "eq", "value": "manic"},
                    ],
                    "recommendation": {
                        "action": "Treat bipolar mania",
                        "source_section": "2",
                        "source_text": "B",
                    },
                    "branches": [],
                },
            ],
        }

        patient = parse_patient_description(
            "35F generalized anxiety disorder",
            guideline=guideline,
        )
        meta = patient.get("_extraction_meta", {})

        assert patient.get("diagnosis") == "generalized_anxiety_disorder"
        assert "bipolar_episode_type" not in meta
        assert "self_harm_history" not in meta

    def test_guideline_parser_keeps_relevant_required_fields_in_scope(self):
        guideline = {
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["bipolar_disorder"],
                    "known_values": ["bipolar_disorder"],
                },
                {
                    "field": "bipolar_episode_type",
                    "type": "enum",
                    "required": True,
                    "values": ["manic", "depressive"],
                    "known_values": ["manic", "depressive"],
                },
            ],
            "field_synonyms": {
                "bipolar_disorder": ["bipolar disorder"],
            },
            "decisions": [
                {
                    "id": "bipolar_root",
                    "entry_point": True,
                    "conditions": [
                        {"field": "diagnosis", "operator": "eq", "value": "bipolar_disorder"},
                        {"field": "bipolar_episode_type", "operator": "eq", "value": "manic"},
                    ],
                    "recommendation": {
                        "action": "Treat bipolar mania",
                        "source_section": "2",
                        "source_text": "B",
                    },
                    "branches": [],
                },
            ],
        }

        patient = parse_patient_description(
            "42M bipolar disorder",
            guideline=guideline,
        )
        meta = patient.get("_extraction_meta", {})

        assert patient.get("diagnosis") == "bipolar_disorder"
        assert meta["bipolar_episode_type"]["source"] == "missing"

    def test_guideline_parser_derives_age_years_when_relevant(self):
        guideline = {
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["generalized_anxiety_disorder"],
                    "known_values": ["generalized_anxiety_disorder"],
                },
                {
                    "field": "age_years",
                    "type": "number",
                    "required": True,
                    "values": None,
                    "known_values": None,
                },
            ],
            "field_synonyms": {
                "generalized_anxiety_disorder": ["generalized anxiety disorder"],
            },
            "decisions": [
                {
                    "id": "adult_anxiety",
                    "entry_point": True,
                    "conditions": [
                        {
                            "field": "diagnosis",
                            "operator": "eq",
                            "value": "generalized_anxiety_disorder",
                        },
                        {"field": "age_years", "operator": "gte", "value": 18},
                    ],
                    "recommendation": {
                        "action": "Adult anxiety treatment",
                        "source_section": "1",
                        "source_text": "A",
                    },
                    "branches": [],
                },
            ],
        }

        patient = parse_patient_description(
            "35F generalized anxiety disorder",
            guideline=guideline,
        )

        assert patient.get("age_years") == 35

    def test_guideline_parser_does_not_follow_unknown_branches(self):
        guideline = {
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["bipolar_disorder"],
                    "known_values": ["bipolar_disorder"],
                },
                {
                    "field": "bipolar_episode_type",
                    "type": "enum",
                    "required": True,
                    "values": ["manic", "depressive"],
                    "known_values": ["manic", "depressive"],
                },
                {
                    "field": "childbearing_potential",
                    "type": "bool",
                    "required": True,
                    "values": None,
                    "known_values": None,
                },
            ],
            "field_synonyms": {
                "bipolar_disorder": ["bipolar disorder"],
            },
            "decisions": [
                {
                    "id": "bipolar_root",
                    "entry_point": True,
                    "conditions": [
                        {"field": "diagnosis", "operator": "eq", "value": "bipolar_disorder"},
                    ],
                    "recommendation": {
                        "action": "Initial bipolar assessment",
                        "source_section": "1",
                        "source_text": "A",
                    },
                    "branches": [
                        {
                            "condition": {
                                "field": "bipolar_episode_type",
                                "operator": "eq",
                                "value": "manic",
                            },
                            "next_decision": "mania_branch",
                        }
                    ],
                },
                {
                    "id": "mania_branch",
                    "entry_point": False,
                    "conditions": [
                        {"field": "childbearing_potential", "operator": "eq", "value": True},
                    ],
                    "recommendation": {
                        "action": "Escalate mania treatment",
                        "source_section": "2",
                        "source_text": "B",
                    },
                    "branches": [],
                },
            ],
        }

        patient = parse_patient_description(
            "42M bipolar disorder",
            guideline=guideline,
        )
        meta = patient.get("_extraction_meta", {})

        assert "bipolar_episode_type" in meta
        assert "childbearing_potential" not in meta

    def test_guideline_parser_derives_bipolar_condition_phrase(self):
        guideline = {
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["bipolar_disorder"],
                    "known_values": ["bipolar_disorder"],
                },
                {
                    "field": "condition",
                    "type": "enum",
                    "required": False,
                    "values": ["bipolar disorder current episode mania"],
                    "known_values": ["bipolar disorder current episode mania"],
                },
            ],
            "field_synonyms": {
                "bipolar_disorder": ["bipolar disorder"],
            },
            "decisions": [
                {
                    "id": "bipolar_mania",
                    "entry_point": True,
                    "conditions": [
                        {
                            "field": "condition",
                            "operator": "eq",
                            "value": "bipolar disorder current episode mania",
                        },
                    ],
                    "recommendation": {
                        "action": "Treat bipolar mania",
                        "source_section": "1",
                        "source_text": "A",
                    },
                    "branches": [],
                },
            ],
        }

        patient = parse_patient_description(
            "28-year-old adult with bipolar disorder and manic episode",
            guideline=guideline,
        )

        assert patient.get("condition") == "bipolar disorder current episode mania"

    def test_guideline_parser_prefers_condition_specific_scope_over_generic_diagnosis(self):
        guideline = {
            "patient_fields": [
                {
                    "field": "diagnosis",
                    "type": "enum",
                    "required": True,
                    "values": ["bipolar_disorder"],
                    "known_values": ["bipolar_disorder"],
                },
                {
                    "field": "condition",
                    "type": "enum",
                    "required": False,
                    "values": ["bipolar disorder current episode mania"],
                    "known_values": ["bipolar disorder current episode mania"],
                },
                {
                    "field": "phase",
                    "type": "enum",
                    "required": True,
                    "values": ["remission"],
                    "known_values": ["remission"],
                },
            ],
            "field_synonyms": {
                "bipolar_disorder": ["bipolar disorder"],
            },
            "decisions": [
                {
                    "id": "mania_path",
                    "entry_point": True,
                    "conditions": [
                        {
                            "field": "condition",
                            "operator": "eq",
                            "value": "bipolar disorder current episode mania",
                        },
                    ],
                    "recommendation": {
                        "action": "Treat mania",
                        "source_section": "1",
                        "source_text": "A",
                    },
                    "branches": [],
                },
                {
                    "id": "remission_path",
                    "entry_point": True,
                    "conditions": [
                        {"field": "diagnosis", "operator": "eq", "value": "bipolar_disorder"},
                        {"field": "phase", "operator": "eq", "value": "remission"},
                    ],
                    "recommendation": {
                        "action": "Treat remission",
                        "source_section": "2",
                        "source_text": "B",
                    },
                    "branches": [],
                },
            ],
        }

        patient = parse_patient_description(
            "28-year-old adult with bipolar disorder and manic episode",
            guideline=guideline,
        )
        meta = patient.get("_extraction_meta", {})

        assert patient.get("condition") == "bipolar disorder current episode mania"
        assert "phase" not in meta
