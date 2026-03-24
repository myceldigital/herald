"""Deterministic query engine for parsed guideline decision trees. No LLM required."""

from __future__ import annotations

import re
from typing import Any


class QueryEngine:
    """Traverse a parsed guideline decision tree given a patient profile.

    The engine walks the tree deterministically — no LLM is involved.
    Patient attributes are matched against decision node conditions,
    and matching recommendations are returned with full source citations.
    """

    def __init__(self, decision_tree: dict):
        self.tree = decision_tree
        self.guideline = decision_tree.get("guideline", {})
        self.patient_fields = decision_tree.get("patient_fields", [])
        self.decisions = {d["id"]: d for d in decision_tree.get("decisions", [])}

    def get_patient_fields(self) -> list[dict]:
        """Return the patient fields this guideline expects."""
        return self.patient_fields

    def query(self, patient: dict) -> list[dict]:
        """Query the decision tree with a patient profile.

        Args:
            patient: Dictionary of patient attributes matching the guideline's
                     patient_fields (e.g. {"diagnosis": "ADHD", "age_group": "adult"}).

        Returns:
            List of matching recommendations, each with:
            - recommendation: the clinical recommendation dict
            - decision_id: which node matched
            - path: list of decision IDs traversed to reach this recommendation
            - specificity: number of conditions matched (more = more specific)
        """
        results = []

        # Find entry points
        entry_points = [d for d in self.decisions.values() if d.get("entry_point")]

        # If no explicit entry points, treat all root-level nodes as entry points
        if not entry_points:
            referenced_ids = set()
            for d in self.decisions.values():
                for b in d.get("branches", []):
                    referenced_ids.add(b["next_decision"])
            entry_points = [d for d in self.decisions.values() if d["id"] not in referenced_ids]

        for entry in entry_points:
            self._traverse(entry["id"], patient, [], results)

        # Sort by specificity (more conditions matched = more specific = higher rank)
        results.sort(key=lambda r: r["specificity"], reverse=True)

        return results

    def _traverse(
        self,
        node_id: str,
        patient: dict,
        path: list[str],
        results: list[dict],
        depth: int = 0,
    ) -> None:
        """Recursively traverse the decision tree from a given node."""
        if depth > 50:
            return  # Prevent infinite loops in malformed trees

        node = self.decisions.get(node_id)
        if not node:
            return

        # Check if all conditions match
        conditions = node.get("conditions", [])
        if not _all_conditions_match(conditions, patient):
            return

        current_path = path + [node_id]

        # Check branches — if a more specific branch matches, follow it
        branch_followed = False
        for branch in node.get("branches", []):
            branch_cond = branch.get("condition", {})
            if _condition_matches(branch_cond, patient):
                self._traverse(
                    branch["next_decision"], patient, current_path, results, depth + 1
                )
                branch_followed = True

        # If no branch was followed, this node's recommendation is the answer
        if not branch_followed and node.get("recommendation"):
            results.append({
                "recommendation": node["recommendation"],
                "decision_id": node_id,
                "path": current_path,
                "specificity": len(conditions),
            })


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


def _all_conditions_match(conditions: list[dict], patient: dict) -> bool:
    """Check if ALL conditions match the patient profile (AND logic)."""
    if not conditions:
        return True
    return all(_condition_matches(c, patient) for c in conditions)


def _condition_matches(condition: dict, patient: dict) -> bool:
    """Evaluate a single condition against the patient profile."""
    field = condition.get("field", "")
    operator = condition.get("operator", "")
    expected = condition.get("value")

    actual = patient.get(field)

    if operator == "exists":
        has_value = actual is not None and actual != "" and actual != []
        return has_value == expected

    if actual is None:
        return False

    if operator == "eq":
        return _normalize(actual) == _normalize(expected)

    if operator == "neq":
        return _normalize(actual) != _normalize(expected)

    if operator == "contains":
        if isinstance(actual, list):
            return _normalize(expected) in [_normalize(v) for v in actual]
        if isinstance(actual, str):
            return _normalize(expected) in _normalize(actual)
        return False

    if operator == "not_contains":
        if isinstance(actual, list):
            return _normalize(expected) not in [_normalize(v) for v in actual]
        if isinstance(actual, str):
            return _normalize(expected) not in _normalize(actual)
        return True

    if operator in ("gt", "gte", "lt", "lte"):
        try:
            actual_num = float(actual)
            expected_num = float(expected)
        except (ValueError, TypeError):
            return False
        if operator == "gt":
            return actual_num > expected_num
        if operator == "gte":
            return actual_num >= expected_num
        if operator == "lt":
            return actual_num < expected_num
        if operator == "lte":
            return actual_num <= expected_num

    if operator == "any_match":
        if not isinstance(actual, list):
            return False
        sub_conditions = expected.get("conditions", []) if isinstance(expected, dict) else []
        return any(_all_conditions_match(sub_conditions, item) for item in actual)

    return False


def _normalize(value: Any) -> Any:
    """Normalize a value for comparison (lowercase strings)."""
    if isinstance(value, str):
        return value.lower().strip()
    return value


# ---------------------------------------------------------------------------
# Natural language patient description parser
# ---------------------------------------------------------------------------

# Common clinical terms mapped to structured fields
_AGE_PATTERNS = {
    r"\b(\d{1,3})\s*(?:year|yr|yo|y/o)": "age",
    r"\b(child|pediatric|paediatric)\b": ("age_group", "child"),
    r"\b(adolescent|teen)\b": ("age_group", "adolescent"),
    r"\b(adult)\b": ("age_group", "adult"),
    r"\b(elderly|geriatric|older adult)\b": ("age_group", "elderly"),
}

_SEX_PATTERNS = {
    r"\b(\d+)\s*[fF]\b": ("sex", "female"),
    r"\b(\d+)\s*[mM]\b": ("sex", "male"),
    r"\b(female|woman)\b": ("sex", "female"),
    r"\b(male|man)\b": ("sex", "male"),
}

_COMORBIDITY_KEYWORDS = [
    "anxiety", "depression", "bipolar", "substance use", "substance abuse",
    "cardiac", "cardiac history", "cardiovascular", "hypertension",
    "tics", "tourette", "asd", "autism", "epilepsy", "seizure",
    "sleep disorder", "insomnia", "obesity", "eating disorder",
    "personality disorder", "ptsd", "ocd",
]

_RESPONSE_KEYWORDS = {
    "no response": "none",
    "non-response": "none",
    "non-responder": "none",
    "partial response": "partial",
    "partial responder": "partial",
    "full response": "full",
    "good response": "full",
    "responded well": "full",
}

_MEDICATION_KEYWORDS = [
    "methylphenidate", "concerta", "ritalin", "equasym", "medikinet",
    "amphetamine", "elvanse", "vyvanse", "adderall", "dexamphetamine",
    "atomoxetine", "strattera", "lisdexamfetamine",
    "guanfacine", "intuniv", "clonidine",
    "bupropion", "wellbutrin",
    "sertraline", "fluoxetine", "citalopram", "escitalopram", "venlafaxine",
]


def parse_patient_description(text: str) -> dict:
    """Parse a natural language patient description into structured attributes.

    This is a best-effort parser for common clinical descriptions. It extracts:
    - Age and age group
    - Sex
    - Diagnosis
    - Comorbidities
    - Prior treatments and response
    - Contraindications

    Args:
        text: Natural language description like "34F, ADHD, comorbid anxiety,
              tried methylphenidate with partial response"

    Returns:
        Dictionary of patient attributes suitable for QueryEngine.query()
    """
    text_lower = text.lower()
    patient: dict[str, Any] = {}

    # Extract age
    age_match = re.search(r"\b(\d{1,3})\s*(?:year|yr|yo|y/o|[fFmM]\b)", text)
    if age_match:
        age = int(age_match.group(1))
        patient["age"] = age
        if age < 12:
            patient["age_group"] = "child"
        elif age < 18:
            patient["age_group"] = "adolescent"
        elif age < 65:
            patient["age_group"] = "adult"
        else:
            patient["age_group"] = "elderly"

    # Extract sex
    for pattern, result in _SEX_PATTERNS.items():
        if re.search(pattern, text):
            if isinstance(result, tuple):
                patient[result[0]] = result[1]
            break

    # Extract diagnosis (default to ADHD if mentioned or implied)
    if "adhd" in text_lower or "attention deficit" in text_lower:
        patient["diagnosis"] = "ADHD"
    if "depression" in text_lower and "comorbid" not in text_lower:
        patient["diagnosis"] = "depression"

    # Extract comorbidities
    comorbidities = []
    for keyword in _COMORBIDITY_KEYWORDS:
        if keyword in text_lower:
            # Normalize compound terms
            normalized = keyword.replace(" ", "_")
            if normalized == "cardiac_history" or normalized == "cardiovascular":
                normalized = "cardiac_history"
            comorbidities.append(normalized)

    if comorbidities:
        patient["comorbidities"] = comorbidities

    # Extract prior treatments
    prior_treatments = []
    for med in _MEDICATION_KEYWORDS:
        if med in text_lower:
            treatment = {"medication": med, "class": _classify_medication(med)}

            # Check for response
            for response_phrase, response_val in _RESPONSE_KEYWORDS.items():
                if response_phrase in text_lower:
                    treatment["response"] = response_val
                    break

            # Check for side effects / discontinuation reasons
            if "insomnia" in text_lower or "sleep" in text_lower:
                treatment["discontinued_reason"] = "insomnia"
            if "appetite" in text_lower:
                treatment["discontinued_reason"] = "appetite_suppression"
            if "side effect" in text_lower:
                treatment["discontinued_reason"] = "side_effects"

            prior_treatments.append(treatment)

    if prior_treatments:
        patient["prior_treatments"] = prior_treatments

    # Extract contraindications
    contraindications = []
    if "cardiac" in text_lower and "history" in text_lower:
        contraindications.append("cardiac_history")
    if "seizure" in text_lower or "epilepsy" in text_lower:
        contraindications.append("seizure_history")
    if "pregnancy" in text_lower or "pregnant" in text_lower:
        contraindications.append("pregnancy")
    if "breastfeeding" in text_lower or "lactating" in text_lower:
        contraindications.append("breastfeeding")

    if contraindications:
        patient["contraindications"] = contraindications

    return patient


def _classify_medication(med: str) -> str:
    """Classify a medication into its drug class."""
    mph_class = [
        "methylphenidate", "concerta", "ritalin", "equasym", "medikinet",
    ]
    amp_class = [
        "amphetamine", "elvanse", "vyvanse", "adderall",
        "dexamphetamine", "lisdexamfetamine",
    ]
    non_stim = [
        "atomoxetine", "strattera", "guanfacine", "intuniv", "clonidine",
    ]
    antidepressant = [
        "bupropion", "wellbutrin", "sertraline", "fluoxetine",
        "citalopram", "escitalopram", "venlafaxine",
    ]

    if med in mph_class:
        return "stimulant_mph"
    if med in amp_class:
        return "stimulant_amp"
    if med in non_stim:
        return "non_stimulant"
    if med in antidepressant:
        return "antidepressant"
    return "other"
