#!/usr/bin/env python3
"""Quick demo of herald query engine using pre-parsed synthetic guideline. No API key needed."""

import json
from pathlib import Path

from rich.console import Console

from herald_cli.query import QueryEngine, parse_patient_description

console = Console()

EXAMPLES = [
    "34F, ADHD confirmed, no comorbidities",
    "28M, ADHD, comorbid anxiety disorder",
    "42F, ADHD, comorbid depression, PHQ-9 score 18",
    "35M, ADHD, history of substance use disorder",
    "55F, ADHD, cardiac history, previous MI",
    "29F, ADHD, pregnant",
    "31F, ADHD, breastfeeding",
    "40M, ADHD, tried methylphenidate with no response",
    "38F, ADHD, comorbid anxiety, tried concerta with partial response and insomnia",
    "45M, ADHD with tics, no prior treatment",
]


def main():
    guideline_path = Path(__file__).parent / "synthetic_adhd_guideline.json"

    if not guideline_path.exists():
        console.print("[red]Error:[/red] synthetic_adhd_guideline.json not found")
        return

    data = json.loads(guideline_path.read_text(encoding="utf-8"))
    engine = QueryEngine(data)

    title = data["guideline"]["title"]
    n_decisions = len(data["decisions"])

    console.print(f"\n[bold]{title}[/bold]")
    console.print(f"[dim]{n_decisions} decision nodes loaded from synthetic guideline[/dim]")
    console.print(f"[dim]Source: {data['guideline']['source']}[/dim]\n")
    console.print("[bold]Running example queries:[/bold]\n")
    console.print("=" * 72)

    for example in EXAMPLES:
        console.print(f"\n[bold blue]> {example}[/bold blue]\n")

        patient = parse_patient_description(example)
        results = engine.query(patient)

        if not results:
            console.print("  [yellow]No matching recommendations.[/yellow]")
        else:
            for r in results:
                rec = r["recommendation"]
                console.print(f"  [green]→ {rec['action'][:100]}...[/green]" if len(rec['action']) > 100 else f"  [green]→ {rec['action']}[/green]")
                console.print(f"    Evidence: {rec.get('evidence_grade', '?')} ({rec.get('strength', '?')})")
                console.print(f"    Source: Section {rec.get('source_section', '?')}, p.{rec.get('source_page', '?')}")
                if r.get("path"):
                    console.print(f"    [dim]Path: {' → '.join(r['path'])}[/dim]")
                console.print()

        console.print("-" * 72)

    console.print("\n[bold]Demo complete.[/bold] Try interactive mode:")
    console.print("  herald query examples/synthetic_adhd_guideline.json\n")


if __name__ == "__main__":
    main()
