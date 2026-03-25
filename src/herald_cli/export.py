"""Export a Herald decision tree to FHIR CPG-on-FHIR PlanDefinition."""

from __future__ import annotations

import json
from datetime import date
from typing import Any


def export_fhir(decision_tree: dict) -> dict:
    """Convert a Herald decision tree to a FHIR PlanDefinition resource.

    Maps Herald schema to CPG-on-FHIR structure:
    - guideline → PlanDefinition metadata
    - decisions → action[]
    - conditions → action.condition[]
    - branches → action.relatedAction[]
    - patient_fields → input[]
    - field code mappings → using SNOMED/ICD codes when available
    """
    guideline = decision_tree.get("guideline", {})
    decisions = decision_tree.get("decisions", [])
    patient_fields = decision_tree.get("patient_fields", [])

    plan = {
        "resourceType": "PlanDefinition",
        "status": "active",
        "experimental": True,
        "title": guideline.get("title", ""),
        "description": guideline.get("population", ""),
        "date": guideline.get("last_updated", str(date.today())),
        "publisher": guideline.get("source", ""),
        "url": guideline.get("url"),
        "version": guideline.get("version", "0.1"),
        "type": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/plan-definition-type",
                "code": "clinical-protocol",
                "display": "Clinical Protocol",
            }]
        },
        "subjectCodeableConcept": {
            "text": guideline.get("condition", ""),
        },
        "useContext": [{
            "code": {
                "system": "http://terminology.hl7.org/CodeSystem/usage-context-type",
                "code": "focus",
            },
            "valueCodeableConcept": {
                "text": guideline.get("condition", ""),
            },
        }],
        "input": _build_inputs(patient_fields),
        "action": [_build_action(d, decisions) for d in decisions],
    }

    # Remove None values
    return _clean_none(plan)


def _build_inputs(patient_fields: list[dict]) -> list[dict]:
    """Convert patient_fields to FHIR input definitions."""
    inputs = []
    for field in patient_fields:
        inp: dict[str, Any] = {
            "id": field.get("field", ""),
            "type": _map_type(field.get("type", "string")),
        }
        if field.get("description"):
            inp["profile"] = [field["description"]]

        # Add coding if available (SNOMED support)
        code = field.get("code")
        if code:
            inp["codeFilter"] = [{
                "path": field.get("field", ""),
                "code": [{
                    "system": code.get("system", ""),
                    "code": code.get("code", ""),
                    "display": code.get("display", field.get("field", "")),
                }],
            }]

        inputs.append(inp)
    return inputs


def _build_action(decision: dict, all_decisions: list[dict]) -> dict:
    """Convert a single Herald decision node to a FHIR action."""
    rec = decision.get("recommendation", {})

    action: dict[str, Any] = {
        "id": decision.get("id", ""),
        "title": decision.get("description", ""),
        "description": rec.get("action", ""),
        "condition": _build_conditions(decision.get("conditions", [])),
        "documentation": [],
    }

    # Add evidence documentation
    if rec.get("source_text"):
        action["documentation"].append({
            "type": "citation",
            "label": rec.get("source_section", ""),
            "citation": rec.get("source_text", ""),
        })

    # Add evidence grade as extension
    if rec.get("evidence_grade"):
        action["extension"] = [{
            "url": "http://hl7.org/fhir/StructureDefinition/cqf-strengthOfRecommendation",
            "valueCodeableConcept": {
                "text": f"{rec.get('strength', 'conditional')} "
                        f"({rec.get('evidence_grade', '')})",
            },
        }]

    # Map branches to relatedAction
    branches = decision.get("branches", [])
    if branches:
        action["relatedAction"] = [
            {
                "actionId": b.get("next_decision", ""),
                "relationship": "before-start",
                "extension": [{
                    "url": "http://hl7.org/fhir/StructureDefinition/condition",
                    "valueString": b.get("label", ""),
                }],
            }
            for b in branches
        ]

    # Map sequence construct
    sequence = decision.get("sequence", [])
    if sequence:
        action["groupingBehavior"] = "sequential-group"
        action["selectionBehavior"] = "all"
        action["action"] = [
            {"id": step_id, "relatedAction": [
                {"actionId": step_id, "relationship": "before-start"}
            ]}
            for step_id in sequence
        ]

    return action


def _build_conditions(conditions: list[dict]) -> list[dict]:
    """Convert Herald conditions to FHIR applicability conditions."""
    fhir_conditions = []
    for cond in conditions:
        field = cond.get("field", "")
        op = cond.get("operator", "eq")
        value = cond.get("value")

        op_map = {
            "eq": "=", "neq": "!=", "gt": ">", "gte": ">=",
            "lt": "<", "lte": "<=", "in": "in", "not_in": "not in",
            "contains": "contains", "not_contains": "not contains",
            "exists": "exists",
        }
        op_str = op_map.get(op, op)
        value_str = json.dumps(value) if isinstance(value, list) else str(value)

        fhir_conditions.append({
            "kind": "applicability",
            "expression": {
                "language": "text/herald-condition",
                "expression": f"{field} {op_str} {value_str}",
            },
        })
    return fhir_conditions


def _map_type(herald_type: str) -> str:
    """Map Herald field types to FHIR types."""
    type_map = {
        "string": "string",
        "enum": "code",
        "bool": "boolean",
        "number": "decimal",
        "list[string]": "string",
        "list[object]": "BackboneElement",
    }
    return type_map.get(herald_type, "string")


def _clean_none(obj: Any) -> Any:
    """Recursively remove None values and empty lists from dicts."""
    if isinstance(obj, dict):
        return {
            k: _clean_none(v) for k, v in obj.items()
            if v is not None and v != [] and v != {}
        }
    if isinstance(obj, list):
        return [_clean_none(item) for item in obj if item is not None]
    return obj
