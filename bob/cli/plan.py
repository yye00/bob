"""Plan command for BOB CLI.

Uses Claude Opus to generate or enhance feature plans from application specs.
Planning ALWAYS uses Opus for deep reasoning about architecture, verification,
and task decomposition. Implementation uses Sonnet (with Opus escalation).
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from bob.database.manager import DatabaseManager
from bob.state import StateManager


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
    json_output: bool,
) -> None:
    """Generate or enhance a feature plan using Claude Opus.

    \\b
    BOB uses two phases:
      1. PLANNING (this command) — Always uses Opus for deep reasoning
      2. IMPLEMENTATION (bob run) — Uses Sonnet, escalates to Opus on failure

    \\b
    Planning generates:
      - Detailed task breakdown with proper dependencies
      - Real verify_scripts that test actual behavior
      - Meaningful expected_outputs with must_contain patterns
      - Specific, measurable acceptance criteria

    \\b
    Examples:
      bob plan app_spec.yaml              # Generate tasks from high-level spec
      bob plan --enhance                  # Enhance current project's spec
      bob plan app_spec.yaml -o tasks.yaml  # Output to specific file

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
            console.print("[bold cyan]🧠 Enhancing spec with Opus...[/bold cyan]")
            console.print(f"   Spec: {spec_path}")
            console.print(f"   Model: claude-opus-4-5-20251101 (always Opus for planning)")
            console.print(f"   Thinking budget: {thinking_budget} tokens")
            console.print()

        from bob.orchestrator.feature_planner import enhance_existing_spec

        success, result = asyncio.run(enhance_existing_spec(
            spec_path=spec_path,
            workspace_dir=workspace_dir,
            project_dir=project_dir,
            enable_thinking=True,
            thinking_budget=thinking_budget,
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
        # Generate from spec file
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
            console.print("[bold cyan]🧠 Generating feature plan with Opus...[/bold cyan]")
            console.print(f"   Spec: {spec_file}")
            console.print(f"   Model: claude-opus-4-5-20251101 (always Opus for planning)")
            console.print(f"   Thinking budget: {thinking_budget} tokens")
            console.print()

        from bob.orchestrator.feature_planner import generate_feature_plan

        success, result, generated_path = asyncio.run(generate_feature_plan(
            spec_content=spec_content,
            workspace_dir=workspace_dir,
            project_dir=project_dir,
            enable_thinking=True,
            thinking_budget=thinking_budget,
        ))

        if success:
            output_path = output or generated_path or str(Path(workspace_dir) / "generated_spec.yaml")
            if not generated_path or output:
                Path(output_path).write_text(result)

            if json_output:
                click.echo(json.dumps({"status": "success", "output": output_path}))
            else:
                console.print(f"[green]✓ Feature plan generated: {output_path}[/green]")
                console.print()
                console.print("Next steps:")
                console.print(f"  1. Review: cat {output_path}")
                console.print(f"  2. Create project: bob project create <name> {workspace_dir} file://{output_path}")
                console.print(f"  3. Sync: bob sync")
                console.print(f"  4. Run: bob run")
        else:
            if json_output:
                click.echo(json.dumps({"status": "error", "error": result}))
            else:
                console.print(f"[red]✗ Planning failed: {result}[/red]")
            sys.exit(1)
