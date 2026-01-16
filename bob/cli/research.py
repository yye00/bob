"""Research command for BOB framework.

This module provides the 'bob research' command for executing research
on tasks that require it.
"""

import json
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel

from bob.database.manager import DatabaseManager
from bob.models.base import ProjectStatus, Task
from bob.orchestrator.research_controller import ResearchController


@click.command("research")
@click.argument("task_id")
@click.option(
    "--type",
    "research_type",
    type=click.Choice(["quick", "deep", "experimental"], case_sensitive=False),
    default="quick",
    help="Type of research to perform (default: quick)",
)
@click.option(
    "--max-queries",
    type=int,
    default=3,
    help="Maximum number of research queries to execute (default: 3)",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def research(
    ctx: click.Context,
    task_id: str,
    research_type: str,
    max_queries: int,
    json_output: bool,
) -> None:
    """Execute research for a task that requires it.

    \b
    Run research queries for tasks marked with research_required=True.
    The research findings are stored in the task and can be used to
    guide implementation.

    \b
    Examples:
      bob research F001
      bob research F001 --type deep
      bob research F001 --max-queries 5
      bob research F001 --json
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

    # Get project
    project = db.get_project(project_id)
    if not project:
        if json_output:
            click.echo(json.dumps({"error": f"Project '{project_id}' not found"}))
        else:
            click.echo(f"✗ Project '{project_id}' not found")
        raise click.Abort()

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

    # Check if task needs research
    if not task.research_required:
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "error": f"Task '{task.spec_id}' does not require research",
                        "task_id": task.spec_id,
                        "research_required": False,
                    }
                )
            )
        else:
            click.echo(f"✗ Task '{task.spec_id}' does not require research")
            click.echo()
            click.echo("Only tasks with research_required=True can be researched.")
        raise click.Abort()

    # Check if research already complete
    if task.research_complete:
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "error": f"Research already complete for task '{task.spec_id}'",
                        "task_id": task.spec_id,
                        "research_complete": True,
                        "research_findings": task.research_findings,
                    }
                )
            )
        else:
            click.echo(f"✗ Research already complete for task '{task.spec_id}'")
            click.echo()
            click.echo("Use 'bob task show --research' to view findings.")
        raise click.Abort()

    # Check if task has research queries
    if not task.research_queries:
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "error": f"No research queries defined for task '{task.spec_id}'",
                        "task_id": task.spec_id,
                    }
                )
            )
        else:
            click.echo(f"✗ No research queries defined for task '{task.spec_id}'")
            click.echo()
            click.echo("Task must have research_queries to execute research.")
        raise click.Abort()

    # Display research info
    console = Console()

    if not json_output:
        console.print()
        console.print(f"[bold cyan]Executing research for {task.spec_id}: {task.title}[/bold cyan]")
        console.print()
        console.print(f"[bold]Research Type:[/bold] {research_type}")
        console.print(f"[bold]Max Queries:[/bold] {max_queries}")
        console.print(f"[bold]Queries to Execute:[/bold] {len(task.research_queries)}")
        console.print()

        # Show queries
        for i, query in enumerate(task.research_queries[:max_queries], 1):
            console.print(f"  {i}. {query}")
        console.print()

    # Initialize research controller
    research_controller = ResearchController(
        db_manager=db,
        workspace_dir=project.workspace_dir,
        perplexity_available=True,  # Will check for API key internally
    )

    # Execute research
    try:
        success = research_controller.run_research(
            task=task,
            research_type=research_type,
            max_queries=max_queries,
        )

        if not success:
            if json_output:
                click.echo(
                    json.dumps(
                        {
                            "error": "Research execution failed",
                            "task_id": task.spec_id,
                        }
                    )
                )
            else:
                console.print("[red]✗ Research execution failed[/red]")
            raise click.Abort()

        # Get updated task from database
        updated_task = db.get_task(task.id)
        if not updated_task:
            raise Exception("Failed to retrieve updated task")

        # Output results
        if json_output:
            result = {
                "success": True,
                "task_id": updated_task.spec_id,
                "research_complete": updated_task.research_complete,
                "research_findings": updated_task.research_findings,
                "queries_executed": len(task.research_queries[:max_queries]),
            }
            click.echo(json.dumps(result, indent=2))
        else:
            console.print("[green]✓ Research completed successfully[/green]")
            console.print()

            # Display findings
            if updated_task.research_findings:
                console.print("[bold]Research Findings:[/bold]")
                console.print()

                for query, finding in updated_task.research_findings.items():
                    # Convert finding to string if it's a dict or other object
                    if isinstance(finding, dict):
                        finding_text = json.dumps(finding, indent=2)
                    else:
                        finding_text = str(finding)

                    panel = Panel(
                        finding_text,
                        title=f"[cyan]{query}[/cyan]",
                        border_style="blue",
                    )
                    console.print(panel)
                    console.print()

            # Next steps
            console.print("[bold]Next Steps:[/bold]")
            console.print("  • View full task details: bob task show", updated_task.spec_id)
            console.print("  • Start implementation: bob run --task", updated_task.spec_id)
            console.print()

    except Exception as e:
        if json_output:
            click.echo(json.dumps({"error": str(e), "task_id": task.spec_id}))
        else:
            console.print(f"[red]✗ Error: {e}[/red]")
        raise click.Abort()
