"""CLI entry point for herald — three commands: convert, parse, query."""

import json
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option()
def cli():
    """herald — Clinical guidelines, as code.

    Turn any clinical practice guideline PDF into a queryable
    decision engine.

    Three commands, one pipeline:

    \b
        herald convert guideline.pdf    PDF → structured markdown
        herald parse   guideline.md     markdown → decision tree JSON
        herald query   guideline.json   ask questions, get answers
    """
    pass


@cli.command()
@click.argument(
    "input_file", type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "-o", "--output", type=click.Path(path_type=Path),
    default=None, help="Output .md path.",
)
def convert(input_file: Path, output: Path | None):
    """Convert a guideline PDF to structured markdown.

    Uses markitdown to extract text while preserving headings,
    tables, and document structure. No LLM required.
    """
    from herald_cli.convert import convert_pdf

    if output is None:
        output = input_file.with_suffix(".md")

    console.print(
        f"[bold]Converting[/bold] {input_file.name} → {output.name}"
    )

    result = convert_pdf(input_file)
    output.write_text(result, encoding="utf-8")

    lines = result.count("\n")
    console.print(f"[green]✓[/green] Written {output} ({lines} lines)")


@cli.command()
@click.argument(
    "input_file", type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "-o", "--output", type=click.Path(path_type=Path),
    default=None, help="Output .json path.",
)
@click.option(
    "--provider", type=click.Choice(["anthropic", "openai"]),
    default="anthropic", help="LLM provider.",
)
@click.option(
    "--model", type=str, default=None, help="Model name override.",
)
def parse(
    input_file: Path,
    output: Path | None,
    provider: str,
    model: str | None,
):
    """Parse guideline markdown into a decision tree JSON.

    Requires an LLM API key. Set ANTHROPIC_API_KEY or
    OPENAI_API_KEY in your environment.
    """
    from herald_cli.parse import parse_guideline

    if output is None:
        output = input_file.with_suffix(".json")

    console.print(
        f"[bold]Parsing[/bold] {input_file.name} with {provider}"
    )

    markdown_text = input_file.read_text(encoding="utf-8")
    decision_tree = parse_guideline(
        markdown_text, provider=provider, model=model,
    )

    output.write_text(
        json.dumps(decision_tree, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    n_decisions = len(decision_tree.get("decisions", []))
    console.print(
        f"[green]✓[/green] Extracted {n_decisions} decision nodes → "
        f"{output}"
    )


@cli.command()
@click.argument(
    "input_file", type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--ask", type=str, default=None,
    help="Single question. Omit for interactive mode.",
)
def query(input_file: Path, ask: str | None):
    """Query a parsed guideline decision tree.

    No LLM required — traverses the decision tree deterministically.
    Provide patient attributes and get guideline-concordant
    recommendations with source citations.
    """
    from herald_cli.query import QueryEngine

    data = json.loads(input_file.read_text(encoding="utf-8"))
    engine = QueryEngine(data)

    title = data.get("guideline", {}).get("title", input_file.stem)
    n = len(data.get("decisions", []))
    console.print(f"\n[bold]{title}[/bold]")
    console.print(f"[dim]{n} decision nodes loaded[/dim]\n")

    if ask:
        _handle_query(engine, ask)
    else:
        _interactive_mode(engine)


def _handle_query(engine, question: str):
    """Process a single query and display results."""
    from herald_cli.query import parse_patient_description

    patient = parse_patient_description(question)

    console.print("[dim]Patient profile:[/dim]")
    for key, value in patient.items():
        console.print(f"  {key}: {value}")
    console.print()

    results = engine.query(patient)

    if not results:
        console.print(
            "[yellow]No matching recommendations found.[/yellow]"
        )
        console.print(
            "[dim]Try: diagnosis, age, comorbidities, "
            "prior treatments.[/dim]"
        )
        return

    for i, result in enumerate(results, 1):
        rec = result["recommendation"]
        console.print(
            f"[bold green]Recommendation {i}:[/bold green] "
            f"{rec['action']}"
        )
        grade = rec.get("evidence_grade", "N/A")
        strength = rec.get("strength", "N/A")
        console.print(f"  Evidence grade: {grade} ({strength})")
        if rec.get("monitoring"):
            console.print(f"  Monitoring: {rec['monitoring']}")
        section = rec.get("source_section", "?")
        page = rec.get("source_page", "?")
        console.print(f"  Source: Section {section}, p.{page}")
        src = rec.get("source_text", "")
        console.print(f"  [dim]\"{src}\"[/dim]")

        if result.get("path"):
            path_str = " → ".join(result["path"])
            console.print(f"  [dim]Decision path: {path_str}[/dim]")
        console.print()


def _interactive_mode(engine):
    """Run interactive query loop."""
    console.print(
        "[bold]Interactive mode[/bold] — describe a patient "
        "to get recommendations."
    )
    console.print(
        "[dim]Type 'quit' to exit. "
        "Type 'fields' for patient attributes.[/dim]\n"
    )

    while True:
        try:
            question = console.input(
                "[bold blue]> [/bold blue]"
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            break
        if question.lower() == "fields":
            _show_fields(engine)
            continue

        _handle_query(engine, question)


def _show_fields(engine):
    """Display available patient fields."""
    fields = engine.get_patient_fields()
    if not fields:
        console.print(
            "[dim]No patient fields defined in this guideline.[/dim]"
        )
        return

    console.print("\n[bold]Available patient attributes:[/bold]\n")
    for field in fields:
        req = " [red](required)[/red]" if field.get("required") else ""
        desc = field.get("description", "")
        name = field["field"]
        console.print(f"  [bold]{name}[/bold]{req} — {desc}")
        if field.get("type") == "enum" and field.get("values"):
            vals = ", ".join(field["values"])
            console.print(f"    Values: {vals}")
        if field.get("known_values"):
            vals = ", ".join(field["known_values"])
            console.print(f"    Known values: {vals}")
    console.print()


@cli.command()
@click.argument(
    "tree_file", type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--source", type=click.Path(exists=True, path_type=Path),
    required=True, help="Source markdown to validate against.",
)
def validate(tree_file: Path, source: Path):
    """Validate parsed tree against its source markdown.

    Checks that each recommendation's source_text actually appears
    in the original markdown.
    """
    from herald_cli.validate import (
        print_validation_report,
        validate_tree,
    )

    console.print(
        f"[bold]Validating[/bold] {tree_file.name} "
        f"against {source.name}\n"
    )

    results = validate_tree(tree_file, source)
    print_validation_report(results, console)


if __name__ == "__main__":
    cli()
