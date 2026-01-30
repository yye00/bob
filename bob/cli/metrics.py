"""Metrics commands for BOB framework.

Display telemetry and metrics from previous runs, including per-task
attempt counts, debug rates, verification results, and wall clock time.
"""

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from bob.database.manager import DatabaseManager
from bob.models.base import ProjectStatus
from bob.observability.telemetry import RunTelemetry


def _find_workspace(db: DatabaseManager, project_id: Optional[str] = None) -> Optional[Path]:
    """Find the workspace directory for the active or specified project."""
    if project_id:
        project = db.get_project(project_id)
        if project:
            return Path(project.workspace_dir)
        return None

    projects = db.list_projects(status=ProjectStatus.ACTIVE, limit=1)
    if projects:
        return Path(projects[0].workspace_dir)
    return None


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}m {secs:.0f}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


@click.command("metrics")
@click.option(
    "--run",
    "run_id",
    help="Show metrics for a specific run ID",
)
@click.option(
    "--task",
    "task_id",
    help="Show metrics for a specific task (spec_id)",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def metrics(
    ctx: click.Context,
    run_id: Optional[str],
    task_id: Optional[str],
    json_output: bool,
) -> None:
    """Show run metrics and telemetry.

    \b
    Display metrics from previous runs including tasks completed,
    attempt counts, debug rates, and wall clock time.

    \b
    Examples:
      bob metrics                     # Show last run summary
      bob metrics --run <run-id>      # Show specific run
      bob metrics --task F001         # Show task history across runs
      bob metrics --json              # JSON output
    """
    global_ctx = ctx.obj

    if global_ctx and global_ctx.json_output:
        json_output = True

    db = DatabaseManager(global_ctx.db_path if global_ctx else Path.home() / ".bob" / "bob.db")

    project_id = global_ctx.project_id if global_ctx else None
    workspace = _find_workspace(db, project_id)

    if not workspace:
        if json_output:
            click.echo(json.dumps({"error": "No active project found"}))
        else:
            click.echo("✗ No active project found")
        return

    # List available runs
    runs = RunTelemetry.list_runs(workspace)
    if not runs:
        if json_output:
            click.echo(json.dumps({"error": "No telemetry data found", "workspace": str(workspace)}))
        else:
            click.echo("✗ No telemetry data found")
            click.echo(f"  Workspace: {workspace}")
            click.echo("  Run 'bob run' to generate telemetry data.")
        return

    # Show specific task history across all runs
    if task_id:
        _show_task_history(runs, task_id, json_output)
        return

    # Find the requested run
    if run_id:
        target_run = None
        for run_path in runs:
            try:
                data = RunTelemetry.load(run_path)
                if data.get("run_id") == run_id:
                    target_run = data
                    break
            except Exception:
                continue
        if not target_run:
            if json_output:
                click.echo(json.dumps({"error": f"Run '{run_id}' not found"}))
            else:
                click.echo(f"✗ Run '{run_id}' not found")
                click.echo("\nAvailable runs:")
                for rp in runs[:10]:
                    try:
                        d = RunTelemetry.load(rp)
                        click.echo(f"  {d.get('run_id', rp.stem)}")
                    except Exception:
                        pass
            return
        run_data = target_run
    else:
        # Default: show last run
        try:
            run_data = RunTelemetry.load(runs[0])
        except Exception as e:
            if json_output:
                click.echo(json.dumps({"error": f"Failed to load telemetry: {e}"}))
            else:
                click.echo(f"✗ Failed to load telemetry: {e}")
            return

    # Output
    if json_output:
        click.echo(json.dumps(run_data, indent=2, default=str))
        return

    _display_run_summary(run_data)


def _display_run_summary(run_data: dict) -> None:
    """Display a formatted run summary."""
    console = Console()

    run_id = run_data.get("run_id", "unknown")
    started = run_data.get("started_at", "N/A")
    ended = run_data.get("ended_at", "N/A")
    wall_clock = run_data.get("wall_clock_seconds", 0)
    tasks_completed = run_data.get("tasks_completed", 0)
    tasks_failed = run_data.get("tasks_failed", 0)
    total_tasks = run_data.get("total_tasks", 0)
    total_attempts = run_data.get("total_attempts", 0)
    total_debug = run_data.get("total_debug_attempts", 0)

    console.print()
    console.print(f"[bold cyan]Run: {run_id}[/bold cyan]")
    console.print()
    console.print(f"  Started:    {started}")
    console.print(f"  Ended:      {ended}")
    console.print(f"  Duration:   {_format_duration(wall_clock)}")
    console.print()
    console.print(f"  Tasks:      {total_tasks} total, [green]{tasks_completed} completed[/green], [red]{tasks_failed} failed[/red]")
    console.print(f"  Attempts:   {total_attempts} total, {total_debug} debug")

    if total_attempts > 0:
        debug_rate = (total_debug / total_attempts) * 100
        console.print(f"  Debug rate: {debug_rate:.1f}%")
    console.print()

    # Per-task table
    tasks = run_data.get("tasks", {})
    if tasks:
        table = Table(title="Task Details", show_header=True)
        table.add_column("Spec ID", style="cyan", no_wrap=True)
        table.add_column("Title", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("Attempts", justify="right", style="blue")
        table.add_column("Debug", justify="right", style="magenta")
        table.add_column("Time", justify="right", style="green")
        table.add_column("Model", style="dim")

        for tid, tdata in tasks.items():
            status = tdata.get("final_status", "unknown")
            status_color = "green" if status == "completed" else "red"
            title = tdata.get("title", "")
            if len(title) > 40:
                title = title[:37] + "..."
            model = tdata.get("model_used", "")
            if len(model) > 20:
                model = "..." + model[-17:]

            table.add_row(
                tdata.get("spec_id", tid),
                title,
                f"[{status_color}]{status}[/{status_color}]",
                str(tdata.get("total_attempts", 0)),
                str(tdata.get("debug_attempts", 0)),
                _format_duration(tdata.get("wall_clock_seconds", 0)),
                model,
            )

        console.print(table)
        console.print()


def _show_task_history(runs: list[Path], task_spec_id: str, json_output: bool) -> None:
    """Show history for a specific task across all runs."""
    task_entries = []

    for run_path in runs:
        try:
            data = RunTelemetry.load(run_path)
        except Exception:
            continue

        run_id = data.get("run_id", run_path.stem)
        tasks = data.get("tasks", {})
        for tid, tdata in tasks.items():
            if tdata.get("spec_id") == task_spec_id:
                task_entries.append({
                    "run_id": run_id,
                    **tdata,
                })

    if not task_entries:
        if json_output:
            click.echo(json.dumps({"error": f"No telemetry found for task '{task_spec_id}'"}))
        else:
            click.echo(f"✗ No telemetry found for task '{task_spec_id}'")
        return

    if json_output:
        click.echo(json.dumps({"task_id": task_spec_id, "runs": task_entries}, indent=2, default=str))
        return

    console = Console()
    console.print()
    console.print(f"[bold cyan]Task History: {task_spec_id}[/bold cyan]")
    console.print()

    table = Table(show_header=True)
    table.add_column("Run ID", style="cyan")
    table.add_column("Status", style="yellow")
    table.add_column("Attempts", justify="right", style="blue")
    table.add_column("Debug", justify="right", style="magenta")
    table.add_column("Time", justify="right", style="green")
    table.add_column("Errors", justify="right", style="red")

    for entry in task_entries:
        status = entry.get("final_status", "unknown")
        status_color = "green" if status == "completed" else "red"
        run_id = entry.get("run_id", "?")
        if len(run_id) > 30:
            run_id = run_id[:27] + "..."

        table.add_row(
            run_id,
            f"[{status_color}]{status}[/{status_color}]",
            str(entry.get("total_attempts", 0)),
            str(entry.get("debug_attempts", 0)),
            _format_duration(entry.get("wall_clock_seconds", 0)),
            str(len(entry.get("error_messages", []))),
        )

    console.print(table)
    console.print()


@metrics.command()
@click.option("--resolved-only", is_flag=True, help="Only clean up resolved journals")
@click.pass_context
def cleanup(ctx, resolved_only):
    """Clean up debug journal files.
    
    By default, removes ALL debug journals. Use --resolved-only to
    keep journals for tasks still being debugged.
    """
    from bob.orchestrator.debug_journal import DebugJournal
    
    project = _get_active_project(ctx)
    if not project:
        return
    
    journal = DebugJournal(project.workspace_dir)
    
    # Show what we have
    journals = journal.list_journals()
    if not journals:
        click.echo("No debug journals found.")
        return
    
    total_kb = journal.total_size_kb()
    resolved = sum(1 for j in journals if j["resolved"])
    unresolved = len(journals) - resolved
    
    click.echo(f"Debug journals: {len(journals)} files ({total_kb} KB)")
    click.echo(f"  Resolved: {resolved}")
    click.echo(f"  Unresolved: {unresolved}")
    
    if resolved_only:
        cleaned = journal.cleanup_resolved()
        click.echo(f"\nCleaned up {len(cleaned)} resolved journal(s): {', '.join(cleaned) if cleaned else 'none'}")
    else:
        count = journal.cleanup_all()
        click.echo(f"\nRemoved all {count} debug journal(s).")


def _get_active_project(ctx):
    """Get the active project from context."""
    from bob.database.manager import DatabaseManager
    
    db_path = ctx.obj.db_path
    db = DatabaseManager(db_path)
    
    # Try to find active project
    projects = db.list_projects()
    active = [p for p in projects if p.status.value == "active"]
    if not active:
        click.echo("No active project found.", err=True)
        return None
    return active[0]
