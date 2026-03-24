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
