"""CLI for herald — convert, parse, query, validate, diff, export."""

import json
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option(package_name="herald-cpg")
def cli():
    """herald — Clinical guidelines, as code.

    \b
        herald convert guideline.pdf     PDF → markdown
        herald parse   guideline.md      markdown → decision tree JSON
        herald query   guideline.json    ask questions, get answers
        herald diff    old.json new.json compare guideline versions
        herald export  guideline.json    export to FHIR PlanDefinition
    """


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None)
def convert(input_file: Path, output: Path | None):
    """Convert a guideline PDF to structured markdown."""
    from herald_cli.convert import convert_pdf
    if output is None:
        output = input_file.with_suffix(".md")
    console.print(f"[bold]Converting[/bold] {input_file.name} → {output.name}")
    result = convert_pdf(input_file)
    output.write_text(result, encoding="utf-8")
    console.print(f"[green]✓[/green] Written {output} ({result.count(chr(10))} lines)")


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None)
@click.option("--provider", type=click.Choice(["anthropic", "openai"]), default="anthropic")
@click.option("--model", type=str, default=None)
def parse(input_file: Path, output: Path | None, provider: str, model: str | None):
    """Parse guideline markdown into a decision tree JSON."""
    from herald_cli.parse import parse_guideline
    if output is None:
        output = input_file.with_suffix(".json")
    console.print(f"[bold]Parsing[/bold] {input_file.name} with {provider}")
    md = input_file.read_text(encoding="utf-8")
    tree = parse_guideline(md, provider=provider, model=model)
    output.write_text(json.dumps(tree, indent=2, ensure_ascii=False), encoding="utf-8")
    n = len(tree.get("decisions", []))
    console.print(f"[green]✓[/green] Extracted {n} decision nodes → {output}")


@cli.command()
@click.argument("input_files", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--ask", type=str, default=None, help="Single question.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--log", type=click.Path(path_type=Path), default=None,
              help="Append query + results to JSONL audit log.")
@click.option("--batch", type=click.Path(exists=True, path_type=Path), default=None,
              help="CSV file of patient records for batch processing.")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output file for batch results.")
def query(input_files, ask, fmt, log, batch, output):
    """Query parsed guideline decision trees.

    Provide one or more JSON files. Multiple files enables multi-guideline
    queries with conflict detection.

    \b
    Examples:
      herald query guideline.json --ask "45F moderate depression"
      herald query guideline.json --ask "..." --format json
      herald query guideline.json --ask "..." --log audit.jsonl
      herald query guideline.json --batch patients.csv -o results.csv
      herald query g1.json g2.json --ask "..." (multi-guideline)
    """
    from herald_cli.query import (
        MultiQueryEngine,
        QueryEngine,
        parse_csv_patients,
    )

    if not input_files:
        console.print("[red]Error: provide at least one guideline JSON.[/red]")
        raise SystemExit(1)

    guidelines = [json.loads(f.read_text(encoding="utf-8")) for f in input_files]

    # --- Batch mode ---
    if batch:
        engine = QueryEngine(guidelines[0])
        csv_text = batch.read_text(encoding="utf-8")
        patients = parse_csv_patients(csv_text)
        results = engine.query_batch(patients)

        if fmt == "json":
            out_text = json.dumps(results, indent=2, ensure_ascii=False)
        else:
            # CSV output
            import csv
            import io
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                "patient_index", "recommendation_count",
                "first_action", "decision_path",
            ])
            for r in results:
                recs = r.get("recommendations", [])
                first = recs[0] if recs else {}
                writer.writerow([
                    r["patient_index"],
                    r["recommendation_count"],
                    first.get("action", "")[:100],
                    " → ".join(first.get("decision_path", [])),
                ])
            out_text = buf.getvalue()

        if output:
            output.write_text(out_text, encoding="utf-8")
            console.print(
                f"[green]✓[/green] Processed {len(patients)} patients → {output}"
            )
        else:
            click.echo(out_text)
        return

    # --- Single/Multi guideline mode ---
    if len(guidelines) == 1:
        engine = QueryEngine(guidelines[0])
        data = guidelines[0]
        title = data.get("guideline", {}).get("title", input_files[0].stem)
        n = len(data.get("decisions", []))

        if fmt == "text":
            console.print(f"\n[bold]{title}[/bold]")
            console.print(f"[dim]{n} decision nodes loaded[/dim]\n")

        if ask:
            _handle_query(engine, ask, data, fmt, log)
        else:
            _interactive_mode(engine, data, fmt, log)
    else:
        multi = MultiQueryEngine(guidelines)
        titles = [g.get("guideline", {}).get("short_title", "?") for g in guidelines]
        if fmt == "text":
            console.print("\n[bold]Multi-guideline query[/bold]")
            console.print(f"[dim]Loaded: {', '.join(titles)}[/dim]\n")
        if ask:
            _handle_multi_query(multi, ask, guidelines, fmt, log)
        else:
            console.print(
                "[yellow]Interactive mode not supported "
                "for multi-guideline. Use --ask.[/yellow]"
            )


def _log_entry(log_path, entry):
    """Append a query+result to JSONL audit log."""
    if not log_path:
        return
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _handle_query(engine, question, guideline_data, fmt="text", log_path=None):
    from herald_cli.query import parse_patient_description

    patient = parse_patient_description(question, guideline=guideline_data)
    meta = patient.pop("_extraction_meta", {})
    results = engine.query(patient)

    # Extract blocked recommendations
    blocked = []
    for r in results:
        blocked.extend(r.pop("_blocked_siblings", []))

    if fmt == "json":
        out = {
            "patient": patient,
            "extraction_meta": meta,
            "recommendations": [_rec_to_dict(r) for r in results],
            "blocked_recommendations": [
                {
                    "action": b["recommendation"]["action"],
                    "reason": b.get("blocked_reason", ""),
                    "decision_id": b["decision_id"],
                }
                for b in blocked
            ],
            "missing_fields": [
                {"field": k, "required": v.get("required", False)}
                for k, v in meta.items() if v.get("source") == "missing"
            ],
        }
        click.echo(json.dumps(out, indent=2, ensure_ascii=False))
        _log_entry(log_path, {"query": question, "result": out})
        return

    # --- Text format ---
    console.print("[dim]Patient profile:[/dim]")
    for key, value in patient.items():
        console.print(f"  {key}: {value}")

    # Missing fields
    missing = [k for k, v in meta.items() if v.get("source") == "missing"]
    if missing:
        console.print()
        for f in missing:
            console.print(
                f"  [yellow]⚠ {f}: not extracted — required field missing[/yellow]"
            )

    # Extraction sources
    for field, info in meta.items():
        src = info.get("source", "")
        if src == "synonym":
            matched = info.get("matched", "")
            canonical = info.get("canonical", "")
            console.print(
                f"  [dim]↳ {field}: matched '{matched}'"
                f"{f' → {canonical}' if canonical else ''}[/dim]"
            )
        elif src == "auto_inferred":
            console.print(f"  [dim]↳ {field}: auto-inferred from guideline[/dim]")

    console.print()

    if not results:
        console.print("[yellow]No matching recommendations found.[/yellow]")
        if missing:
            console.print(f"[dim]Missing required: {', '.join(missing)}[/dim]")
        else:
            console.print("[dim]Try: diagnosis, age, comorbidities.[/dim]")
        _log_entry(log_path, {
            "query": question, "patient": patient,
            "recommendations": [], "blocked": [],
        })
        return

    for i, result in enumerate(results, 1):
        rec = result["recommendation"]
        priority = rec.get("priority", "")
        priority_tag = f" [{priority}]" if priority else ""
        console.print(
            f"[bold green]Recommendation {i}{priority_tag}:[/bold green] "
            f"{rec['action']}"
        )
        grade = rec.get("evidence_grade", "N/A")
        strength = rec.get("strength", "N/A")
        console.print(f"  Evidence grade: {grade} ({strength})")
        if rec.get("monitoring"):
            console.print(f"  Monitoring: {rec['monitoring']}")
        # Dosing
        dosing = rec.get("dosing")
        if dosing:
            parts = []
            if dosing.get("dose"):
                parts.append(dosing["dose"])
            if dosing.get("route"):
                parts.append(dosing["route"])
            if dosing.get("frequency"):
                parts.append(dosing["frequency"])
            if dosing.get("duration"):
                parts.append(f"for {dosing['duration']}")
            if dosing.get("weight_based"):
                parts.append("(weight-based)")
            console.print(f"  Dosing: {' '.join(parts)}")
        # Pre/post actions
        for pre in rec.get("pre_actions", []):
            console.print(f"  [cyan]↑ Before:[/cyan] {pre}")
        for post in rec.get("post_actions", []):
            console.print(f"  [cyan]↓ After:[/cyan] {post}")
        # Source
        section = rec.get("source_section", "?")
        page = rec.get("source_page", "?")
        console.print(f"  Source: Section {section}, p.{page}")
        src = rec.get("source_text", "")
        console.print(f"  [dim]\"{src}\"[/dim]")
        if result.get("path"):
            console.print(
                f"  [dim]Decision path: {' → '.join(result['path'])}[/dim]"
            )
        console.print()

    # Blocked recommendations
    if blocked:
        console.print("[bold red]⊘ Blocked recommendations:[/bold red]")
        for b in blocked:
            console.print(
                f"  [red]✗[/red] {b['recommendation']['action'][:80]}..."
            )
            console.print(
                f"    [dim]Reason: {b.get('blocked_reason', 'contraindicated')}[/dim]"
            )
        console.print()

    _log_entry(log_path, {
        "query": question, "patient": patient,
        "recommendations": [_rec_to_dict(r) for r in results],
        "blocked": [b["decision_id"] for b in blocked],
    })


def _rec_to_dict(r):
    rec = r["recommendation"]
    d = {
        "action": rec["action"],
        "evidence_grade": rec.get("evidence_grade"),
        "strength": rec.get("strength"),
        "priority": rec.get("priority"),
        "monitoring": rec.get("monitoring"),
        "source_section": rec.get("source_section"),
        "source_page": rec.get("source_page"),
        "source_text": rec.get("source_text"),
        "decision_path": r.get("path", []),
    }
    if rec.get("dosing"):
        d["dosing"] = rec["dosing"]
    if rec.get("pre_actions"):
        d["pre_actions"] = rec["pre_actions"]
    if rec.get("post_actions"):
        d["post_actions"] = rec["post_actions"]
    return d


def _handle_multi_query(multi, question, guidelines, fmt="text", log_path=None):
    from herald_cli.query import parse_patient_description
    patient = parse_patient_description(question, guideline=guidelines[0])
    for g in guidelines[1:]:
        extra = parse_patient_description(question, guideline=g)
        for k, v in extra.items():
            if k not in patient:
                patient[k] = v
    patient.pop("_extraction_meta", {})
    result = multi.query(patient)

    if fmt == "json":
        out = {
            "patient": patient,
            "recommendations": [
                {"guideline": r.get("guideline", ""),
                 "action": r["recommendation"]["action"],
                 "decision_path": r.get("path", [])}
                for r in result["recommendations"]
            ],
            "conflicts": result["conflicts"],
        }
        click.echo(json.dumps(out, indent=2, ensure_ascii=False))
        _log_entry(log_path, {"query": question, **out})
        return

    console.print("[dim]Patient profile:[/dim]")
    for k, v in patient.items():
        console.print(f"  {k}: {v}")
    console.print()

    recs = result["recommendations"]
    if not recs:
        console.print("[yellow]No matching recommendations found.[/yellow]")
        return
    for i, r in enumerate(recs, 1):
        gl = r.get("guideline", "")
        console.print(
            f"[bold green]Recommendation {i}[/bold green] [{gl}]: "
            f"{r['recommendation']['action']}"
        )
        if r.get("path"):
            console.print(f"  [dim]Path: {' → '.join(r['path'])}[/dim]")
        console.print()
    for c in result.get("conflicts", []):
        console.print("[bold red]⚠ Potential conflict:[/bold red]")
        console.print(
            f"  {c['guideline_a']}:{c['recommendation_a']} ↔ "
            f"{c['guideline_b']}:{c['recommendation_b']}"
        )
    _log_entry(log_path, {"query": question, "patient": patient,
                          "results": len(recs), "conflicts": len(result.get("conflicts", []))})


def _interactive_mode(engine, guideline_data=None, fmt="text", log_path=None):
    console.print("[bold]Interactive mode[/bold] — describe a patient.")
    console.print("[dim]Type 'quit' to exit. 'fields' for attributes.[/dim]\n")
    while True:
        try:
            q = console.input("[bold blue]> [/bold blue]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break
        if not q:
            continue
        if q.lower() in ("quit", "exit", "q"):
            break
        if q.lower() == "fields":
            _show_fields(engine)
            continue
        _handle_query(engine, q, guideline_data, fmt, log_path)


def _show_fields(engine):
    fields = engine.get_patient_fields()
    if not fields:
        console.print("[dim]No patient fields defined.[/dim]")
        return
    console.print("\n[bold]Available patient attributes:[/bold]\n")
    for f in fields:
        req = " [red](required)[/red]" if f.get("required") else ""
        desc = f.get("description", "")
        console.print(f"  [bold]{f['field']}[/bold]{req} — {desc}")
        if f.get("type") == "enum" and f.get("values"):
            console.print(f"    Values: {', '.join(f['values'])}")
        if f.get("known_values"):
            console.print(f"    Known values: {', '.join(f['known_values'])}")
        code = f.get("code")
        if code:
            console.print(f"    Code: {code.get('system', '')}|{code.get('code', '')}")
        dm = f.get("data_mapping")
        if dm:
            console.print(f"    EHR mapping: {dm.get('ehr_source', '')} → {dm.get('codelist', '')}")
    console.print()


@cli.command()
@click.argument("tree_file", type=click.Path(exists=True, path_type=Path))
@click.option("--source", type=click.Path(exists=True, path_type=Path), required=True)
def validate(tree_file: Path, source: Path):
    """Validate parsed tree against its source markdown."""
    from herald_cli.validate import print_validation_report, validate_tree
    console.print(f"[bold]Validating[/bold] {tree_file.name} against {source.name}\n")
    results = validate_tree(tree_file, source)
    print_validation_report(results, console)


@cli.command()
@click.argument("old_file", type=click.Path(exists=True, path_type=Path))
@click.argument("new_file", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["text", "json", "markdown"]), default="text")
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None)
def diff(old_file: Path, new_file: Path, fmt: str, output: Path | None):
    """Compare two versions of a parsed guideline."""
    from herald_cli.diff import diff_guidelines, format_markdown

    old = json.loads(old_file.read_text(encoding="utf-8"))
    new = json.loads(new_file.read_text(encoding="utf-8"))
    result = diff_guidelines(old, new)

    if fmt == "json":
        out_text = json.dumps(result, indent=2, ensure_ascii=False)
        if output:
            output.write_text(out_text, encoding="utf-8")
        else:
            click.echo(out_text)
        return

    if fmt == "markdown":
        md = format_markdown(result, old_file.name, new_file.name)
        if output:
            output.write_text(md, encoding="utf-8")
            console.print(f"[green]✓[/green] Written {output}")
        else:
            click.echo(md)
        return

    # Text format
    s = result["summary"]
    console.print(
        f"\n[bold]Guideline diff:[/bold] {old_file.name} → {new_file.name}\n"
    )
    console.print(
        f"  [green]+{s['nodes_added']} added[/green]  "
        f"[red]-{s['nodes_removed']} removed[/red]  "
        f"[yellow]~{s['nodes_modified']} modified[/yellow]  "
        f"[dim]={s['nodes_unchanged']} unchanged[/dim]"
    )
    if result["metadata_changes"]:
        console.print("\n[bold]Metadata changes:[/bold]")
        for c in result["metadata_changes"]:
            console.print(f"  {c['field']}: {c['old']} → {c['new']}")
    if result["added"]:
        console.print("\n[bold green]Added:[/bold green]")
        for a in result["added"]:
            console.print(f"  + {a['id']}: {a['description']}")
    if result["removed"]:
        console.print("\n[bold red]Removed:[/bold red]")
        for r in result["removed"]:
            console.print(f"  - {r['id']}: {r['description']}")
    if result["modified"]:
        console.print("\n[bold yellow]Modified:[/bold yellow]")
        for m in result["modified"]:
            console.print(f"  ~ {m['id']}:")
            for c in m["changes"]:
                if "old" in c and "new" in c:
                    console.print(f"    {c['field']}:")
                    console.print(f"      [red]- {str(c['old'])[:80]}[/red]")
                    console.print(f"      [green]+ {str(c['new'])[:80]}[/green]")
    console.print()


@cli.command(name="export")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None)
@click.option("--format", "fmt", type=click.Choice(["fhir"]), default="fhir")
def export_cmd(input_file: Path, output: Path | None, fmt: str):
    """Export a parsed guideline to FHIR PlanDefinition."""
    from herald_cli.export import export_fhir
    data = json.loads(input_file.read_text(encoding="utf-8"))
    result = export_fhir(data)
    if output is None:
        output = input_file.with_suffix(f".{fmt}.json")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]✓[/green] Exported {len(result.get('action', []))} actions → {output}")


if __name__ == "__main__":
    cli()
