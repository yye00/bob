"""Global status command implementation (F038)"""
import json as json_lib
from typing import Optional, Dict, Any, List
import click
from datetime import datetime, timedelta

from bob.database.manager import DatabaseManager
from bob.models import Project
from bob.observability.cost_tracker import CostTracker


def format_cost(amount: float) -> str:
    """Format cost amount with color coding."""
    if amount == 0:
        return click.style("$0.00", fg="green")
    elif amount < 1.0:
        return click.style(f"${amount:.2f}", fg="green")
    elif amount < 10.0:
        return click.style(f"${amount:.2f}", fg="yellow")
    else:
        return click.style(f"${amount:.2f}", fg="red")


def format_percentage(value: int, total: int) -> str:
    """Format percentage with color coding."""
    if total == 0:
        pct = 0
    else:
        pct = (value / total) * 100

    color = "green" if pct >= 80 else "yellow" if pct >= 50 else "red"
    return click.style(f"{pct:.1f}%", fg=color)


def get_project_summary(db: DatabaseManager, project: Project) -> Dict[str, Any]:
    """Get summary statistics for a project."""
    # Get task counts
    tasks = db.list_tasks(project_id=project.id)
    task_counts = {
        'total': len(tasks),
        'pending': sum(1 for t in tasks if t.status.value == 'pending'),
        'in_progress': sum(1 for t in tasks if t.status.value == 'in_progress'),
        'completed': sum(1 for t in tasks if t.status.value == 'completed'),
        'failed': sum(1 for t in tasks if t.status.value == 'failed'),
        'blocked': sum(1 for t in tasks if t.status.value == 'blocked'),
    }

    # Get session counts
    sessions = db.list_sessions(project_id=project.id)
    active_sessions = [s for s in sessions if s.status.value == 'running']

    # Get costs
    cost_tracker = CostTracker(db)
    costs = cost_tracker.get_project_costs(project.id)

    return {
        'project': project,
        'task_counts': task_counts,
        'active_sessions': len(active_sessions),
        'total_sessions': len(sessions),
        'costs': costs,
    }


def display_text_status(
    summaries: List[Dict[str, Any]],
    total_costs: Any,
    show_details: bool = False
) -> None:
    """Display status in text format."""
    click.echo()
    click.echo(click.style("═" * 80, fg="cyan"))
    click.echo(click.style("  BOB STATUS OVERVIEW", fg="cyan", bold=True))
    click.echo(click.style("═" * 80, fg="cyan"))
    click.echo()

    if not summaries:
        click.echo("  No projects found.")
        click.echo()
        return

    # Overall statistics
    total_projects = len(summaries)
    active_projects = sum(1 for s in summaries if s['active_sessions'] > 0)
    total_tasks = sum(s['task_counts']['total'] for s in summaries)
    completed_tasks = sum(s['task_counts']['completed'] for s in summaries)

    click.echo(click.style("  OVERVIEW", fg="cyan", bold=True))
    click.echo(f"    Projects:        {total_projects} total, {active_projects} active")
    click.echo(f"    Tasks:           {completed_tasks}/{total_tasks} completed " +
               f"({format_percentage(completed_tasks, total_tasks)})")
    total_cost_value = total_costs.total_cost if hasattr(total_costs, 'total_cost') else 0
    click.echo(f"    Total Cost:      {format_cost(total_cost_value)}")
    click.echo()

    # Per-project status
    click.echo(click.style("  PROJECTS", fg="cyan", bold=True))
    click.echo()

    for summary in summaries:
        project = summary['project']
        task_counts = summary['task_counts']
        costs = summary['costs']

        # Project header
        project_name = click.style(project.name, fg="white", bold=True)
        if summary['active_sessions'] > 0:
            status_badge = click.style(" [ACTIVE] ", fg="green", bg="black")
        else:
            status_badge = ""

        click.echo(f"  {project_name} {status_badge}")
        click.echo(f"    ID: {click.style(project.id, fg='cyan')}")

        if project.description:
            desc = project.description[:60] + "..." if len(project.description) > 60 else project.description
            click.echo(f"    Description: {desc}")

        # Task breakdown
        completed = task_counts['completed']
        total = task_counts['total']
        pct_complete = format_percentage(completed, total)

        click.echo(f"    Tasks: {completed}/{total} completed ({pct_complete})")

        if show_details or summary['active_sessions'] > 0:
            if task_counts['pending'] > 0:
                click.echo(f"      - Pending:     {task_counts['pending']}")
            if task_counts['in_progress'] > 0:
                click.echo(f"      - In Progress: {task_counts['in_progress']}")
            if task_counts['failed'] > 0:
                click.echo(f"      - Failed:      {click.style(str(task_counts['failed']), fg='red')}")
            if task_counts['blocked'] > 0:
                click.echo(f"      - Blocked:     {click.style(str(task_counts['blocked']), fg='yellow')}")

        # Sessions
        if summary['active_sessions'] > 0:
            click.echo(f"    Sessions: {summary['active_sessions']} active, " +
                      f"{summary['total_sessions']} total")

        # Costs
        project_cost = costs.total_cost if costs else 0
        click.echo(f"    Cost: {format_cost(project_cost)}")

        click.echo()

    # Cost breakdown
    total_cost_val = total_costs.total_cost if hasattr(total_costs, 'total_cost') else 0
    if show_details and total_cost_val > 0:
        click.echo(click.style("  COST BREAKDOWN", fg="cyan", bold=True))
        click.echo(f"    Total:           {format_cost(total_cost_val)}")

        if hasattr(total_costs, 'by_model') and total_costs.by_model:
            click.echo("    By Model:")
            for model, cost in total_costs.by_model.items():
                click.echo(f"      - {model:30s} {format_cost(cost)}")

        click.echo()

    click.echo(click.style("═" * 80, fg="cyan"))
    click.echo()


def display_json_status(summaries: List[Dict[str, Any]], total_costs: Any) -> None:
    """Display status in JSON format."""
    projects = []
    for summary in summaries:
        project = summary['project']
        costs = summary['costs']

        # Convert ProjectCostSummary to dict if needed
        costs_dict = {
            'total': costs.total_cost if costs else 0,
            'by_model': costs.by_model if costs else {},
            'by_agent': costs.by_agent if costs else {},
        } if costs else {'total': 0}

        projects.append({
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'workspace': project.workspace_dir,
            'task_counts': summary['task_counts'],
            'active_sessions': summary['active_sessions'],
            'total_sessions': summary['total_sessions'],
            'costs': costs_dict,
        })

    # Convert total_costs to dict if it's a ProjectCostSummary
    if hasattr(total_costs, 'total_cost'):
        total_costs_dict = {
            'total': total_costs.total_cost,
            'by_model': total_costs.by_model,
            'by_agent': total_costs.by_agent,
        }
    else:
        total_costs_dict = {'total': 0}

    output = {
        'projects': projects,
        'summary': {
            'total_projects': len(summaries),
            'active_projects': sum(1 for s in summaries if s['active_sessions'] > 0),
            'total_tasks': sum(s['task_counts']['total'] for s in summaries),
            'completed_tasks': sum(s['task_counts']['completed'] for s in summaries),
        },
        'total_costs': total_costs_dict,
        'timestamp': datetime.now().isoformat(),
    }

    click.echo(json_lib.dumps(output, indent=2))


@click.command()
@click.option('--project', '-p', 'project_name', help='Show status for specific project')
@click.option('--json', 'json_output', is_flag=True, help='Output in JSON format')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed status')
@click.pass_context
def status(
    ctx: click.Context,
    project_name: Optional[str],
    json_output: bool,
    verbose: bool
) -> None:
    """View global status across all projects.

    \b
    Show current status of projects, tasks, and recent sessions.
    Provides overview of progress and costs.

    \b
    Examples:
        bob status                    # Overall status
        bob status --project my-app   # Specific project
        bob status --verbose          # Detailed status
        bob status --json             # JSON output
    """
    # Get database path from context
    db_path = ctx.obj.db_path

    # Initialize database manager
    db = DatabaseManager(db_path)

    # Get projects to show
    if project_name:
        # Find specific project
        project = None
        if project_name.startswith("proj-"):
            project = db.get_project(project_name)

        if not project:
            projects = db.list_projects()
            matching_projects = [p for p in projects if p.name == project_name]
            if matching_projects:
                project = matching_projects[0]

        if not project:
            click.echo(f"✗ Project not found: {project_name}", err=True)
            ctx.exit(1)

        projects = [project]
    else:
        # Get all projects
        projects = db.list_projects()

    # Get summaries for each project
    summaries = [get_project_summary(db, project) for project in projects]

    # Get total costs
    if project_name:
        # For single project, use its costs
        total_costs = summaries[0]['costs'] if summaries else None
    else:
        # For all projects, aggregate costs
        from bob.observability.cost_tracker import ProjectCostSummary
        from dataclasses import dataclass, field
        from collections import defaultdict

        total_cost_sum = 0.0
        by_model_sum = defaultdict(float)
        by_agent_sum = defaultdict(float)

        for summary in summaries:
            costs = summary['costs']
            if costs:
                total_cost_sum += costs.total_cost
                for model, cost in costs.by_model.items():
                    by_model_sum[model] += cost
                for agent, cost in costs.by_agent.items():
                    by_agent_sum[agent] += cost

        # Create aggregate summary
        total_costs = ProjectCostSummary(
            project_id="all",
            project_name="All Projects",
            total_cost=total_cost_sum,
            total_tokens=0,  # Not aggregating tokens for simplicity
            session_count=sum(s['total_sessions'] for s in summaries),
            by_model=dict(by_model_sum),
            by_agent=dict(by_agent_sum),
            by_day={},  # Not aggregating by day for simplicity
        )

    # Display
    if json_output:
        display_json_status(summaries, total_costs)
    else:
        display_text_status(summaries, total_costs, show_details=verbose)
