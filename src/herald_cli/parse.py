"""Parse guideline markdown into structured decision tree JSON using LLM extraction."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Schema models (Pydantic)
# ---------------------------------------------------------------------------


class Condition(BaseModel):
    field: str
    operator: str  # eq, neq, contains, not_contains, gt, gte, lt, lte, exists, any_match
    value: Any


class Recommendation(BaseModel):
    action: str
    evidence_grade: str = ""
    strength: str = ""  # strong, conditional, weak
    monitoring: str | None = None
    source_section: str = ""
    source_page: int | None = None
    source_text: str = ""


class Branch(BaseModel):
    condition: Condition
    next_decision: str
    label: str | None = None


class PatientField(BaseModel):
    field: str
    type: str  # string, enum, bool, number, list[string], list[object]
    required: bool = False
    description: str = ""
    values: list[str] | None = None
    known_values: list[str] | None = None


class DecisionNode(BaseModel):
    id: str
    description: str = ""
    entry_point: bool = False
    conditions: list[Condition] = Field(default_factory=list)
    recommendation: Recommendation
    branches: list[Branch] = Field(default_factory=list)


class GuidelineMeta(BaseModel):
    title: str
    short_title: str = ""
    source: str = ""
    version: str = ""
    last_updated: str = ""
    url: str | None = None
    condition: str = ""
    population: str = ""


class GuidelineDecisionTree(BaseModel):
    schema_version: str = "0.1"
    guideline: GuidelineMeta
    patient_fields: list[PatientField] = Field(default_factory=list)
    decisions: list[DecisionNode] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Extraction prompt (inlined per council decision)
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """\
You are a clinical guideline parser. Read a clinical practice \
guideline (in markdown) and extract its recommendations as a \
structured decision tree.

For each recommendation in the guideline, extract:

1. **Decision node ID**: A unique snake_case identifier \
(e.g. `first_line_treatment`, `adhd_with_anxiety`)
2. **Description**: Human-readable description of this decision
3. **Entry point**: True if this is a starting point \
(typically the first-line treatment recommendation)
4. **Conditions**: Patient attributes that must be true. Each has:
   - `field`: the patient attribute (e.g. `diagnosis`, `age_group`)
   - `operator`: eq, neq, contains, not_contains, gt, gte, \
lt, lte, exists, any_match
   - `value`: the value to compare against
5. **Recommendation**: The clinical action to take, including:
   - `action`: what to do (e.g. "Start methylphenidate 18mg, titrate weekly")
   - `evidence_grade`: the evidence grade from the guideline (A, B, C, D, GPP)
   - `strength`: strong, conditional, or weak
   - `monitoring`: any monitoring requirements
   - `source_section`: the section number in the original document
   - `source_page`: the page number (if identifiable)
   - `source_text`: the EXACT text from the guideline that supports this recommendation
6. **Branches**: Conditional next steps based on additional patient attributes. Each branch has:
   - `condition`: a single condition object
   - `next_decision`: the ID of the next decision node to follow
   - `label`: a human-readable description of this branch

Also extract:
- **Guideline metadata**: title, source, version, condition, population
- **Patient fields**: all patient attributes the guideline branches on, with their types and allowed values. Add `known_values` for string fields that have a fixed set of canonical values.
- **Field synonyms**: a mapping of canonical values to their clinical synonyms and alternative phrasings. This enables natural language queries to match guideline-specific terminology.

Return ONLY valid JSON matching this exact structure (no markdown, no explanation):

{
  "schema_version": "0.1",
  "guideline": {
    "title": "...",
    "short_title": "...",
    "source": "...",
    "version": "...",
    "last_updated": "...",
    "url": null,
    "condition": "...",
    "population": "..."
  },
  "patient_fields": [
    {
      "field": "...",
      "type": "enum|string|bool|number|list[string]|list[object]",
      "required": true/false,
      "description": "...",
      "values": ["..."],
      "known_values": ["..."]
    }
  ],
  "field_synonyms": {
    "canonical_value": ["synonym1", "synonym2"],
    "bool_field_name": ["alternative phrasing 1", "alternative phrasing 2"]
  },
  "decisions": [
    {
      "id": "...",
      "description": "...",
      "entry_point": true/false,
      "conditions": [{"field": "...", "operator": "...", "value": "..."}],
      "recommendation": {
        "action": "...",
        "evidence_grade": "...",
        "strength": "...",
        "monitoring": "...",
        "source_section": "...",
        "source_page": null,
        "source_text": "..."
      },
      "branches": [
        {
          "condition": {"field": "...", "operator": "...", "value": "..."},
          "next_decision": "...",
          "label": "..."
        }
      ]
    }
  ]
}

CRITICAL RULES:
- source_text must be EXACT quotes from the guideline, not paraphrased
- Every recommendation must have at least one condition
- Entry points should cover the primary/first-line treatment decisions
- Branch next_decision values must reference valid decision node IDs
- Use snake_case for all IDs and field names
- Extract ALL recommendations, not just the first few
- field_synonyms must include common clinical synonyms, abbreviations, and alternative phrasings for each canonical value used in conditions
- For diagnosis fields, include the condition name as a known_value and list common alternative names as synonyms
"""


# ---------------------------------------------------------------------------
# LLM interaction
# ---------------------------------------------------------------------------


def _call_anthropic(markdown_text: str, model: str | None = None) -> str:
    """Call Anthropic API to extract decision tree."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic package required. Install with: pip install 'guideline-as-code[anthropic]'"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)
    model = model or "claude-sonnet-4-20250514"

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=EXTRACTION_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Parse this clinical guideline into "
                    f"a decision tree:\n\n{markdown_text}"
                ),
            }
        ],
    )

    return response.content[0].text


def _call_openai(markdown_text: str, model: str | None = None) -> str:
    """Call OpenAI API to extract decision tree."""
    try:
        import openai
    except ImportError:
        raise RuntimeError(
            "openai package required. "
            "Install: pip install 'guideline-as-code[openai]'"
        )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable not set."
        )

    client = openai.OpenAI(api_key=api_key)
    model = model or "gpt-4o"

    response = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {
                "role": "user",
                "content": (
                    "Parse this clinical guideline into "
                    f"a decision tree:\n\n{markdown_text}"
                ),
            },
        ],
    )

    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------


def parse_guideline(
    markdown_text: str,
    provider: str = "anthropic",
    model: str | None = None,
) -> dict:
    """Parse guideline markdown into a structured decision tree.

    Args:
        markdown_text: The guideline content in markdown format.
        provider: LLM provider — "anthropic" or "openai".
        model: Optional model name override.

    Returns:
        Dictionary conforming to the CPG schema.

    Raises:
        RuntimeError: If the LLM call fails or returns invalid JSON.
    """
    if provider == "anthropic":
        raw_response = _call_anthropic(markdown_text, model)
    elif provider == "openai":
        raw_response = _call_openai(markdown_text, model)
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'anthropic' or 'openai'.")

    # Strip markdown code fences if the LLM wrapped the response
    cleaned = raw_response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM returned invalid JSON. First 500 chars:\n{cleaned[:500]}\n\nError: {e}"
        )

    # Validate against schema
    try:
        tree = GuidelineDecisionTree(**data)
    except Exception as e:
        raise RuntimeError(f"LLM output does not conform to CPG schema: {e}")

    # Validate internal references
    _validate_references(tree)

    result = tree.model_dump(mode="json")

    # Add parse metadata for reproducibility
    from datetime import datetime, timezone

    actual_model = model
    if actual_model is None:
        actual_model = (
            "claude-sonnet-4-20250514" if provider == "anthropic"
            else "gpt-4o"
        )

    result["parse_metadata"] = {
        "provider": provider,
        "model": actual_model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_version": "0.2",
        "schema_version": "0.1",
    }

    return result


def _validate_references(tree: GuidelineDecisionTree) -> None:
    """Check that all branch next_decision values reference valid node IDs."""
    valid_ids = {node.id for node in tree.decisions}

    for node in tree.decisions:
        for branch in node.branches:
            if branch.next_decision not in valid_ids:
                raise RuntimeError(
                    f"Decision node '{node.id}' has branch pointing to "
                    f"'{branch.next_decision}' which does not exist. "
                    f"Valid IDs: {sorted(valid_ids)}"
                )
