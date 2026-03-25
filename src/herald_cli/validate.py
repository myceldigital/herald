"""Validate parsed decision trees against their source markdown.

Generates a human-readable diff showing each parsed recommendation alongside
the exact source text it was extracted from. This allows clinicians to verify
the parsing in minutes instead of months.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text


def validate_tree(tree_path: Path, source_path: Path) -> list[dict]:
    """Validate a parsed decision tree against its source markdown.

    For each decision node, searches the source markdown for the quoted
    source_text and reports whether it was found, its location, and any
    discrepancies.

    Args:
        tree_path: Path to the parsed decision tree JSON.
        source_path: Path to the source markdown file.

    Returns:
        List of validation results, one per decision node.
    """
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    source = source_path.read_text(encoding="utf-8")
    source_lower = source.lower()

    results = []

    for node in tree.get("decisions", []):
        node_id = node.get("id", "unknown")
        rec = node.get("recommendation", {})
        source_text = rec.get("source_text", "")
        source_section = rec.get("source_section", "")

        result = {
            "node_id": node_id,
            "action": rec.get("action", ""),
            "source_section": source_section,
            "source_text": source_text,
            "status": "unknown",
            "details": "",
        }

        if not source_text:
            result["status"] = "missing"
            result["details"] = "No source_text provided — cannot verify"
            results.append(result)
            continue

        # Search for the source text in the markdown
        search_text = source_text.lower().strip()

        if search_text in source_lower:
            result["status"] = "verified"
            # Find approximate line number
            pos = source_lower.index(search_text)
            line_num = source[:pos].count("\n") + 1
            result["details"] = f"Found at line {line_num}"
        else:
            # Try partial match (first 50 chars)
            partial = search_text[:50]
            if partial in source_lower:
                result["status"] = "partial"
                pos = source_lower.index(partial)
                line_num = source[:pos].count("\n") + 1
                result["details"] = f"Partial match at line {line_num} — verify full text"
            else:
                result["status"] = "not_found"
                result["details"] = "Source text not found in markdown — may be paraphrased"

        # Check if cited section exists in markdown
        if source_section:
            section_patterns = [
                f"# {source_section}",
                f"## {source_section}",
                f"### {source_section}",
                f"**{source_section}",
                f"{source_section}.",
                f"section {source_section}",
            ]
            section_found = any(p.lower() in source_lower for p in section_patterns)
            if not section_found:
                result["details"] += f" | Section '{source_section}' not found in headings"

        results.append(result)

    return results


def print_validation_report(results: list[dict], console: Console | None = None) -> None:
    """Print a formatted validation report to the terminal."""
    if console is None:
        console = Console()

    table = Table(title="Validation Report", show_lines=True)
    table.add_column("Node", style="bold", width=24)
    table.add_column("Status", width=12)
    table.add_column("Action", width=28)
    table.add_column("Details", width=36)

    status_styles = {
        "verified": "[green]✓ verified[/green]",
        "partial": "[yellow]~ partial[/yellow]",
        "not_found": "[red]✗ not found[/red]",
        "missing": "[dim]— missing[/dim]",
    }

    for r in results:
        table.add_row(
            r["node_id"],
            status_styles.get(r["status"], r["status"]),
            Text(r["action"], overflow="ellipsis"),
            r["details"],
        )

    console.print(table)

    # Summary
    total = len(results)
    verified = sum(1 for r in results if r["status"] == "verified")
    partial = sum(1 for r in results if r["status"] == "partial")
    not_found = sum(1 for r in results if r["status"] == "not_found")
    missing = sum(1 for r in results if r["status"] == "missing")

    console.print(f"\n[bold]Summary:[/bold] {total} nodes")
    console.print(f"  [green]✓ Verified:[/green] {verified}")
    if partial:
        console.print(f"  [yellow]~ Partial:[/yellow] {partial}")
    if not_found:
        console.print(f"  [red]✗ Not found:[/red] {not_found}")
    if missing:
        console.print(f"  [dim]— No source text:[/dim] {missing}")

    if verified == total:
        console.print(
            "\n[bold green]All recommendations verified "
            "against source text.[/bold green]"
        )
    elif not_found > 0:
        console.print(
            "\n[yellow]Some recommendations could not be verified. "
            "Review 'not found' entries — the LLM may have "
            "paraphrased the source text.[/yellow]"
        )

    # Fidelity score
    if total > 0:
        fidelity = (verified * 1.0 + partial * 0.5) / total
        console.print(
            f"\n[bold]Fidelity score:[/bold] {fidelity:.0%} "
            f"({verified} verified + {partial} partial / {total} total)"
        )
        if fidelity < 0.8:
            console.print(
                "[yellow]⚠ Fidelity below 80% — review parse output "
                "carefully before clinical use.[/yellow]"
            )


def compute_fidelity(results: list[dict]) -> dict:
    """Compute quantitative fidelity metrics."""
    total = len(results)
    if total == 0:
        return {"fidelity_score": 0, "verified": 0, "partial": 0,
                "not_found": 0, "missing": 0, "total": 0}
    verified = sum(1 for r in results if r["status"] == "verified")
    partial = sum(1 for r in results if r["status"] == "partial")
    not_found = sum(1 for r in results if r["status"] == "not_found")
    missing = sum(1 for r in results if r["status"] == "missing")
    fidelity = (verified * 1.0 + partial * 0.5) / total
    return {
        "fidelity_score": round(fidelity, 3),
        "verified": verified,
        "partial": partial,
        "not_found": not_found,
        "missing": missing,
        "total": total,
    }
