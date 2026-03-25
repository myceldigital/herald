# Herald Schema Specification v0.1

The CPG schema defines how clinical practice guidelines are represented as machine-readable decision trees. Every element traces back to its source text, making the output auditable by clinicians.

## Design principles

1. **Auditable** — every recommendation includes `source_section`, `source_page`, and `source_text` from the original guideline
2. **Traversable** — the decision tree can be walked with deterministic logic (no LLM required for queries)
3. **Composable** — multiple guidelines can be loaded and cross-referenced
4. **Minimal** — only the fields needed for clinical decision support, nothing more

## Top-level structure

```json
{
  "schema_version": "0.1",
  "guideline": { ... },
  "patient_fields": [ ... ],
  "field_synonyms": { ... },
  "decisions": [ ... ]
}
```

## `guideline` — metadata about the source document

```json
{
  "guideline": {
    "title": "string — full guideline title",
    "short_title": "string — abbreviated name for display",
    "source": "string — publishing body (e.g. 'NICE', 'APA', 'WHO')",
    "version": "string — guideline version",
    "last_updated": "string — ISO date (YYYY-MM-DD)",
    "url": "string|null — canonical URL of the guideline",
    "condition": "string — primary condition covered (e.g. 'ADHD', 'Depression')",
    "population": "string — target population (e.g. 'Adults', 'Children 5-17')"
  }
}
```

## `patient_fields` — inputs the decision tree expects

Defines the patient attributes that the tree branches on. This tells the query engine what to ask for.

```json
{
  "patient_fields": [
    {
      "field": "age_group",
      "type": "enum",
      "values": ["child", "adolescent", "adult", "elderly"],
      "required": true,
      "description": "Patient age category"
    },
    {
      "field": "diagnosis",
      "type": "string",
      "required": true,
      "description": "Confirmed diagnosis"
    },
    {
      "field": "comorbidities",
      "type": "list[string]",
      "required": false,
      "description": "Active comorbid conditions",
      "known_values": ["anxiety", "depression", "substance_use", "cardiac_history", "tics", "asd"]
    },
    {
      "field": "prior_treatments",
      "type": "list[object]",
      "required": false,
      "description": "Previous medication trials",
      "object_fields": {
        "medication": "string",
        "class": "string — e.g. 'stimulant_mph', 'stimulant_amp', 'non_stimulant'",
        "max_dose": "string",
        "response": "enum: full|partial|none",
        "discontinued_reason": "string|null"
      }
    },
    {
      "field": "contraindications",
      "type": "list[string]",
      "required": false,
      "description": "Active contraindications"
    }
  ]
}
```

### Supported field types

| Type | Description | Example |
|------|-------------|---------|
| `string` | Free text | `"ADHD"` |
| `enum` | One of a defined set | `"adult"` |
| `bool` | True/false | `true` |
| `number` | Numeric value | `36` |
| `list[string]` | List of strings | `["anxiety", "depression"]` |
| `list[object]` | List of structured objects | Prior treatments |

## `field_synonyms` — guideline-driven vocabulary (optional)

Maps canonical values to their natural language synonyms. This enables the `--ask` parser to understand clinical terminology without hardcoded keywords — each guideline teaches the parser its own vocabulary.

```json
{
  "field_synonyms": {
    "cystic_echinococcosis": ["echinococcosis", "hydatid", "hydatid cyst"],
    "liver": ["hepatic", "hepatobiliary"],
    "CE3a": ["type 3a", "transitional", "water lily sign"],
    "biliary_communication": ["biliary fistula", "bile-stained"]
  }
}
```

Keys can be:
- **Enum values** (e.g. `"CE1"`, `"liver"`) — synonym matches map to that value
- **Boolean field names** (e.g. `"biliary_communication"`) — synonym matches set the field to `true`
- **String field values** — used when `patient_fields` has `known_values`

The parser also auto-infers required fields with exactly one `known_value` (e.g., loading the CE guideline implies `diagnosis = cystic_echinococcosis`).

The `herald parse` step can generate `field_synonyms` automatically during LLM extraction.

## `decisions` — the decision tree

An array of decision nodes. Each node has conditions that must be met, a recommendation, and optional branches to other nodes.

```json
{
  "decisions": [
    {
      "id": "string — unique identifier (snake_case)",
      "description": "string — human-readable description of this decision point",
      "entry_point": "bool — true if this is a root node (default: false)",
      "conditions": [ ... ],
      "recommendation": { ... },
      "branches": [ ... ]
    }
  ]
}
```

### `conditions` — when does this decision apply?

An array of conditions that must ALL be true for this node to activate. Evaluated with AND logic. For OR logic, create separate decision nodes.

```json
{
  "conditions": [
    {
      "field": "string — references a patient_field",
      "operator": "string — comparison operator",
      "value": "any — the value to compare against"
    }
  ]
}
```

### Supported operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `eq` | Equals | `{"field": "age_group", "operator": "eq", "value": "adult"}` |
| `neq` | Not equals | `{"field": "diagnosis", "operator": "neq", "value": "bipolar"}` |
| `contains` | List contains value | `{"field": "comorbidities", "operator": "contains", "value": "anxiety"}` |
| `not_contains` | List does not contain | `{"field": "contraindications", "operator": "not_contains", "value": "cardiac"}` |
| `gt` / `gte` | Greater than (or equal) | `{"field": "age", "operator": "gte", "value": 18}` |
| `lt` / `lte` | Less than (or equal) | `{"field": "bmi", "operator": "lt", "value": 30}` |
| `exists` | Field is present and non-empty | `{"field": "prior_treatments", "operator": "exists", "value": true}` |
| `any_match` | Any item in list matches sub-conditions | See below |

### `any_match` — querying list items

For fields like `prior_treatments` (a list of objects), `any_match` checks if any item meets sub-conditions:

```json
{
  "field": "prior_treatments",
  "operator": "any_match",
  "value": {
    "conditions": [
      { "field": "class", "operator": "eq", "value": "stimulant_mph" },
      { "field": "response", "operator": "eq", "value": "none" }
    ]
  }
}
```

This reads: "the patient has tried at least one methylphenidate-class stimulant with no response."

### `recommendation` — what should be done

```json
{
  "recommendation": {
    "action": "string — the clinical action to take",
    "evidence_grade": "string — e.g. 'A', 'B', 'C', 'D', 'GPP' (good practice point)",
    "strength": "enum: strong|conditional|weak",
    "monitoring": "string|null — any monitoring requirements",
    "source_section": "string — section number in original document",
    "source_page": "number|null — page number in original document",
    "source_text": "string — exact text from the guideline supporting this recommendation"
  }
}
```

### `branches` — conditional next steps

After a recommendation, branches point to other decision nodes based on additional patient attributes:

```json
{
  "branches": [
    {
      "condition": {
        "field": "string",
        "operator": "string",
        "value": "any"
      },
      "next_decision": "string — id of the next decision node",
      "label": "string|null — human-readable description of this branch"
    }
  ]
}
```

If no branch condition matches, the recommendation stands as the final answer.

## Traversal algorithm

The query engine walks the tree as follows:

1. Find all `entry_point: true` decision nodes
2. For each entry point, evaluate its `conditions` against the patient profile
3. If all conditions match, return the `recommendation`
4. Check `branches` — if a branch condition matches, follow `next_decision` and repeat from step 2 at that node
5. If multiple entry points match, return all matching recommendations ranked by specificity (more conditions = more specific = higher rank)

This is fully deterministic. No LLM is involved in the query step.

## Example: complete synthetic ADHD guideline

See `examples/synthetic_adhd_guideline.json` for a full working example with 12+ decision nodes covering first-line treatment, comorbidity branching, titration failure pathways, and monitoring requirements.

## Versioning

The schema follows semantic versioning. The `schema_version` field in every JSON file indicates which version it conforms to. Breaking changes increment the major version. New optional fields increment the minor version.

## Schema Extensions (v0.2)

### `priority` — urgency ordering on recommendations

```json
"recommendation": {
  "action": "Secure airway immediately",
  "priority": "critical",
  ...
}
```

Values: `critical`, `emergent`, `urgent`, `high`, `standard`, `normal`, `low`, `routine`, `elective`. The query engine sorts results by priority first (most urgent first), then by specificity.

### `dosing` — structured dosing on recommendations

```json
"recommendation": {
  "action": "Give tranexamic acid",
  "dosing": {
    "dose": "1g",
    "route": "IV",
    "frequency": "over 10 minutes, then 1g over 8 hours",
    "duration": "single administration",
    "weight_based": false,
    "max_dose": "2g total"
  }
}
```

### `pre_actions` / `post_actions` — implementation workflow

```json
"recommendation": {
  "action": "Start ACE inhibitor",
  "pre_actions": ["Check U&Es and eGFR", "Check potassium level"],
  "post_actions": ["Recheck U&Es at 2 weeks", "Book follow-up in 4 weeks"]
}
```

### `contraindicated_if` — automatic blocking

```json
"recommendation": {
  "action": "Consider amitriptyline (TCA)",
  "contraindicated_if": [
    { "field": "contraindications", "operator": "contains", "value": "pregnancy" },
    { "field": "age_group", "operator": "eq", "value": "elderly" }
  ]
}
```

When a recommendation matches but its `contraindicated_if` conditions also match the patient, it is moved to `blocked_recommendations` in the output instead of active recommendations.

### `pathway` — grouping construct for complex guidelines

```json
{
  "id": "cancer_assessment",
  "pathway": "suspected_cancer",
  "pathway_stage": "initial_assessment",
  "entry_point": true,
  ...
}
```

Pathways group related decisions into named clinical workflows. The `pathway` field is a string identifier; `pathway_stage` indicates position within the pathway.

### `sequence` — ordered step execution

```json
{
  "id": "imnci_fever",
  "sequence": ["check_danger_signs", "classify_severity", "treat"],
  ...
}
```

Unlike branches (conditional), sequences execute ALL listed steps in order.

### `data_mapping` — EHR phenotype mapping

```json
"patient_fields": [
  {
    "field": "diagnosis",
    "type": "string",
    "data_mapping": {
      "ehr_source": "clinical_events",
      "codelist": "opensafely/adhd/2023-01-01",
      "fhir_path": "Condition.code",
      "snomed_codes": ["406506008"]
    }
  }
]
```

Maps Herald patient fields to EHR data sources for automated population-level queries.

### `cross_references` — guideline linkage

```json
"guideline": {
  "title": "NICE NG87 ADHD",
  "cross_references": [
    { "guideline": "NICE CG181", "title": "Lipid modification", "context": "Cardiovascular risk assessment" },
    { "guideline": "NICE NG12", "title": "Suspected cancer", "context": "If symptoms suggest malignancy" }
  ]
}
```

### `parse_metadata` — reproducibility

```json
"parse_metadata": {
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  "timestamp": "2025-03-24T22:00:00Z",
  "prompt_version": "0.2",
  "schema_version": "0.1"
}
```

Recorded automatically by `herald parse` for research reproducibility.

### `licence` — source guideline licensing

```json
"guideline": {
  "licence": "CC BY-NC-SA 3.0 IGO",
  "licence_url": "https://creativecommons.org/licenses/by-nc-sa/3.0/igo/"
}
```

### Temporal conditions

Temporal conditions use the same operator syntax as other conditions. The field value is computed by the caller (e.g., from prescription dates):

```json
{ "field": "treatment_duration_months", "operator": "gte", "value": 3 }
{ "field": "days_since_last_review", "operator": "gt", "value": 90 }
```
