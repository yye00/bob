"""Task management commands for BOB framework.

This module provides commands for viewing and managing tasks,
including listing, filtering, and displaying task details.
"""

import json
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from bob.database.manager import DatabaseManager
from bob.models.base import ProjectStatus, TaskStatus


# ============================================================================
# Task List Command
# ============================================================================


@click.command("list")
@click.option(
    "--status",
    type=click.Choice([s.value for s in TaskStatus], case_sensitive=False),
    help="Filter by task status",
)
@click.option(
    "--priority",
    type=click.Choice(["critical", "high", "medium", "low"], case_sensitive=False),
    help="Filter by priority level",
)
@click.option(
    "--category",
    type=click.Choice(["functional", "test", "infra", "docs"], case_sensitive=False),
    help="Filter by task category",
)
@click.option(
    "--needs-research",
    is_flag=True,
    help="Show only tasks that require research",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.option(
    "--limit",
    type=int,
    default=100,
    help="Maximum number of tasks to display (default: 100)",
)
@click.pass_context
def list(
    ctx: click.Context,
    status: Optional[str],
    priority: Optional[str],
    category: Optional[str],
    needs_research: bool,
    json_output: bool,
    limit: int,
) -> None:
    """List tasks with optional filters.

    \b
    Display tasks with filtering options. Shows task ID, title, status,
    priority, attempts, and assigned model.

    \b
    Examples:
      bob task list
      bob task list --status pending
      bob task list --priority critical
      bob task list --category functional
      bob task list --needs-research
      bob task list --status pending --priority high
      bob task list --json
    """
    # Get global context
    global_ctx = ctx.obj

    # Override with global JSON flag if set
    if global_ctx.json_output:
        json_output = True

    # Get database manager
    db = DatabaseManager(global_ctx.db_path)

    # Determine project ID
    project_id = global_ctx.project_id
    if not project_id:
        # Try to get active project
        # TODO: Implement get_active_project() in DatabaseManager
        # For now, get the first active project
        projects = db.list_projects(status=ProjectStatus.ACTIVE, limit=1)
        if not projects:
            if json_output:
                click.echo(json.dumps({"error": "No active project found"}))
            else:
                click.echo("✗ No active project found")
                click.echo()
                click.echo("Please specify a project with --project or create one:")
                click.echo("  bob project create <name> <workspace> <spec-source>")
            raise click.Abort()
        project_id = projects[0].id

    # Convert status string to TaskStatus enum
    task_status = TaskStatus(status) if status else None

    # Query tasks from database
    tasks = db.list_tasks(
        project_id=project_id,
        status=task_status,
        priority=priority,
        limit=limit,
    )

    # Apply additional filters (category, needs_research)
    if category:
        tasks = [t for t in tasks if t.category == category]
    if needs_research:
        tasks = [t for t in tasks if t.research_required and not t.research_complete]

    # Output in JSON format
    if json_output:
        tasks_data = [
            {
                "id": t.id,
                "spec_id": t.spec_id,
                "title": t.title,
                "description": t.description,
                "status": t.status.value,
                "priority": t.priority,
                "category": t.category,
                "attempts": t.attempts,
                "assigned_agent": t.assigned_agent.value if t.assigned_agent else None,
                "current_model": t.current_model,
                "depends_on": t.depends_on,
                "research_required": t.research_required,
                "research_complete": t.research_complete,
            }
            for t in tasks
        ]
        result = {
            "project_id": project_id,
            "count": len(tasks),
            "tasks": tasks_data,
        }
        click.echo(json.dumps(result, indent=2))
        return

    # Display in table format using Rich
    console = Console()

    if not tasks:
        console.print("[yellow]No tasks found matching the filters[/yellow]")
        console.print()
        console.print("Try:")
        console.print("  • Removing filters to see all tasks")
        console.print("  • Creating tasks with: bob sync")
        return

    # Create Rich table
    table = Table(title=f"Tasks for Project: {project_id}", show_header=True)
    table.add_column("Spec ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Priority", style="magenta", no_wrap=True)
    table.add_column("Attempts", justify="right", style="blue", no_wrap=True)
    table.add_column("Model", style="green", no_wrap=True)

    # Add rows
    for task in tasks:
        # Color status based on value
        status_color = {
            TaskStatus.PENDING.value: "yellow",
            TaskStatus.IN_PROGRESS.value: "blue",
            TaskStatus.COMPLETED.value: "green",
            TaskStatus.FAILED.value: "red",
            TaskStatus.BLOCKED.value: "red",
            TaskStatus.RESEARCH_NEEDED.value: "cyan",
            TaskStatus.RESEARCH_COMPLETE.value: "cyan",
            TaskStatus.SKIPPED.value: "dim",
            TaskStatus.DEPRECATED.value: "dim",
        }.get(task.status.value, "white")

        # Color priority
        priority_color = {
            "critical": "red bold",
            "high": "red",
            "medium": "yellow",
            "low": "dim",
        }.get(task.priority, "white")

        # Truncate title if too long
        title = task.title
        if len(title) > 50:
            title = title[:47] + "..."

        # Truncate model name (show last part)
        model_display = task.current_model
        if len(model_display) > 20:
            # Show last 20 chars (usually the version)
            model_display = "..." + model_display[-17:]

        table.add_row(
            task.spec_id,
            title,
            f"[{status_color}]{task.status.value}[/{status_color}]",
            f"[{priority_color}]{task.priority}[/{priority_color}]",
            str(task.attempts),
            model_display,
        )

    console.print(table)
    console.print()
    console.print(f"Total tasks: {len(tasks)}")

    # Show summary statistics
    status_counts = {}
    for task in tasks:
        status_counts[task.status.value] = status_counts.get(task.status.value, 0) + 1

    if status_counts:
        console.print()
        console.print("Status summary:")
        for status_name, count in sorted(status_counts.items()):
            console.print(f"  • {status_name}: {count}")
