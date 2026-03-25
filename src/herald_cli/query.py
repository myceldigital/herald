"""Deterministic query engine for parsed guideline decision trees. No LLM required."""

from __future__ import annotations

import csv
import io
import re
from typing import Any

# ---------------------------------------------------------------------------
# Thread-safe module-level constants (tuples/frozensets, not lists)
# ---------------------------------------------------------------------------

_SEX_PATTERNS = (
    (r"\b(\d+)\s*[fF]\b", ("sex", "female")),
    (r"\b(\d+)\s*[mM]\b", ("sex", "male")),
    (r"\b(female|woman)\b", ("sex", "female")),
    (r"\b(male|man)\b", ("sex", "male")),
)

_MEDICATION_KEYWORDS = (
    "methylphenidate", "concerta", "ritalin", "equasym", "medikinet",
    "amphetamine", "elvanse", "vyvanse", "adderall", "dexamphetamine",
    "atomoxetine", "strattera", "lisdexamfetamine",
    "guanfacine", "intuniv", "clonidine",
    "bupropion", "wellbutrin",
    "sertraline", "fluoxetine", "citalopram", "escitalopram", "venlafaxine",
    "amitriptyline", "paroxetine", "fluvoxamine",
    "ceftriaxone", "cefotaxime", "ampicillin", "amoxicillin", "vancomycin",
    "chloramphenicol", "benzylpenicillin", "rifampicin",
    "albendazole", "praziquantel", "metformin", "amlodipine",
    "atorvastatin", "ramipril", "lisinopril", "losartan",
)

_RESPONSE_KEYWORDS = (
    ("no response", "none"),
    ("non-response", "none"),
    ("non-responder", "none"),
    ("partial response", "partial"),
    ("partial responder", "partial"),
    ("full response", "full"),
)

_NUMERIC_UNIT_PATTERNS = {
    "cm": r"(\d+(?:\.\d+)?)\s*(?:cm|centimeter)",
    "mm": r"(\d+(?:\.\d+)?)\s*(?:mm|millimeter)",
    "mg": r"(\d+(?:\.\d+)?)\s*(?:mg|milligram)",
    "kg": r"(\d+(?:\.\d+)?)\s*(?:kg|kilogram)",
}

_NEGATION_PATTERNS = (
    r"\bno\s+(?:history\s+of\s+)?",
    r"\bnot\s+",
    r"\bwithout\s+",
    r"\bdenies\s+",
    r"\babsent\s+",
    r"\bnegative\s+for\s+",
    r"\brules?\s+out\s+",
    r"\bno\s+known\s+",
    r"\bfree\s+of\s+",
)

_NEGATION_RE = re.compile(
    r"(?:" + "|".join(_NEGATION_PATTERNS) + r")(\w[\w\s]{0,30})",
    re.IGNORECASE,
)

# Vital signs patterns
_VITAL_PATTERNS = (
    (r"\bBP\s*(\d{2,3})\s*/\s*(\d{2,3})", "bp_systolic", "bp_diastolic"),
    (r"\bbp\s*(\d{2,3})\s*/\s*(\d{2,3})", "bp_systolic", "bp_diastolic"),
    (r"\bsystolic\s*(?:BP\s*)?(\d{2,3})", "bp_systolic", None),
    (r"\bGCS\s*(\d{1,2})", "gcs", None),
    (r"\bgcs\s*(\d{1,2})", "gcs", None),
    (r"\bSpO2\s*(\d{2,3})\s*%?", "spo2", None),
    (r"\bspo2\s*(\d{2,3})\s*%?", "spo2", None),
    (r"\bsats?\s*(\d{2,3})\s*%", "spo2", None),
    (r"\bHR\s*(\d{2,3})", "heart_rate", None),
    (r"\bheart\s*rate\s*(\d{2,3})", "heart_rate", None),
    (r"\bpulse\s*(\d{2,3})", "heart_rate", None),
    (r"\bRR\s*(\d{1,2})", "resp_rate", None),
    (r"\bresp(?:iratory)?\s*rate\s*(\d{1,2})", "resp_rate", None),
    (r"\btemp(?:erature)?\s*(\d{2}(?:\.\d)?)\s*[°]?[cC]?", "temperature", None),
)

# Common medical abbreviations → canonical terms
_MEDICAL_ABBREVIATIONS = {
    "htn": "hypertension", "dm": "diabetes", "t2dm": "type 2 diabetes",
    "t1dm": "type 1 diabetes", "ckd": "chronic kidney disease",
    "ckd3": "chronic kidney disease stage 3",
    "ckd4": "chronic kidney disease stage 4",
    "ckd5": "chronic kidney disease stage 5",
    "af": "atrial fibrillation", "mi": "myocardial infarction",
    "cva": "cerebrovascular accident", "tia": "transient ischaemic attack",
    "copd": "chronic obstructive pulmonary disease",
    "ccf": "congestive cardiac failure", "chf": "congestive heart failure",
    "dvt": "deep vein thrombosis", "pe": "pulmonary embolism",
    "uti": "urinary tract infection", "lrti": "lower respiratory tract infection",
    "gord": "gastro-oesophageal reflux disease",
    "gerd": "gastroesophageal reflux disease",
    "ibs": "irritable bowel syndrome", "ibd": "inflammatory bowel disease",
    "ra": "rheumatoid arthritis", "oa": "osteoarthritis",
    "mdd": "major depressive disorder", "gad": "generalised anxiety disorder",
    "ptsd": "post-traumatic stress disorder",
    "ocd": "obsessive-compulsive disorder",
    "bpd": "borderline personality disorder",
    "adhd": "attention deficit hyperactivity disorder",
    "asd": "autism spectrum disorder",
    "ccb": "calcium channel blocker", "ace": "ace inhibitor",
    "arb": "angiotensin receptor blocker", "bb": "beta blocker",
    "ppi": "proton pump inhibitor", "nsaid": "non-steroidal anti-inflammatory",
    "ssri": "selective serotonin reuptake inhibitor",
    "snri": "serotonin-norepinephrine reuptake inhibitor",
    "tca": "tricyclic antidepressant",
    "diabetic": "diabetes", "hypertensive": "hypertension",
    "asthmatic": "asthma", "epileptic": "epilepsy",
    "egfr": "estimated glomerular filtration rate",
    "hba1c": "glycated haemoglobin",
}

# Priority values for urgency sorting
_PRIORITY_ORDER = {
    "critical": 0, "emergent": 0,
    "urgent": 1, "high": 1,
    "standard": 2, "normal": 2, "medium": 2,
    "low": 3, "routine": 3, "elective": 3,
}


class QueryEngine:
    """Traverse a parsed guideline decision tree given a patient profile."""

    def __init__(self, decision_tree: dict):
        self.tree = decision_tree
        self.guideline = decision_tree.get("guideline", {})
        self.patient_fields = decision_tree.get("patient_fields", [])
        self.field_synonyms = decision_tree.get("field_synonyms", {})
        self.decisions = {
            d["id"]: d for d in decision_tree.get("decisions", [])
        }

        # Pre-compute entry points
        explicit = [
            d for d in self.decisions.values() if d.get("entry_point")
        ]
        if explicit:
            self._entry_points = explicit
        else:
            referenced = set()
            for d in self.decisions.values():
                for b in d.get("branches", []):
                    referenced.add(b["next_decision"])
            self._entry_points = [
                d for d in self.decisions.values()
                if d["id"] not in referenced
            ]

        # Pre-compute frozensets for in/not_in O(1) lookups
        self._cond_sets: dict[int, frozenset] = {}
        for d in self.decisions.values():
            for c in d.get("conditions", []) + [
                b.get("condition", {}) for b in d.get("branches", [])
            ]:
                if c.get("operator") in ("in", "not_in") and isinstance(
                    c.get("value"), list
                ):
                    key = id(c["value"])
                    if key not in self._cond_sets:
                        self._cond_sets[key] = frozenset(
                            _normalize(v) for v in c["value"]
                        )

    def get_patient_fields(self) -> list[dict]:
        return self.patient_fields

    def query(self, patient: dict) -> list[dict]:
        """Query with priority sorting and contraindication blocking."""
        results = []
        blocked = []

        for entry in self._entry_points:
            self._traverse(entry["id"], patient, [], results)

        # Separate blocked (contraindicated) recommendations
        active = []
        for r in results:
            rec = r["recommendation"]
            if rec.get("contraindicated_if"):
                ci_conditions = rec["contraindicated_if"]
                if _all_conditions_match(
                    ci_conditions, patient, self._cond_sets
                ):
                    r["blocked_reason"] = "Contraindicated for this patient"
                    blocked.append(r)
                    continue
            active.append(r)

        # Sort: priority first (lower = more urgent), then specificity
        def sort_key(r):
            rec = r["recommendation"]
            p = rec.get("priority", "standard")
            priority_val = _PRIORITY_ORDER.get(p, 2)
            return (priority_val, -r["specificity"])

        active.sort(key=sort_key)

        # Attach blocked info to result set
        if blocked:
            for a in active:
                a.setdefault("_blocked_siblings", [])
            if active:
                active[0]["_blocked_siblings"] = blocked

        return active

    def query_batch(self, patients: list[dict]) -> list[dict]:
        """Query multiple patients. Returns list of result dicts."""
        output = []
        for i, patient in enumerate(patients):
            results = self.query(patient)
            output.append({
                "patient_index": i,
                "patient": patient,
                "recommendations": [
                    {
                        "action": r["recommendation"]["action"],
                        "decision_path": r.get("path", []),
                        "priority": r["recommendation"].get("priority"),
                    }
                    for r in results
                ],
                "recommendation_count": len(results),
            })
        return output

    def _traverse(self, node_id, patient, path, results, depth=0):
        """Iterative-capable tree traversal."""
        stack = [(node_id, path, depth)]
        while stack:
            nid, cur_path, d = stack.pop()
            if d > 50:
                continue
            node = self.decisions.get(nid)
            if not node:
                continue

            conditions = node.get("conditions", [])
            if not _all_conditions_match(
                conditions, patient, self._cond_sets
            ):
                continue

            this_path = cur_path + [nid]

            # Sequence nodes
            sequence = node.get("sequence", [])
            if sequence:
                for step_id in sequence:
                    step = self.decisions.get(step_id)
                    if step and step.get("recommendation"):
                        sc = step.get("conditions", [])
                        if _all_conditions_match(
                            sc, patient, self._cond_sets
                        ):
                            results.append({
                                "recommendation": step["recommendation"],
                                "decision_id": step_id,
                                "path": this_path + [step_id],
                                "specificity": len(sc) + len(conditions),
                            })
                continue

            branch_followed = False
            for branch in node.get("branches", []):
                bc = branch.get("condition", {})
                if _condition_matches(bc, patient, self._cond_sets):
                    stack.append(
                        (branch["next_decision"], this_path, d + 1)
                    )
                    branch_followed = True

            if not branch_followed and node.get("recommendation"):
                results.append({
                    "recommendation": node["recommendation"],
                    "decision_id": nid,
                    "path": this_path,
                    "specificity": len(conditions),
                })


class MultiQueryEngine:
    """Query multiple guidelines with conflict detection."""

    def __init__(self, guidelines: list[dict]):
        self.engines = [QueryEngine(g) for g in guidelines]

    def query(self, patient: dict) -> dict:
        all_results = []
        for engine in self.engines:
            title = engine.guideline.get("short_title", "Unknown")
            for r in engine.query(patient):
                r["guideline"] = title
                all_results.append(r)
        return {
            "recommendations": all_results,
            "conflicts": self._detect_conflicts(all_results),
        }

    def _detect_conflicts(self, results):
        conflicts = []
        actions = []
        avoid = ("avoid", "do not", "contraindicated", "not recommended")
        consider = ("consider", "should be", "is suggested", "administer")
        for r in results:
            al = r["recommendation"]["action"].lower()
            gl = r.get("guideline", "")
            for pa, pg, pr in actions:
                a_neg = any(t in pa for t in avoid)
                b_pos = any(t in al for t in consider)
                b_neg = any(t in al for t in avoid)
                a_pos = any(t in pa for t in consider)
                if (a_neg and b_pos) or (b_neg and a_pos):
                    conflicts.append({
                        "type": "potential_conflict",
                        "guideline_a": pg,
                        "recommendation_a": pr["decision_id"],
                        "guideline_b": gl,
                        "recommendation_b": r["decision_id"],
                        "note": "May conflict. Clinical review recommended.",
                    })
            actions.append((al, gl, r))
        return conflicts


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

def _all_conditions_match(conditions, patient, cond_sets=None):
    if not conditions:
        return True
    return all(_condition_matches(c, patient, cond_sets) for c in conditions)


def _condition_matches(condition, patient, cond_sets=None):
    field = condition.get("field", "")
    operator = condition.get("operator", "")
    expected = condition.get("value")
    actual = patient.get(field)

    if operator == "exists":
        has = actual is not None and actual != "" and actual != []
        return has == expected
    if actual is None:
        return False
    if operator == "eq":
        return _normalize(actual) == _normalize(expected)
    if operator == "neq":
        return _normalize(actual) != _normalize(expected)
    if operator in ("in", "not_in"):
        if isinstance(expected, list):
            if cond_sets:
                fset = cond_sets.get(id(expected))
                if fset is not None:
                    r = _normalize(actual) in fset
                    return r if operator == "in" else not r
            ns = frozenset(_normalize(v) for v in expected)
            r = _normalize(actual) in ns
            return r if operator == "in" else not r
        return operator == "not_in"
    if operator == "contains":
        if isinstance(actual, list):
            return _normalize(expected) in [_normalize(v) for v in actual]
        if isinstance(actual, str):
            return _normalize(expected) in _normalize(actual)
        return False
    if operator == "not_contains":
        if isinstance(actual, list):
            return _normalize(expected) not in [
                _normalize(v) for v in actual
            ]
        if isinstance(actual, str):
            return _normalize(expected) not in _normalize(actual)
        return True
    if operator in ("gt", "gte", "lt", "lte"):
        try:
            an = float(actual)
            en = float(expected)
        except (ValueError, TypeError):
            return False
        return {"gt": an > en, "gte": an >= en,
                "lt": an < en, "lte": an <= en}[operator]
    if operator == "any_match":
        if not isinstance(actual, list):
            return False
        sub = (expected.get("conditions", [])
               if isinstance(expected, dict) else [])
        return any(
            _all_conditions_match(sub, item, cond_sets) for item in actual
        )
    return False


def _normalize(value):
    if isinstance(value, str):
        return value.lower().strip()
    return value


# ---------------------------------------------------------------------------
# Negation + abbreviation helpers
# ---------------------------------------------------------------------------

def _find_negated_terms(text):
    negated = set()
    for m in _NEGATION_RE.finditer(text):
        term = m.group(1).strip().lower()
        words = term.split()[:3]
        negated.add(" ".join(words))
        if words:
            negated.add(words[0])
    return negated


def _expand_abbreviations(text):
    """Expand medical abbreviations in text for better extraction."""
    expanded = text
    for abbr, full in _MEDICAL_ABBREVIATIONS.items():
        pattern = r"\b" + re.escape(abbr) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            expanded = expanded + " " + full
    return expanded


def _extract_vitals(text, patient, meta):
    """Extract vital signs from clinical shorthand."""
    for pattern, field1, field2 in _VITAL_PATTERNS:
        m = re.search(pattern, text)
        if m:
            patient[field1] = float(m.group(1))
            meta[field1] = {"source": "extracted", "matched": m.group(0)}
            if field2 and m.lastindex >= 2:
                patient[field2] = float(m.group(2))
                meta[field2] = {"source": "extracted", "matched": m.group(0)}


# ---------------------------------------------------------------------------
# Natural language parser
# ---------------------------------------------------------------------------

def parse_patient_description(text, guideline=None):
    """Parse natural language patient description with vital signs,
    abbreviation expansion, confidence scoring, and negation handling."""
    # Expand abbreviations first
    expanded = _expand_abbreviations(text)
    text_lower = expanded.lower()
    patient: dict[str, Any] = {}
    meta: dict[str, dict] = {}
    negated = _find_negated_terms(expanded)

    # --- Vitals ---
    _extract_vitals(text, patient, meta)

    # --- Age ---
    age_match = re.search(
        r"\b(\d{1,3})\s*(?:year|yr|yo|y/o|[fFmM]\b)", text
    )
    if age_match:
        age = int(age_match.group(1))
        patient["age"] = age
        meta["age"] = {"source": "extracted", "matched": age_match.group(0)}
        if age < 12:
            patient["age_group"] = "child"
        elif age < 18:
            patient["age_group"] = "adolescent"
        elif age < 65:
            patient["age_group"] = "adult"
        else:
            patient["age_group"] = "elderly"
        meta["age_group"] = {"source": "derived_from_age"}

    # --- Sex ---
    for pattern, result in _SEX_PATTERNS:
        if re.search(pattern, text):
            if isinstance(result, tuple):
                patient[result[0]] = result[1]
                meta[result[0]] = {"source": "extracted"}
            break

    # --- Medications ---
    treatments = []
    for med in _MEDICATION_KEYWORDS:
        if med in text_lower and med not in negated:
            t = {"medication": med, "class": _classify_medication(med)}
            for phrase, val in _RESPONSE_KEYWORDS:
                if phrase in text_lower:
                    t["response"] = val
                    break
            if "insomnia" in text_lower or "sleep" in text_lower:
                t["discontinued_reason"] = "insomnia"
            if "appetite" in text_lower:
                t["discontinued_reason"] = "appetite_suppression"
            if "side effect" in text_lower:
                t["discontinued_reason"] = "side_effects"
            treatments.append(t)
    if treatments:
        patient["prior_treatments"] = treatments

    # --- Treatment phase ---
    if "continuation" in text_lower or "responding" in text_lower:
        patient["treatment_phase"] = "continuation"
    elif "failed" in text_lower or "treatment failure" in text_lower:
        patient["treatment_phase"] = "treatment_failure"

    # --- Severity ---
    if "mild" in text_lower and "moderate" not in text_lower:
        patient["severity"] = "mild"
    elif "severe" in text_lower:
        patient["severity"] = "severe"
    elif "moderate" in text_lower:
        patient["severity"] = "moderate"

    # --- Dynamic guideline-driven extraction ---
    if guideline:
        pf = guideline.get("patient_fields", [])
        fs = guideline.get("field_synonyms", {})

        for fd in pf:
            fn = fd.get("field", "")
            ft = fd.get("type", "string")
            if fn in patient:
                continue
            kv = fd.get("values", []) + fd.get("known_values", [])

            if ft == "bool":
                _extract_bool_field(text_lower, fn, fs, patient, negated, meta)
            elif ft == "number":
                _extract_number_field(
                    text_lower, text, fn, fs, patient, meta
                )
            elif ft.startswith("list"):
                _extract_list_field(
                    text_lower, fn, kv, fs, patient, negated, meta
                )
            elif ft == "enum" and kv:
                _extract_enum_field(
                    text_lower, text, fn, kv, fs, patient, negated, meta
                )
            elif ft == "string":
                if kv:
                    _extract_enum_field(
                        text_lower, text, fn, kv, fs, patient, negated, meta
                    )
                else:
                    _extract_string_field(text_lower, fn, fs, patient, meta)

        # Auto-infer single-value required fields
        for fd in pf:
            fn = fd.get("field", "")
            if fn in patient or not fd.get("required", False):
                continue
            kv = fd.get("values", []) + fd.get("known_values", [])
            if len(kv) == 1:
                patient[fn] = kv[0]
                meta[fn] = {"source": "auto_inferred"}

        # Flag missing required fields
        for fd in pf:
            fn = fd.get("field", "")
            if fn not in patient and fd.get("required", False):
                meta[fn] = {"source": "missing", "required": True}

    # --- Legacy fallback ---
    if not guideline:
        _legacy_extract(text, text_lower, patient, negated)

    if meta:
        patient["_extraction_meta"] = meta
    return patient


# ---------------------------------------------------------------------------
# Dynamic field extractors
# ---------------------------------------------------------------------------

def _extract_enum_field(tl, tr, fn, kv, fs, p, neg, m):
    for v in sorted(kv, key=len, reverse=True):
        if _is_negated(v, tl, neg):
            continue
        if _term_in_text(v, tl, tr):
            p[fn] = v
            m[fn] = {"source": "extracted", "matched": v}
            return
        for syn in fs.get(v, []):
            if _is_negated(syn, tl, neg):
                continue
            if _term_in_text(syn, tl, tr):
                p[fn] = v
                m[fn] = {"source": "synonym", "matched": syn, "canonical": v}
                return


def _extract_bool_field(tl, fn, fs, p, neg, m):
    st = fn.replace("_", " ")
    if _is_negated(st, tl, neg):
        return
    if st in tl:
        p[fn] = True
        m[fn] = {"source": "extracted", "matched": st}
        return
    for syn in fs.get(fn, []):
        if _is_negated(syn, tl, neg):
            continue
        if syn.lower() in tl:
            p[fn] = True
            m[fn] = {"source": "synonym", "matched": syn}
            return


def _extract_number_field(tl, tr, fn, fs, p, m):
    for u in ("cm", "mm", "mg", "kg"):
        if u in fn and u in _NUMERIC_UNIT_PATTERNS:
            match = re.search(_NUMERIC_UNIT_PATTERNS[u], tl)
            if match:
                p[fn] = float(match.group(1))
                m[fn] = {"source": "extracted", "matched": match.group(0)}
                return
    for syn in fs.get(fn, []) + [fn.replace("_", " ")]:
        sl = syn.lower()
        if sl in tl:
            idx = tl.index(sl)
            ctx = tl[max(0, idx - 20):idx + len(sl) + 20]
            nm = re.search(r"(\d+(?:\.\d+)?)", ctx)
            if nm:
                p[fn] = float(nm.group(1))
                m[fn] = {"source": "extracted_near", "matched": syn}
                return


def _extract_list_field(tl, fn, kv, fs, p, neg, m):
    matches = []
    for v in kv:
        st = v.replace("_", " ")
        if _is_negated(st, tl, neg):
            continue
        if st in tl:
            matches.append(v)
            continue
        for syn in fs.get(v, []):
            if _is_negated(syn, tl, neg):
                continue
            if syn.lower() in tl:
                matches.append(v)
                break
    if matches:
        p[fn] = matches
        m[fn] = {"source": "extracted", "count": len(matches)}


def _extract_string_field(tl, fn, fs, p, m):
    for cv, syns in fs.items():
        if not isinstance(syns, list):
            continue
        for syn in syns:
            if syn.lower() in tl:
                p[fn] = cv
                m[fn] = {"source": "synonym", "matched": syn}
                return


def _term_in_text(term, tl, tr):
    if term != term.lower():
        return bool(re.search(r"\b" + re.escape(term) + r"\b", tr))
    return bool(re.search(r"\b" + re.escape(term) + r"\b", tl))


def _is_negated(term, tl, negated):
    t = term.lower()
    return any(t in n or n in t for n in negated)


# ---------------------------------------------------------------------------
# Legacy extraction
# ---------------------------------------------------------------------------

def _legacy_extract(text, tl, p, neg):
    if "adhd" in tl or "attention deficit" in tl:
        p.setdefault("diagnosis", "ADHD")
    if "meningitis" in tl:
        p.setdefault("diagnosis", "meningitis")
    if any(t in tl for t in ("echinococcosis", "hydatid", "echinococcal")):
        p.setdefault("diagnosis", "cystic_echinococcosis")
    if "depression" in tl or "depressive" in tl:
        dp = tl.find("depression")
        if dp == -1:
            dp = tl.find("depressive")
        pre = tl[max(0, dp - 30):dp]
        if "comorbid" not in pre:
            p.setdefault("diagnosis", "depression")

    comorbidity_kw = (
        "anxiety", "depression", "bipolar", "substance use",
        "cardiac", "cardiac history", "cardiovascular", "hypertension",
        "diabetes", "asthma", "chronic kidney disease",
        "tics", "tourette", "asd", "autism", "epilepsy", "seizure",
        "sleep disorder", "insomnia", "obesity", "eating disorder",
        "personality disorder", "ptsd", "ocd",
    )
    comorbs = []
    diag = p.get("diagnosis", "").lower()
    for kw in comorbidity_kw:
        if kw in tl and kw != diag and not _is_negated(kw, tl, neg):
            n = kw.replace(" ", "_")
            if n in ("cardiac_history", "cardiovascular"):
                n = "cardiac_history"
            comorbs.append(n)
    if comorbs:
        p.setdefault("comorbidities", comorbs)

    contras = []
    if "cardiac" in tl and "history" in tl:
        if not _is_negated("cardiac", tl, neg):
            contras.append("cardiac_history")
    if ("seizure" in tl or "epilepsy" in tl):
        if not _is_negated("seizure", tl, neg):
            contras.append("seizure_history")
    if "pregnancy" in tl or "pregnant" in tl:
        contras.append("pregnancy")
    if "breastfeeding" in tl or "lactating" in tl:
        contras.append("breastfeeding")
    if contras:
        p.setdefault("contraindications", contras)


def _classify_medication(med):
    mph = ("methylphenidate", "concerta", "ritalin", "equasym", "medikinet")
    amp = ("amphetamine", "elvanse", "vyvanse", "adderall",
           "dexamphetamine", "lisdexamfetamine")
    nst = ("atomoxetine", "strattera", "guanfacine", "intuniv", "clonidine")
    adp = ("bupropion", "wellbutrin", "sertraline", "fluoxetine",
           "citalopram", "escitalopram", "venlafaxine", "amitriptyline",
           "paroxetine", "fluvoxamine")
    abx = ("ceftriaxone", "cefotaxime", "ampicillin", "amoxicillin",
           "vancomycin", "chloramphenicol", "benzylpenicillin", "rifampicin")
    atp = ("albendazole", "praziquantel")
    cvs = ("amlodipine", "atorvastatin", "ramipril", "lisinopril",
           "losartan", "metformin")
    if med in mph:
        return "stimulant_mph"
    if med in amp:
        return "stimulant_amp"
    if med in nst:
        return "non_stimulant"
    if med in adp:
        return "antidepressant"
    if med in abx:
        return "antibiotic"
    if med in atp:
        return "antiparasitic"
    if med in cvs:
        return "cardiovascular"
    return "other"


# ---------------------------------------------------------------------------
# Batch CSV processing
# ---------------------------------------------------------------------------

def parse_csv_patients(csv_text: str) -> list[dict]:
    """Parse a CSV of patient records into dicts."""
    reader = csv.DictReader(io.StringIO(csv_text))
    patients = []
    for row in reader:
        patient = {}
        for k, v in row.items():
            if v is None or v.strip() == "":
                continue
            k = k.strip()
            # Try numeric
            try:
                patient[k] = float(v) if "." in v else int(v)
            except ValueError:
                # Try list (comma-separated in brackets)
                if v.startswith("[") and v.endswith("]"):
                    patient[k] = [
                        x.strip().strip("'\"")
                        for x in v[1:-1].split(",")
                    ]
                elif v.lower() in ("true", "yes"):
                    patient[k] = True
                elif v.lower() in ("false", "no"):
                    patient[k] = False
                else:
                    patient[k] = v.strip()
        patients.append(patient)
    return patients
