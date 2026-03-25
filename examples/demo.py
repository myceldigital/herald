#!/usr/bin/env python3
"""Quick demo of Herald using shipped synthetic guidelines. No API key needed."""

import json
from pathlib import Path

from rich.console import Console

from herald_cli.query import QueryEngine, parse_patient_description

console = Console()

DEMO_GUIDELINES = [
    {
        "file": "synthetic_meningitis_guideline.json",
        "label": "Acute bacterial meningitis",
        "queries": [
            "68F, suspected meningitis",
            "42M, suspected meningitis, severe penicillin allergy",
            "34F, suspected meningitis, immunocompromised",
        ],
    },
    {
        "file": "synthetic_adhd_guideline.json",
        "label": "Adult ADHD management",
        "queries": [
            "34F, ADHD confirmed, no comorbidities",
            "28M, ADHD, comorbid anxiety disorder",
            "40M, ADHD, tried methylphenidate with no response",
        ],
    },
]


def _run_guideline_demo(guideline_path: Path, label: str, queries: list[str]) -> None:
    if not guideline_path.exists():
        console.print(f"[red]Error:[/red] {guideline_path.name} not found")
        return

    data = json.loads(guideline_path.read_text(encoding="utf-8"))
    engine = QueryEngine(data)

    title = data["guideline"]["title"]
    n_decisions = len(data["decisions"])

    console.print(f"\n[bold]{label}[/bold] - {title}")
    console.print(f"[dim]{n_decisions} decision nodes loaded[/dim]")
    console.print(f"[dim]Source: {data['guideline']['source']}[/dim]\n")

    for query in queries:
        console.print(f"[bold blue]> {query}[/bold blue]\n")

        patient = parse_patient_description(query, guideline=data)
        results = engine.query(patient)

        if not results:
            console.print("  [yellow]No matching recommendations.[/yellow]\n")
            continue

        for result in results:
            rec = result["recommendation"]
            action = rec["action"]
            if len(action) > 100:
                action = action[:100] + "..."
            console.print(f"  [green]-> {action}[/green]")
            console.print(
                f"    Evidence: {rec.get('evidence_grade', '?')} ({rec.get('strength', '?')})"
            )
            console.print(
                f"    Source: Section {rec.get('source_section', '?')}, p.{rec.get('source_page', '?')}"
            )
            if result.get("path"):
                console.print(f"    [dim]Path: {' -> '.join(result['path'])}[/dim]")
            console.print()

        console.print("-" * 72)


def main():
    console.print("\n[bold]Herald synthetic demo[/bold]")
    console.print("[dim]Shows deterministic querying on shipped example guidelines.[/dim]")
    console.print("=" * 72)

    base = Path(__file__).parent
    for demo in DEMO_GUIDELINES:
        _run_guideline_demo(base / demo["file"], demo["label"], demo["queries"])

    console.print("\n[bold]Demo complete.[/bold] Try interactive mode:")
    console.print("  herald query examples/synthetic_meningitis_guideline.json")
    console.print("  herald query examples/synthetic_adhd_guideline.json\n")


if __name__ == "__main__":
    main()
