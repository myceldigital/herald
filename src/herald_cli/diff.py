"""Compare two versions of a parsed guideline decision tree."""

from __future__ import annotations

from typing import Any


def diff_guidelines(old: dict, new: dict) -> dict:
    """Diff two guideline decision trees.

    Returns a structured diff with added, removed, and modified nodes.
    """
    old_decisions = {d["id"]: d for d in old.get("decisions", [])}
    new_decisions = {d["id"]: d for d in new.get("decisions", [])}

    old_ids = set(old_decisions.keys())
    new_ids = set(new_decisions.keys())

    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    common = sorted(old_ids & new_ids)

    modified = []
    unchanged = []

    for node_id in common:
        changes = _diff_node(old_decisions[node_id], new_decisions[node_id])
        if changes:
            modified.append({"id": node_id, "changes": changes})
        else:
            unchanged.append(node_id)

    # Metadata diff
    meta_changes = _diff_metadata(
        old.get("guideline", {}), new.get("guideline", {})
    )

    # Field changes
    old_fields = {f["field"]: f for f in old.get("patient_fields", [])}
    new_fields = {f["field"]: f for f in new.get("patient_fields", [])}
    fields_added = sorted(set(new_fields) - set(old_fields))
    fields_removed = sorted(set(old_fields) - set(new_fields))

    return {
        "summary": {
            "nodes_added": len(added),
            "nodes_removed": len(removed),
            "nodes_modified": len(modified),
            "nodes_unchanged": len(unchanged),
            "fields_added": len(fields_added),
            "fields_removed": len(fields_removed),
        },
        "metadata_changes": meta_changes,
        "added": [
            {"id": nid, "description": new_decisions[nid].get("description", "")}
            for nid in added
        ],
        "removed": [
            {"id": nid, "description": old_decisions[nid].get("description", "")}
            for nid in removed
        ],
        "modified": modified,
        "fields_added": fields_added,
        "fields_removed": fields_removed,
    }


def _diff_node(old: dict, new: dict) -> list[dict]:
    """Compare two decision nodes and return a list of changes."""
    changes = []

    # Compare recommendation action text
    old_action = old.get("recommendation", {}).get("action", "")
    new_action = new.get("recommendation", {}).get("action", "")
    if old_action != new_action:
        changes.append({
            "field": "recommendation.action",
            "old": old_action,
            "new": new_action,
        })

    # Compare evidence grade
    old_grade = old.get("recommendation", {}).get("evidence_grade", "")
    new_grade = new.get("recommendation", {}).get("evidence_grade", "")
    if old_grade != new_grade:
        changes.append({
            "field": "recommendation.evidence_grade",
            "old": old_grade,
            "new": new_grade,
        })

    # Compare strength
    old_str = old.get("recommendation", {}).get("strength", "")
    new_str = new.get("recommendation", {}).get("strength", "")
    if old_str != new_str:
        changes.append({
            "field": "recommendation.strength",
            "old": old_str,
            "new": new_str,
        })

    # Compare conditions
    old_conds = _serialize(old.get("conditions", []))
    new_conds = _serialize(new.get("conditions", []))
    if old_conds != new_conds:
        changes.append({
            "field": "conditions",
            "old": old.get("conditions", []),
            "new": new.get("conditions", []),
        })

    # Compare branches
    old_branches = _serialize(old.get("branches", []))
    new_branches = _serialize(new.get("branches", []))
    if old_branches != new_branches:
        changes.append({
            "field": "branches",
            "old_count": len(old.get("branches", [])),
            "new_count": len(new.get("branches", [])),
        })

    return changes


def _diff_metadata(old: dict, new: dict) -> list[dict]:
    changes = []
    for key in set(list(old.keys()) + list(new.keys())):
        if old.get(key) != new.get(key):
            changes.append({
                "field": key,
                "old": old.get(key),
                "new": new.get(key),
            })
    return changes


def _serialize(obj: Any) -> str:
    """Deterministic serialization for comparison."""
    import json
    return json.dumps(obj, sort_keys=True, default=str)


def format_markdown(result: dict, old_name: str = "v1", new_name: str = "v2") -> str:
    """Format diff result as markdown suitable for email distribution."""
    s = result["summary"]
    lines = [
        f"# Guideline Update: {old_name} → {new_name}\n",
        f"**{s['nodes_added']}** recommendations added, "
        f"**{s['nodes_removed']}** removed, "
        f"**{s['nodes_modified']}** modified, "
        f"{s['nodes_unchanged']} unchanged.\n",
    ]

    if result["metadata_changes"]:
        lines.append("## Metadata Changes\n")
        for c in result["metadata_changes"]:
            lines.append(f"- **{c['field']}**: {c['old']} → {c['new']}")
        lines.append("")

    if result["added"]:
        lines.append("## New Recommendations\n")
        for a in result["added"]:
            lines.append(f"- **{a['id']}**: {a['description']}")
        lines.append("")

    if result["removed"]:
        lines.append("## Removed Recommendations\n")
        for r in result["removed"]:
            lines.append(f"- ~~{r['id']}~~: {r['description']}")
        lines.append("")

    if result["modified"]:
        lines.append("## Modified Recommendations\n")
        for m in result["modified"]:
            lines.append(f"### {m['id']}\n")
            for c in m["changes"]:
                if "old" in c and "new" in c:
                    lines.append(f"**{c['field']}**:")
                    lines.append(f"- Before: {c['old']}")
                    lines.append(f"- After: {c['new']}")
                    lines.append("")
        lines.append("")

    if result["fields_added"]:
        lines.append(
            f"## New Patient Fields: {', '.join(result['fields_added'])}\n"
        )
    if result["fields_removed"]:
        lines.append(
            f"## Removed Patient Fields: {', '.join(result['fields_removed'])}\n"
        )

    return "\n".join(lines)
