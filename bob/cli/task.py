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
from bob.models.base import ModelTier, ProjectStatus, TaskStatus


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


# ============================================================================
# Task Show Command
# ============================================================================


@click.command("show")
@click.argument("task_id")
@click.option(
    "--research",
    is_flag=True,
    help="Show research findings",
)
@click.option(
    "--escalation",
    is_flag=True,
    help="Show escalation state details",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def show(
    ctx: click.Context,
    task_id: str,
    research: bool,
    escalation: bool,
    json_output: bool,
) -> None:
    """Show detailed information about a specific task.

    \b
    Display comprehensive task details including title, description,
    acceptance criteria, implementation steps, dependencies, status,
    and error history.

    \b
    Examples:
      bob task show F001
      bob task show F001 --research
      bob task show F001 --escalation
      bob task show F001 --json
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

    # Get task by spec_id or database ID
    task = None

    # Try as database ID first
    task = db.get_task(task_id)

    # If not found, try as spec_id
    if not task:
        tasks = db.list_tasks(project_id=project_id, limit=1000)
        for t in tasks:
            if t.spec_id == task_id:
                task = t
                break

    if not task:
        if json_output:
            click.echo(json.dumps({"error": f"Task '{task_id}' not found"}))
        else:
            click.echo(f"✗ Task '{task_id}' not found")
        raise click.Abort()

    # Get task sessions for error history
    sessions = db.list_sessions(
        project_id=project_id,
        task_id=task.id,
        limit=100
    )

    # Output in JSON format
    if json_output:
        task_data = {
            "id": task.id,
            "spec_id": task.spec_id,
            "title": task.title,
            "description": task.description,
            "acceptance_criteria": task.acceptance_criteria,
            "steps": task.steps,
            "depends_on": task.depends_on,
            "priority": task.priority,
            "category": task.category,
            "labels": task.labels,
            "status": task.status.value,
            "assigned_agent": task.assigned_agent.value if task.assigned_agent else None,
            "current_model": task.current_model,
            "attempts": task.attempts,
            "escalation_tier": task.escalation_tier.value,
            "failure_type": task.failure_type.value if task.failure_type else None,
            "research_required": task.research_required,
            "research_complete": task.research_complete,
            "research_queries": task.research_queries,
        }

        if research and task.research_findings:
            task_data["research_findings"] = task.research_findings

        if escalation:
            task_data["escalation_details"] = {
                "tier": task.escalation_tier.value,
                "model": task.current_model,
                "attempts": task.attempts,
                "failure_type": task.failure_type.value if task.failure_type else None,
            }

        # Add sessions
        task_data["sessions"] = [
            {
                "id": s.id,
                "agent_type": s.agent_type.value,
                "model": s.model,
                "status": s.status.value,
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "turns": s.turns,
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
                "cost": s.cost,
            }
            for s in sessions
        ]

        click.echo(json.dumps(task_data, indent=2))
        return

    # Display in Rich format
    console = Console()

    # Header
    console.print()
    console.print(f"[bold cyan]{task.spec_id}: {task.title}[/bold cyan]")
    console.print()

    # Status and metadata
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

    priority_color = {
        "critical": "red bold",
        "high": "red",
        "medium": "yellow",
        "low": "dim",
    }.get(task.priority, "white")

    console.print(f"[bold]Status:[/bold] [{status_color}]{task.status.value}[/{status_color}]")
    console.print(f"[bold]Priority:[/bold] [{priority_color}]{task.priority}[/{priority_color}]")
    console.print(f"[bold]Category:[/bold] {task.category}")
    if task.labels:
        console.print(f"[bold]Labels:[/bold] {', '.join(task.labels)}")
    console.print()

    # Description
    console.print("[bold]Description:[/bold]")
    console.print(f"  {task.description}")
    console.print()

    # Acceptance criteria
    if task.acceptance_criteria:
        console.print("[bold]Acceptance Criteria:[/bold]")
        for criterion in task.acceptance_criteria:
            console.print(f"  • {criterion}")
        console.print()

    # Implementation steps
    if task.steps:
        console.print("[bold]Implementation Steps:[/bold]")
        for i, step in enumerate(task.steps, 1):
            console.print(f"  {i}. {step}")
        console.print()

    # Dependencies
    if task.depends_on:
        console.print("[bold]Dependencies:[/bold]")
        console.print(f"  Depends on: {', '.join(task.depends_on)}")
        console.print()

    # Find tasks that depend on this one (blockers)
    all_tasks = db.list_tasks(project_id=project_id, limit=1000)
    blockers = [t for t in all_tasks if task.spec_id in t.depends_on]
    if blockers:
        console.print("[bold]Blocks:[/bold]")
        console.print(f"  Blocks: {', '.join(t.spec_id for t in blockers)}")
        console.print()

    # Progress and attempts
    console.print("[bold]Progress:[/bold]")
    console.print(f"  Attempts: {task.attempts}")
    console.print(f"  Current Model: {task.current_model}")
    if task.assigned_agent:
        console.print(f"  Assigned Agent: {task.assigned_agent.value}")
    console.print()

    # Escalation details
    if escalation or task.escalation_tier != ModelTier.TIER1:
        console.print("[bold]Escalation State:[/bold]")
        console.print(f"  Tier: {task.escalation_tier.value}")
        if task.failure_type:
            console.print(f"  Failure Type: {task.failure_type.value}")
        console.print()

    # Research details
    if task.research_required:
        console.print("[bold]Research:[/bold]")
        console.print(f"  Required: Yes")
        console.print(f"  Complete: {'Yes' if task.research_complete else 'No'}")

        if task.research_queries:
            console.print(f"  Queries:")
            for query in task.research_queries:
                console.print(f"    • {query}")

        if research and task.research_findings:
            console.print(f"  Findings:")
            for key, value in task.research_findings.items():
                console.print(f"    • {key}: {value}")
        console.print()

    # Session history
    if sessions:
        console.print("[bold]Session History:[/bold]")

        # Create sessions table
        sessions_table = Table(show_header=True)
        sessions_table.add_column("Agent", style="cyan")
        sessions_table.add_column("Model", style="green")
        sessions_table.add_column("Status", style="yellow")
        sessions_table.add_column("Turns", justify="right")
        sessions_table.add_column("Tokens", justify="right")
        sessions_table.add_column("Cost", justify="right")

        for session in sessions[-10:]:  # Show last 10 sessions
            session_status_color = {
                "completed": "green",
                "failed": "red",
                "running": "blue",
                "cancelled": "yellow",
            }.get(session.status.value, "white")

            total_tokens = session.input_tokens + session.output_tokens

            sessions_table.add_row(
                session.agent_type.value,
                session.model.split("/")[-1] if "/" in session.model else session.model,
                f"[{session_status_color}]{session.status.value}[/{session_status_color}]",
                str(session.turns),
                f"{total_tokens:,}",
                f"${session.cost:.4f}",
            )

        console.print(sessions_table)
        console.print()

        if len(sessions) > 10:
            console.print(f"[dim]Showing last 10 of {len(sessions)} sessions[/dim]")
            console.print()


# ============================================================================
# Task Retry Command
# ============================================================================


@click.command("retry")
@click.argument("spec_id")
@click.option(
    "--reset-escalation",
    is_flag=True,
    help="Reset escalation tier to TIER1",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def retry(
    ctx: click.Context,
    spec_id: str,
    reset_escalation: bool,
    json_output: bool,
) -> None:
    """Retry a failed or completed task.

    \b
    Reset task status to PENDING and clear error state.
    Preserves error history for debugging.

    \b
    Examples:
      bob task retry F001
      bob task retry F042 --reset-escalation
      bob task retry F015 --json
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
        projects = db.list_projects(status=ProjectStatus.ACTIVE, limit=1)
        if not projects:
            if json_output:
                click.echo(json.dumps({
                    "error": "No active project found",
                    "message": "Use --project to specify a project or 'bob project use' to set an active project"
                }))
            else:
                click.echo("Error: No active project found", err=True)
                click.echo("Use --project to specify a project or 'bob project use' to set an active project", err=True)
            ctx.exit(1)
        project_id = projects[0].id

    # Find task by spec_id
    all_tasks = db.list_tasks(project_id=project_id, limit=1000)
    task = None
    for t in all_tasks:
        if t.spec_id == spec_id:
            task = t
            break

    if not task:
        if json_output:
            click.echo(json.dumps({
                "error": "Task not found",
                "spec_id": spec_id,
                "project_id": project_id,
            }))
        else:
            click.echo(f"Error: Task '{spec_id}' not found in project", err=True)
        ctx.exit(1)

    # Validate task can be retried
    # Note: We allow retrying any task (pending, failed, completed, etc.)
    # This provides flexibility for users

    # Update task in database
    # Note: Cannot clear failure_type (None means "don't update")
    update_kwargs = {
        "task_id": task.id,
        "status": TaskStatus.PENDING,
    }
    if reset_escalation:
        update_kwargs["escalation_tier"] = ModelTier.TIER1

    db.update_task(**update_kwargs)

    # Get updated task for display
    task = db.get_task(task.id)

    # Output result
    if json_output:
        click.echo(json.dumps({
            "status": "success",
            "message": "Task reset to pending",
            "task": {
                "id": task.id,
                "spec_id": task.spec_id,
                "title": task.title,
                "status": task.status.value,
                "attempts": task.attempts,
                "escalation_tier": task.escalation_tier.value,
            },
            "reset_escalation": reset_escalation,
        }, indent=2))
    else:
        console = Console()
        console.print(f"✓ Task [cyan]{spec_id}[/cyan] reset to [green]PENDING[/green]")
        console.print(f"  Title: {task.title}")
        console.print(f"  Attempts: {task.attempts}")
        console.print(f"  Escalation: {task.escalation_tier.value}")
        if reset_escalation:
            console.print(f"  [yellow]Escalation tier reset to TIER1[/yellow]")
        console.print()
        console.print("Run 'bob run' to execute the task")


# ============================================================================
# Task Skip Command
# ============================================================================


@click.command("skip")
@click.argument("spec_id")
@click.option(
    "--reason",
    "-r",
    required=True,
    help="Reason for skipping this task",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def skip(
    ctx: click.Context,
    spec_id: str,
    reason: str,
    json_output: bool,
) -> None:
    """Skip a task with a reason.

    \b
    Mark a task as skipped and record the reason. Skipped tasks will not be
    executed during 'bob run' but remain in the task list for reference.

    \b
    Examples:
      bob task skip F001 --reason "Waiting for external dependency"
      bob task skip F042 -r "Feature postponed to v2.0"
      bob task skip F015 --reason "Blocked by infrastructure setup" --json
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
        projects = db.list_projects(status=ProjectStatus.ACTIVE, limit=1)
        if not projects:
            if json_output:
                click.echo(json.dumps({
                    "error": "No active project found",
                    "message": "Use --project to specify a project or 'bob project use' to set an active project"
                }))
            else:
                click.echo("Error: No active project found", err=True)
                click.echo("Use --project to specify a project or 'bob project use' to set an active project", err=True)
            ctx.exit(1)
        project_id = projects[0].id

    # Find task by spec_id
    all_tasks = db.list_tasks(project_id=project_id, limit=1000)
    task = None
    for t in all_tasks:
        if t.spec_id == spec_id:
            task = t
            break

    if not task:
        if json_output:
            click.echo(json.dumps({
                "error": "Task not found",
                "spec_id": spec_id,
                "project_id": project_id,
            }))
        else:
            click.echo(f"Error: Task '{spec_id}' not found in project", err=True)
        ctx.exit(1)

    # Validate task can be skipped
    # Allow skipping tasks in any status except deprecated
    if task.status == TaskStatus.DEPRECATED:
        if json_output:
            click.echo(json.dumps({
                "error": "Cannot skip deprecated task",
                "spec_id": spec_id,
                "status": task.status.value,
            }))
        else:
            click.echo(f"Error: Cannot skip deprecated task '{spec_id}'", err=True)
        ctx.exit(1)

    # Update task in database
    db.update_task(
        task_id=task.id,
        status=TaskStatus.SKIPPED,
        skip_reason=reason,
    )

    # Get updated task for display
    task = db.get_task(task.id)

    # Output result
    if json_output:
        click.echo(json.dumps({
            "status": "success",
            "message": "Task skipped",
            "task": {
                "id": task.id,
                "spec_id": task.spec_id,
                "title": task.title,
                "status": task.status.value,
                "skip_reason": task.skip_reason,
            },
        }, indent=2))
    else:
        console = Console()
        console.print(f"✓ Task [cyan]{spec_id}[/cyan] marked as [yellow]SKIPPED[/yellow]")
        console.print(f"  Title: {task.title}")
        console.print(f"  Reason: {task.skip_reason}")
        console.print()
        console.print("This task will not be executed during 'bob run'")
        console.print("To unskip, use: bob task retry " + spec_id)
