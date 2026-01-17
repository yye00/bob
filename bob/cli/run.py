"""Run commands for BOB framework.

This module provides commands for running the autonomous coding agent,
including sequential and parallel task execution.
"""

import json
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from pathlib import Path

from bob.database.manager import DatabaseManager
from bob.models.base import ProjectStatus, TaskStatus
from bob.orchestrator.task_queue import TaskQueue
from bob.orchestrator.engine import create_orchestrator


# ============================================================================
# Run Command (Main)
# ============================================================================


@click.command("run")
@click.option(
    "--task",
    "task_id",
    help="Specific task ID to run (default: auto-select from queue)",
)
@click.option(
    "--parallel",
    type=int,
    metavar="N",
    help="Run N tasks in parallel (uses concurrent execution)",
)
@click.option(
    "--max-turns",
    type=int,
    default=100,
    help="Maximum turns per agent session (default: 100)",
)
@click.option(
    "--max-sessions",
    type=int,
    default=1,
    help="Maximum number of sessions to run (default: 1, use 0 for unlimited)",
)
@click.option(
    "--agent",
    type=click.Choice(["coding", "initializer", "sync", "escalation"], case_sensitive=False),
    default="coding",
    help="Agent type to use (default: coding)",
)
@click.option(
    "--model",
    type=click.Choice(["sonnet", "opus", "haiku"], case_sensitive=False),
    help="Override model selection",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be executed without actually running",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def run(
    ctx: click.Context,
    task_id: Optional[str],
    parallel: Optional[int],
    max_turns: int,
    max_sessions: int,
    agent: str,
    model: Optional[str],
    dry_run: bool,
    json_output: bool,
) -> None:
    """Run the autonomous coding agent.

    \b
    Start an agent session to work on tasks. By default, the agent will
    automatically select the highest-priority ready task. Use --task to
    run a specific task, or --parallel to run multiple tasks concurrently.

    \b
    Examples:
      bob run                          # Run on next ready task
      bob run --task F001              # Run specific task
      bob run --parallel 3             # Run 3 tasks in parallel
      bob run --max-turns 50           # Limit turns per session
      bob run --agent coding           # Use specific agent type
      bob run --model opus             # Override model selection
      bob run --json                   # JSON output for scripting
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
                ctx.exit(1)
            else:
                click.echo("✗ No active project found")
                click.echo()
                click.echo("Please specify a project with --project or create one:")
                click.echo("  bob project create <name> <workspace> <spec-source>")
                ctx.exit(1)
        project_id = projects[0].id

    # Get project details
    project = db.get_project(project_id)
    if not project:
        if json_output:
            click.echo(json.dumps({"error": f"Project {project_id} not found"}))
            ctx.exit(1)
        else:
            click.echo(f"✗ Project {project_id} not found")
            ctx.exit(1)

    # Create task queue
    queue = TaskQueue(db, project_id=project_id)

    # Handle parallel execution
    if parallel:
        _run_parallel(
            queue=queue,
            db=db,
            project_id=project_id,
            max_workers=parallel,
            max_turns=max_turns,
            agent=agent,
            model=model,
            json_output=json_output,
        )
        return

    # Handle single task execution
    if task_id:
        _run_single_task(
            db=db,
            project=project,
            queue=queue,
            task_id=task_id,
            max_turns=max_turns,
            max_sessions=max_sessions,
            model=model,
            dry_run=dry_run,
            json_output=json_output,
            ctx=ctx,
        )
    else:
        # Auto-select and run next task
        _run_auto_select(
            db=db,
            project=project,
            queue=queue,
            max_turns=max_turns,
            max_sessions=max_sessions,
            model=model,
            dry_run=dry_run,
            json_output=json_output,
            ctx=ctx,
        )


def _run_parallel(
    queue: TaskQueue,
    db: DatabaseManager,
    project_id: str,
    max_workers: int,
    max_turns: int,
    agent: str,
    model: Optional[str],
    json_output: bool,
) -> None:
    """Run multiple tasks in parallel.

    Args:
        queue: TaskQueue instance
        db: DatabaseManager instance
        project_id: Project ID
        max_workers: Maximum number of concurrent workers
        max_turns: Maximum turns per session
        agent: Agent type to use
        model: Optional model override
        json_output: Whether to output in JSON format
    """
    # Get ready tasks
    ready_tasks = queue.get_ready_tasks(limit=max_workers)

    if not ready_tasks:
        if json_output:
            click.echo(json.dumps({
                "status": "no_tasks",
                "message": "No tasks ready to execute",
            }))
        else:
            click.echo("✗ No tasks ready to execute")
            click.echo()
            click.echo("All tasks may be blocked by dependencies or already completed.")
            click.echo("Run 'bob task list --status pending' to see pending tasks.")
        return

    # Limit to max_workers
    tasks_to_run = ready_tasks[:max_workers]

    if not json_output:
        console = Console()
        console.print()
        console.print(f"🚀 Running {len(tasks_to_run)} tasks in parallel (max workers: {max_workers})")
        console.print()

        # Display tasks table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Task ID", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Priority", style="yellow")

        for task in tasks_to_run:
            # Truncate title if too long
            title = task.title if len(task.title) <= 50 else task.title[:47] + "..."
            table.add_row(task.spec_id, title, task.priority)

        console.print(table)
        console.print()

    # Execute tasks in parallel using TaskQueue.run_parallel()
    # For now, use mock executor (actual agent execution will be implemented later)
    results = queue.run_parallel(tasks_to_run, max_workers=max_workers)

    # Display results
    if json_output:
        click.echo(json.dumps({
            "status": "completed",
            "tasks_run": len(tasks_to_run),
            "max_workers": max_workers,
            "results": results,
        }, indent=2))
    else:
        console = Console()
        console.print()
        console.print("✓ Parallel execution completed")
        console.print()

        # Results table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Task ID", style="cyan")
        table.add_column("Session ID", style="yellow")
        table.add_column("Status", style="white")

        for result in results:
            status_display = "✓ Success" if result["status"] == "success" else f"✗ {result['status']}"
            status_style = "green" if result["status"] == "success" else "red"

            table.add_row(
                result["spec_id"],
                result.get("session_id", "N/A"),
                f"[{status_style}]{status_display}[/{status_style}]",
            )

        console.print(table)
        console.print()

        # Summary
        successful = sum(1 for r in results if r["status"] == "success")
        failed = len(results) - successful

        if failed > 0:
            console.print(f"Summary: {successful} succeeded, {failed} failed")
        else:
            console.print(f"Summary: All {successful} tasks completed successfully")

        console.print()


def _run_single_task(
    db: DatabaseManager,
    project,
    queue: TaskQueue,
    task_id: str,
    max_turns: int,
    max_sessions: int,
    model: Optional[str],
    dry_run: bool,
    json_output: bool,
    ctx: click.Context,
) -> None:
    """Run a single specific task.

    Args:
        db: DatabaseManager instance
        project: Project object
        queue: TaskQueue instance
        task_id: Task ID to run
        max_turns: Maximum turns per session
        max_sessions: Maximum number of sessions
        model: Optional model override
        dry_run: Whether to do a dry run
        json_output: Whether to output in JSON format
        ctx: Click context
    """
    # Get the task
    task = db.get_task_by_spec_id(project.id, task_id)
    if not task:
        if json_output:
            click.echo(json.dumps({"error": f"Task {task_id} not found"}))
            ctx.exit(1)
        else:
            click.echo(f"✗ Task {task_id} not found in project {project.name}")
            ctx.exit(1)

    if dry_run:
        if json_output:
            click.echo(json.dumps({
                "mode": "dry_run",
                "task": {
                    "id": task.spec_id,
                    "title": task.title,
                    "status": task.status.value,
                    "priority": task.priority,
                }
            }, indent=2))
        else:
            console = Console()
            console.print()
            console.print(f"[bold cyan]Dry run mode - would execute:[/bold cyan]")
            console.print()
            console.print(f"  Task ID: {task.spec_id}")
            console.print(f"  Title: {task.title}")
            console.print(f"  Status: {task.status.value}")
            console.print(f"  Priority: {task.priority}")
            console.print()
        return

    # Check if task is ready
    if task.status != TaskStatus.PENDING:
        if json_output:
            click.echo(json.dumps({
                "error": f"Task {task_id} is not in PENDING status (current: {task.status.value})"
            }))
            ctx.exit(1)
        else:
            click.echo(f"✗ Task {task_id} is not in PENDING status (current: {task.status.value})")
            ctx.exit(1)

    # Check dependencies
    ready_tasks = queue.get_ready_tasks(limit=100)
    if task not in ready_tasks:
        if json_output:
            click.echo(json.dumps({
                "error": f"Task {task_id} has unmet dependencies"
            }))
            ctx.exit(1)
        else:
            click.echo(f"✗ Task {task_id} has unmet dependencies")
            click.echo()
            click.echo("Dependencies that must be completed first:")
            for dep_id in task.depends_on:
                dep_task = db.get_task_by_spec_id(project.id, dep_id)
                if dep_task and dep_task.status != TaskStatus.COMPLETED:
                    click.echo(f"  - {dep_id}: {dep_task.status.value}")
            ctx.exit(1)

    # Run the task
    if not json_output:
        console = Console()
        console.print()
        console.print(f"🚀 Running task {task.spec_id}: {task.title}")
        console.print()

    # Create orchestrator
    from bob.orchestrator.engine import OrchestratorConfig

    project_dir = Path(project.workspace_dir)
    config = OrchestratorConfig(
        default_model=model or "claude-sonnet-4-20250514",
    )
    orchestrator = create_orchestrator(
        db_manager=db,
        project_id=project.id,
        project_dir=project_dir,
        config=config,
    )

    # Execute task - this is a placeholder, real execution will use agent SDK
    # For now, just mark as completed for testing
    if json_output:
        click.echo(json.dumps({
            "status": "completed",
            "task_id": task.spec_id,
            "title": task.title,
            "message": "Task execution with orchestrator (placeholder)"
        }, indent=2))
    else:
        console.print("[yellow]Note: Full orchestrator execution not yet implemented[/yellow]")
        console.print("[yellow]This is a placeholder that will integrate with Claude SDK[/yellow]")
        console.print()
        console.print("✓ Task execution initiated")
        console.print()


def _run_auto_select(
    db: DatabaseManager,
    project,
    queue: TaskQueue,
    max_turns: int,
    max_sessions: int,
    model: Optional[str],
    dry_run: bool,
    json_output: bool,
    ctx: click.Context,
) -> None:
    """Auto-select and run the next ready task.

    Args:
        db: DatabaseManager instance
        project: Project object
        queue: TaskQueue instance
        max_turns: Maximum turns per session
        max_sessions: Maximum number of sessions
        model: Optional model override
        dry_run: Whether to do a dry run
        json_output: Whether to output in JSON format
        ctx: Click context
    """
    # Get next ready task
    next_task = queue.get_next_task()

    if not next_task:
        if json_output:
            click.echo(json.dumps({
                "status": "no_tasks",
                "message": "No tasks ready to execute"
            }))
        else:
            click.echo("✗ No tasks ready to execute")
            click.echo()
            click.echo("All tasks may be blocked by dependencies or already completed.")
            click.echo("Run 'bob task list --status pending' to see pending tasks.")
        return

    # Run with single task path
    _run_single_task(
        db=db,
        project=project,
        queue=queue,
        task_id=next_task.spec_id,
        max_turns=max_turns,
        max_sessions=max_sessions,
        model=model,
        dry_run=dry_run,
        json_output=json_output,
        ctx=ctx,
    )
