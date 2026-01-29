"""Plan command for BOB CLI.

Uses Claude Opus with the confidence-driven 3-phase pipeline to generate
or enhance feature plans from application specs.

Pipeline phases:
  1. PLAN    — Generate tasks with dual confidence scores
  2. REFINE  — Loop until all confidence > threshold
  3. VALIDATE — Syntax-check scripts, reject trivial tests

Planning ALWAYS uses Opus for deep reasoning about architecture,
verification, and task decomposition.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from bob.database.manager import DatabaseManager
from bob.state import StateManager


def _display_confidence_summary(
    console: Console, plan_data: dict, threshold: float
) -> None:
    """Display a rich table summarizing task confidence scores."""
    tasks = plan_data.get("tasks", [])
    if not tasks:
        return

    table = Table(
        title="Task Confidence Scores",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("ID", style="bold", width=8)
    table.add_column("Title", width=40)
    table.add_column("Impl", justify="center", width=6)
    table.add_column("Verify", justify="center", width=6)
    table.add_column("Priority", justify="center", width=8)
    table.add_column("Status", justify="center", width=6)

    above = 0
    for t in tasks:
        impl = t.get("implementation_confidence", 0.0)
        ver = t.get("verification_confidence", 0.0)
        priority = t.get("priority", "medium")
        ok = impl >= threshold and ver >= threshold

        impl_color = "green" if impl >= threshold else ("yellow" if impl >= 0.7 else "red")
        ver_color = "green" if ver >= threshold else ("yellow" if ver >= 0.7 else "red")

        table.add_row(
            t.get("id", "?"),
            (t.get("title", "")[:38] + "…") if len(t.get("title", "")) > 40 else t.get("title", ""),
            f"[{impl_color}]{impl:.2f}[/{impl_color}]",
            f"[{ver_color}]{ver:.2f}[/{ver_color}]",
            priority,
            "[green]✓[/green]" if ok else "[yellow]⚠[/yellow]",
        )
        if ok:
            above += 1

    console.print()
    console.print(table)
    console.print(
        f"\n  [bold]{above}/{len(tasks)}[/bold] tasks at or above "
        f"threshold ({threshold})\n"
    )


def _display_warnings(console: Console, warnings: list[str]) -> None:
    """Display validation warnings."""
    if not warnings:
        return
    console.print(f"\n[yellow]⚠ {len(warnings)} validation warning(s):[/yellow]")
    for w in warnings:
        console.print(f"  [yellow]• {w}[/yellow]")
    console.print()


@click.command()
@click.argument("spec_file", required=False)
@click.option(
    "--enhance",
    is_flag=True,
    help="Enhance existing spec with better verification (keep same tasks)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output path for generated spec (default: <workspace>/generated_spec.yaml)",
)
@click.option(
    "--thinking-budget",
    type=int,
    default=16000,
    help="Thinking token budget for Opus (default: 16000)",
)
@click.option(
    "--confidence-threshold",
    type=float,
    default=0.9,
    help="Minimum confidence score to accept tasks (default: 0.9)",
)
@click.option(
    "--max-refinement-iterations",
    type=int,
    default=3,
    help="Max refinement loop iterations (default: 3)",
)
@click.option(
    "--no-research",
    is_flag=True,
    help="Disable research (web search) during planning",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def plan(
    ctx: click.Context,
    spec_file: Optional[str],
    enhance: bool,
    output: Optional[str],
    thinking_budget: int,
    confidence_threshold: float,
    max_refinement_iterations: int,
    no_research: bool,
    json_output: bool,
) -> None:
    """Generate or enhance a feature plan using Claude Opus.

    \\b
    BOB's confidence-driven planning pipeline:

    \\b
    Phase 1: PLAN
      Opus generates tasks with dual confidence scores:
        - implementation_confidence: "Can an agent build this atomically?"
        - verification_confidence: "Will verify_script catch failures?"

    \\b
    Phase 2: REFINE
      Loop until all scores > threshold:
        - Low implementation → break into sub-tasks
        - Low verification → research & write real behavioral tests
        - Max 3 iterations (configurable)

    \\b
    Phase 3: VALIDATE
      - Syntax-check all verify_scripts (bash -n)
      - Flag trivial checks (test -f) as failures
      - Ensure critical/high tasks have expected_outputs

    \\b
    Examples:
      bob plan app_spec.yaml                          # Full pipeline
      bob plan app_spec.yaml --confidence-threshold 0.8  # Lower bar
      bob plan app_spec.yaml --max-refinement-iterations 5
      bob plan app_spec.yaml --no-research            # Skip web search
      bob plan --enhance                              # Refine existing spec

    \\b
    After planning:
      bob sync          # Import the generated tasks
      bob run           # Start implementation
    """
    console = Console()

    # Get database
    db = DatabaseManager(ctx.obj.db_path)

    # Determine project context
    project_id = ctx.obj.project_id
    if not project_id:
        state = StateManager()
        project_id = state.get_active_project()

    project = db.get_project(project_id) if project_id else None
    workspace_dir = project.workspace_dir if project else "."
    project_dir = Path(workspace_dir)

    enable_research = not no_research

    if enhance:
        # Enhance existing spec
        if not project:
            click.echo("✗ No active project. Use 'bob project use <name>' first.", err=True)
            sys.exit(1)

        spec_path = project.spec_source.replace("file://", "")
        if not Path(spec_path).exists():
            click.echo(f"✗ Spec file not found: {spec_path}", err=True)
            sys.exit(1)

        if not json_output:
            console.print()
            console.print("[bold cyan]🧠 Enhancing spec with confidence-driven pipeline[/bold cyan]")
            console.print(f"   Spec: {spec_path}")
            console.print(f"   Model: claude-opus-4-5-20251101")
            console.print(f"   Thinking budget: {thinking_budget} tokens")
            console.print(f"   Confidence threshold: {confidence_threshold}")
            console.print(f"   Max refinement iterations: {max_refinement_iterations}")
            console.print(f"   Research: {'enabled' if enable_research else 'disabled'}")
            console.print()

        from bob.orchestrator.feature_planner import enhance_existing_spec

        success, result = asyncio.run(enhance_existing_spec(
            spec_path=spec_path,
            workspace_dir=workspace_dir,
            project_dir=project_dir,
            enable_thinking=True,
            thinking_budget=thinking_budget,
            confidence_threshold=confidence_threshold,
            max_refinement_iterations=max_refinement_iterations,
            enable_research=enable_research,
        ))

        if success:
            output_path = output or str(Path(workspace_dir) / "enhanced_spec.yaml")
            Path(output_path).write_text(result)
            if json_output:
                click.echo(json.dumps({"status": "success", "output": output_path}))
            else:
                console.print(f"[green]✓ Enhanced spec written to: {output_path}[/green]")
                console.print()
                console.print("Next steps:")
                console.print(f"  1. Review: cat {output_path}")
                console.print(f"  2. Replace spec: cp {output_path} {spec_path}")
                console.print(f"  3. Sync: bob sync --force")
                console.print(f"  4. Run: bob run")
        else:
            if json_output:
                click.echo(json.dumps({"status": "error", "error": result}))
            else:
                console.print(f"[red]✗ Enhancement failed: {result}[/red]")
            sys.exit(1)

    else:
        # Generate from spec file via 3-phase pipeline
        if not spec_file:
            click.echo("✗ Provide a spec file: bob plan <spec_file>", err=True)
            click.echo("  Or use --enhance to improve existing project spec", err=True)
            sys.exit(1)

        spec_path = Path(spec_file)
        if not spec_path.exists():
            click.echo(f"✗ Spec file not found: {spec_file}", err=True)
            sys.exit(1)

        spec_content = spec_path.read_text()

        if not json_output:
            console.print()
            console.print("[bold cyan]🧠 Confidence-Driven Planning Pipeline[/bold cyan]")
            console.print(f"   Spec: {spec_file}")
            console.print(f"   Model: claude-opus-4-5-20251101")
            console.print(f"   Thinking budget: {thinking_budget} tokens")
            console.print(f"   Confidence threshold: {confidence_threshold}")
            console.print(f"   Max refinement iterations: {max_refinement_iterations}")
            console.print(f"   Research: {'enabled' if enable_research else 'disabled'}")
            console.print()

        from bob.orchestrator.feature_planner import FeaturePlanner

        planner = FeaturePlanner(
            workspace_dir=workspace_dir,
            project_dir=project_dir,
            model="claude-opus-4-5-20251101",
            thinking_budget=thinking_budget,
            confidence_threshold=confidence_threshold,
            max_refinement_iterations=max_refinement_iterations,
            enable_research=enable_research,
        )

        try:
            output_path_str, plan_data, warnings = asyncio.run(
                planner.run(spec_content)
            )
        except Exception as e:
            if json_output:
                click.echo(json.dumps({"status": "error", "error": str(e)}))
            else:
                console.print(f"[red]✗ Planning failed: {e}[/red]")
            sys.exit(1)

        # Override output path if specified
        final_output = output or output_path_str
        if output and output != output_path_str:
            Path(output).write_text(Path(output_path_str).read_text())
            final_output = output

        if json_output:
            click.echo(json.dumps({
                "status": "success",
                "output": final_output,
                "tasks": len(plan_data.get("tasks", [])),
                "warnings": len(warnings),
                "confidence_threshold": confidence_threshold,
            }))
        else:
            # Display confidence summary table
            _display_confidence_summary(console, plan_data, confidence_threshold)

            # Display warnings
            _display_warnings(console, warnings)

            console.print(f"[green]✓ Feature plan generated: {final_output}[/green]")
            console.print()
            console.print("Next steps:")
            console.print(f"  1. Review: cat {final_output}")
            console.print(
                f"  2. Create project: bob project create <name> "
                f"{workspace_dir} file://{final_output}"
            )
            console.print(f"  3. Sync: bob sync")
            console.print(f"  4. Run: bob run")
