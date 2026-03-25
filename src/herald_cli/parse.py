"""Parse guideline markdown into structured decision tree JSON using LLM extraction."""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, Field

DEFAULT_MAX_OUTPUT_TOKENS = 20000
CHUNK_PARSE_CHAR_THRESHOLD = 30000
CHUNK_TARGET_CHARS = 18000
CHUNK_SHARED_CONTEXT_CHARS = 5000

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
    field_synonyms: dict[str, list[str]] = Field(default_factory=dict)
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
            "anthropic package required. Install with: pip install 'herald-cpg[anthropic]'"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)
    model = model or "claude-sonnet-4-20250514"

    response = client.messages.create(
        model=model,
        max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
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
            "Install: pip install 'herald-cpg[openai]'"
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
        max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
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


def _call_provider(markdown_text: str, provider: str, model: str | None = None) -> str:
    """Dispatch to the configured LLM provider."""
    if provider == "anthropic":
        return _call_anthropic(markdown_text, model)
    if provider == "openai":
        return _call_openai(markdown_text, model)
    raise ValueError(f"Unknown provider: {provider}. Use 'anthropic' or 'openai'.")


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
    if _should_chunk_guideline(markdown_text):
        result = _parse_guideline_chunked(markdown_text, provider, model)
        strategy = "chunked"
        chunk_count = len(result.pop("_chunk_titles", []))
        result["parse_metadata"] = _build_parse_metadata(
            provider=provider,
            model=model,
            strategy=strategy,
            chunk_count=chunk_count,
        )
        return result

    result = _parse_single_pass(markdown_text, provider, model)
    result["parse_metadata"] = _build_parse_metadata(
        provider=provider,
        model=model,
        strategy="single_pass",
    )
    return result


def _parse_single_pass(markdown_text: str, provider: str, model: str | None) -> dict:
    """Parse a guideline in one LLM call."""
    raw_response = _call_provider(markdown_text, provider, model)
    return _deserialize_tree(raw_response, validate_references=True)


def _parse_guideline_chunked(markdown_text: str, provider: str, model: str | None) -> dict:
    """Parse a large guideline section-by-section and merge the result."""
    chunks = _split_guideline_into_chunks(markdown_text)
    if len(chunks) <= 1:
        return _parse_single_pass(markdown_text, provider, model)

    shared_context = _extract_shared_context(markdown_text)
    parsed_chunks = []
    chunk_titles = []

    for title, chunk_text in chunks:
        payload = _build_chunk_payload(shared_context, title, chunk_text)
        raw_response = _call_provider(payload, provider, model)
        parsed_chunks.append(_deserialize_tree(raw_response, validate_references=False))
        chunk_titles.append(title)

    merged = _merge_chunk_trees(parsed_chunks)
    tree = GuidelineDecisionTree(**merged)
    _validate_references(tree)
    result = tree.model_dump(mode="json")
    result["_chunk_titles"] = chunk_titles
    return result


def _deserialize_tree(raw_response: str, validate_references: bool) -> dict:
    """Convert model output into validated schema data."""
    cleaned = _extract_json_payload(raw_response)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM returned invalid JSON. First 500 chars:\n{cleaned[:500]}\n\nError: {e}"
        )

    data = _sanitize_llm_tree_data(data)

    try:
        tree = GuidelineDecisionTree(**data)
    except Exception as e:
        raise RuntimeError(f"LLM output does not conform to CPG schema: {e}")

    if validate_references:
        _validate_references(tree)

    return tree.model_dump(mode="json")


def _sanitize_llm_tree_data(data: dict) -> dict:
    """Normalize common LLM schema mistakes before Pydantic validation."""
    cleaned = deepcopy(data)

    for field in cleaned.get("patient_fields", []):
        field_type = field.get("type")
        if field_type == "bool":
            field["values"] = None
            field["known_values"] = None
            continue

        for key in ("values", "known_values"):
            values = field.get(key)
            if values is None:
                continue
            if not isinstance(values, list):
                field[key] = None
                continue
            filtered = [value for value in values if isinstance(value, str)]
            field[key] = filtered or None

    for decision in cleaned.get("decisions", []):
        decision["id"] = decision.get("id") or ""
        decision["description"] = decision.get("description") or ""
        recommendation = decision.get("recommendation", {})
        for key in ("action", "evidence_grade", "strength", "source_section", "source_text"):
            recommendation[key] = recommendation.get(key) or ""

    return cleaned


def _build_parse_metadata(
    provider: str,
    model: str | None,
    strategy: str,
    chunk_count: int | None = None,
) -> dict:
    """Build reproducibility metadata for parse results."""
    from datetime import datetime, timezone

    actual_model = model
    if actual_model is None:
        actual_model = (
            "claude-sonnet-4-20250514" if provider == "anthropic"
            else "gpt-4o"
        )

    metadata = {
        "provider": provider,
        "model": actual_model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_version": "0.3",
        "schema_version": "0.1",
        "strategy": strategy,
    }
    if chunk_count is not None:
        metadata["chunk_count"] = chunk_count
    return metadata


def _extract_json_payload(raw_response: str) -> str:
    """Extract the JSON object from common LLM wrapper text.

    Models often add a short preamble before returning fenced JSON.
    Prefer the fenced payload when present; otherwise fall back to the
    outermost JSON-looking object in the response.
    """
    cleaned = raw_response.strip()

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1].strip()

    return cleaned


def _should_chunk_guideline(markdown_text: str) -> bool:
    """Decide whether the guideline is large enough to need chunked parsing."""
    if len(markdown_text) < CHUNK_PARSE_CHAR_THRESHOLD:
        return False
    return len(_split_guideline_into_chunks(markdown_text)) > 1


def _split_guideline_into_chunks(markdown_text: str) -> list[tuple[str, str]]:
    """Split a large guideline into recommendation-heavy section chunks."""
    narrowed = _extract_recommendation_window(markdown_text)
    chunks = _split_by_numbered_headings(narrowed)
    if len(chunks) < 2:
        chunks = _split_by_markdown_headings(narrowed)
    if len(chunks) < 2:
        chunks = _split_by_size(narrowed)
    return _combine_small_chunks(chunks)


def _extract_recommendation_window(markdown_text: str) -> str:
    """Try to narrow parsing to the recommendations chapter when obvious."""
    lines = markdown_text.splitlines()
    rec_re = re.compile(r"^\s*(\d+)\.\s+recommendations\b", re.IGNORECASE)
    next_major_re = re.compile(r"^\s*(\d+)\.\s+\S")
    candidates: list[str] = []

    for start_idx, line in enumerate(lines):
        match = rec_re.match(line.strip())
        if not match:
            continue

        start_num = int(match.group(1))
        end_idx = len(lines)
        for i in range(start_idx + 1, len(lines)):
            next_match = next_major_re.match(lines[i].strip())
            if next_match and int(next_match.group(1)) > start_num:
                end_idx = i
                break

        candidate = "\n".join(lines[start_idx:end_idx]).strip()
        if candidate:
            candidates.append(candidate)

    if not candidates:
        return markdown_text

    return max(candidates, key=len)


def _split_by_numbered_headings(markdown_text: str) -> list[tuple[str, str]]:
    """Split by numbered subsection headings such as 3.1, 4.2.1, etc."""
    lines = markdown_text.splitlines()
    heading_re = re.compile(r"^\s*(\d+\.\d+(?:\.\d+)*)\s+(.+\S)\s*$")
    starts: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        match = heading_re.match(line)
        if match:
            starts.append((i, f"{match.group(1)} {match.group(2)}"))

    if len(starts) < 2:
        return []

    chunks = []
    for idx, (start, title) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        if body:
            chunks.append((title, body))
    return chunks


def _split_by_markdown_headings(markdown_text: str) -> list[tuple[str, str]]:
    """Split by markdown headings if numbered headings are absent."""
    lines = markdown_text.splitlines()
    heading_re = re.compile(r"^(#{2,6})\s+(.+\S)\s*$")
    starts: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        match = heading_re.match(line)
        if match:
            starts.append((i, match.group(2)))

    if len(starts) < 2:
        return []

    chunks = []
    for idx, (start, title) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        if body:
            chunks.append((title, body))
    return chunks


def _split_by_size(markdown_text: str) -> list[tuple[str, str]]:
    """Fallback chunking by paragraph boundaries when headings are weak."""
    paragraphs = [p.strip() for p in markdown_text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [("chunk_1", markdown_text.strip())] if markdown_text.strip() else []

    chunks = []
    current = []
    current_len = 0
    chunk_num = 1

    for paragraph in paragraphs:
        extra = len(paragraph) + (2 if current else 0)
        if current and current_len + extra > CHUNK_TARGET_CHARS:
            chunks.append((f"chunk_{chunk_num}", "\n\n".join(current)))
            chunk_num += 1
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len += extra

    if current:
        chunks.append((f"chunk_{chunk_num}", "\n\n".join(current)))

    return chunks


def _combine_small_chunks(chunks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Combine very small adjacent chunks to avoid wasting LLM calls."""
    if len(chunks) <= 2:
        return chunks

    combined = []
    current_title, current_text = chunks[0]

    for title, text in chunks[1:]:
        if len(current_text) < CHUNK_TARGET_CHARS // 3:
            current_title = f"{current_title} + {title}"
            current_text = f"{current_text}\n\n{text}"
            continue
        combined.append((current_title, current_text))
        current_title, current_text = title, text

    combined.append((current_title, current_text))
    return combined


def _extract_shared_context(markdown_text: str) -> str:
    """Keep top-of-document metadata context available for each chunk."""
    return markdown_text[:CHUNK_SHARED_CONTEXT_CHARS].strip()


def _build_chunk_payload(shared_context: str, title: str, chunk_text: str) -> str:
    """Build a section-scoped extraction payload for chunk parsing."""
    return (
        "Parse this large clinical guideline section into decision-tree JSON.\n\n"
        "Use GLOBAL GUIDELINE CONTEXT only for shared metadata and consistent field naming.\n"
        "Extract recommendations ONLY from SECTION TO PARSE.\n"
        "Only create branches whose target decisions also appear in SECTION TO PARSE.\n"
        "If a downstream recommendation lies outside this section, leave branches empty.\n"
        "Keep source_text as exact quotes from SECTION TO PARSE.\n\n"
        f"GLOBAL GUIDELINE CONTEXT:\n{shared_context}\n\n"
        f"SECTION TO PARSE: {title}\n{chunk_text}"
    )


def _merge_chunk_trees(chunk_trees: list[dict]) -> dict:
    """Merge chunk-level parse outputs into one schema-compliant tree."""
    if not chunk_trees:
        raise RuntimeError("No chunk trees were produced during chunked parse.")

    merged = {
        "schema_version": "0.1",
        "guideline": _merge_guideline_meta([tree.get("guideline", {}) for tree in chunk_trees]),
        "patient_fields": _merge_patient_fields(
            [tree.get("patient_fields", []) for tree in chunk_trees]
        ),
        "field_synonyms": _merge_field_synonyms(
            [tree.get("field_synonyms", {}) for tree in chunk_trees]
        ),
        "decisions": _merge_decisions([tree.get("decisions", []) for tree in chunk_trees]),
    }
    return merged


def _merge_guideline_meta(metas: list[dict]) -> dict:
    """Merge chunk-level guideline metadata, preferring the first non-empty value."""
    merged = {
        "title": "",
        "short_title": "",
        "source": "",
        "version": "",
        "last_updated": "",
        "url": None,
        "condition": "",
        "population": "",
    }

    for meta in metas:
        for key in merged:
            value = meta.get(key)
            if value in ("", None):
                continue
            if merged[key] in ("", None):
                merged[key] = value
            elif key in ("title", "population", "condition") and len(str(value)) > len(
                str(merged[key])
            ):
                merged[key] = value

    return merged


def _merge_patient_fields(field_lists: list[list[dict]]) -> list[dict]:
    """Merge patient fields by name while preserving enum vocabulary."""
    merged: dict[str, dict] = {}

    for fields in field_lists:
        for field in fields:
            name = field.get("field")
            if not name:
                continue
            if name not in merged:
                merged[name] = deepcopy(field)
                continue

            current = merged[name]
            current["type"] = _select_field_type(current.get("type"), field.get("type"))
            current["required"] = bool(current.get("required")) or bool(field.get("required"))

            current_desc = current.get("description") or ""
            new_desc = field.get("description") or ""
            if len(new_desc) > len(current_desc):
                current["description"] = new_desc

            merged_values = _merge_unique(current.get("values"), field.get("values"))
            merged_known = _merge_unique(
                current.get("known_values"),
                field.get("known_values"),
            )
            current["values"] = merged_values if merged_values else None
            current["known_values"] = merged_known if merged_known else None

    return list(merged.values())


def _merge_field_synonyms(synonym_maps: list[dict[str, list[str]]]) -> dict[str, list[str]]:
    """Merge synonym dictionaries while preserving insertion order."""
    merged: dict[str, list[str]] = {}

    for synonym_map in synonym_maps:
        for key, values in synonym_map.items():
            merged[key] = _merge_unique(merged.get(key), values)

    return merged


def _merge_decisions(decision_lists: list[list[dict]]) -> list[dict]:
    """Merge decision nodes, renaming conflicting IDs deterministically."""
    merged: list[dict] = []
    by_id: dict[str, dict] = {}
    used_ids: set[str] = set()

    for decisions in decision_lists:
        local = [deepcopy(decision) for decision in decisions]
        id_map: dict[str, str] = {}

        for decision in local:
            original_id = decision.get("id", "")
            if not original_id:
                continue

            if original_id in by_id and _decisions_equivalent(by_id[original_id], decision):
                id_map[original_id] = original_id
                continue

            new_id = original_id
            if new_id in used_ids:
                new_id = _make_unique_decision_id(original_id, decision, used_ids)
            id_map[original_id] = new_id
            used_ids.add(new_id)

        for decision in local:
            original_id = decision.get("id", "")
            target_id = id_map.get(original_id, original_id)

            for branch in decision.get("branches", []):
                next_id = branch.get("next_decision")
                if next_id in id_map:
                    branch["next_decision"] = id_map[next_id]

            if target_id in by_id and _decisions_equivalent(by_id[target_id], decision):
                _merge_decision_in_place(by_id[target_id], decision)
                continue

            decision["id"] = target_id
            merged.append(decision)
            by_id[target_id] = decision

    return merged


def _merge_unique(first: list[Any] | None, second: list[Any] | None) -> list[Any]:
    """Merge two lists while preserving order and removing duplicates."""
    merged = []
    seen = set()

    for value in [*(first or []), *(second or [])]:
        if isinstance(value, str):
            dedupe_key = value.lower()
        else:
            dedupe_key = json.dumps(value, sort_keys=True, default=str)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        merged.append(value)

    return merged


def _select_field_type(existing: str | None, new: str | None) -> str:
    """Pick the more specific of two field types."""
    if existing == new:
        return existing or "string"
    specificity = {
        "enum": 4,
        "list[object]": 4,
        "list[string]": 3,
        "bool": 3,
        "number": 3,
        "string": 1,
    }
    existing_score = specificity.get(existing or "string", 0)
    new_score = specificity.get(new or "string", 0)
    return existing if existing_score >= new_score else (new or "string")


def _decisions_equivalent(left: dict, right: dict) -> bool:
    """Detect effectively duplicate decision nodes across chunks."""
    left_rec = left.get("recommendation", {})
    right_rec = right.get("recommendation", {})
    return (
        left.get("description", "") == right.get("description", "")
        and left.get("conditions", []) == right.get("conditions", [])
        and left_rec.get("action", "") == right_rec.get("action", "")
        and left_rec.get("source_text", "") == right_rec.get("source_text", "")
    )


def _merge_decision_in_place(target: dict, incoming: dict) -> None:
    """Merge two equivalent decisions without duplicating content."""
    target["entry_point"] = bool(target.get("entry_point")) or bool(incoming.get("entry_point"))
    target["branches"] = [
        branch
        for branch in _merge_unique(target.get("branches"), incoming.get("branches"))
    ]


def _make_unique_decision_id(base_id: str, decision: dict, used_ids: set[str]) -> str:
    """Generate a deterministic unique ID for colliding decision names."""
    source_section = (
        decision.get("recommendation", {}).get("source_section", "") or ""
    ).strip().replace(".", "_")
    suffix_base = source_section or "chunk"
    candidate = f"{base_id}_{suffix_base}"
    counter = 2

    while candidate in used_ids:
        candidate = f"{base_id}_{suffix_base}_{counter}"
        counter += 1

    return candidate


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
