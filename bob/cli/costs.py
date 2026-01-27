"""Cost tracking and reporting commands for BOB CLI.

This module implements the 'bob costs' command for viewing cost reports.
"""

import json
import sys
from datetime import datetime
from typing import Optional

import click

from bob.database.manager import DatabaseManager
from bob.observability.cost_tracker import CostTracker
from bob.state import StateManager


@click.command()
@click.option(
    "--project",
    "-p",
    "project_name",
    help="Show costs for specific project (name or ID)",
)
@click.option(
    "--json-output",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def costs(
    ctx: click.Context,
    project_name: Optional[str],
    json_output: bool,
) -> None:
    """Show cost breakdown for projects.

    \b
    Examples:
        bob costs                    # Show total costs across all projects
        bob costs --project my-app   # Show costs for specific project
        bob costs --json-output      # Output as JSON

    Displays:
        - Total cost in USD
        - Breakdown by model (Claude Sonnet, Opus, Haiku)
        - Breakdown by agent type (coding, research, diagnosis)
        - Daily cost trend (last 7 days)
        - Session count and token usage
    """
    # Get database path from context
    db_path = ctx.obj.db_path

    # Initialize database manager
    db = DatabaseManager(db_path)

    # Initialize cost tracker
    cost_tracker = CostTracker(db)

    # If project specified, show costs for that project
    if project_name:
        # Try to find project by ID first
        project = None
        if project_name.startswith("proj-"):
            project = db.get_project(project_name)

        # If not found, try by name
        if not project:
            projects = db.list_projects()
            matching_projects = [p for p in projects if p.name == project_name]
            if matching_projects:
                project = matching_projects[0]

        # If still not found, error
        if not project:
            click.echo(f"✗ Project not found: {project_name}", err=True)
            click.echo()
            click.echo("Available projects:", err=True)
            projects = db.list_projects()
            if projects:
                for p in projects:
                    click.echo(f"  {p.name} ({p.id})", err=True)
            else:
                click.echo(
                    "  No projects found. Create one with: bob project create",
                    err=True,
                )
            sys.exit(1)

        # Get cost summary for this project
        cost_summary = cost_tracker.get_project_costs(project.id)

        # JSON output
        if json_output:
            output = {
                "project": {
                    "id": cost_summary.project_id,
                    "name": cost_summary.project_name,
                },
                "costs": {
                    "total": round(cost_summary.total_cost, 2),
                    "by_model": {
                        k: round(v, 2) for k, v in cost_summary.by_model.items()
                    },
                    "by_agent": {
                        k: round(v, 2) for k, v in cost_summary.by_agent.items()
                    },
                    "by_day": {k: round(v, 2) for k, v in cost_summary.by_day.items()},
                },
                "statistics": {
                    "total_tokens": cost_summary.total_tokens,
                    "session_count": cost_summary.session_count,
                },
            }
            click.echo(json.dumps(output, indent=2))
            return

        # Human-readable output
        click.echo()
        click.echo("=" * 80)
        click.echo(f"Cost Report: {cost_summary.project_name} ({cost_summary.project_id})")
        click.echo("=" * 80)
        click.echo()

        # Total cost
        click.echo("Total Cost:")
        cost_color = "green" if cost_summary.total_cost < 1.0 else "yellow"
        if cost_summary.total_cost > 10.0:
            cost_color = "red"
        click.echo(
            f"  "
            + click.style(f"${cost_summary.total_cost:.2f}", fg=cost_color, bold=True)
        )
        click.echo()

        # Session statistics
        click.echo("Statistics:")
        click.echo(f"  Sessions: {cost_summary.session_count}")
        click.echo(f"  Total tokens: {cost_summary.total_tokens:,}")
        if cost_summary.session_count > 0:
            avg_cost = cost_summary.total_cost / cost_summary.session_count
            click.echo(f"  Avg cost per session: ${avg_cost:.2f}")
        click.echo()

        # Cost by model
        if cost_summary.by_model:
            click.echo("Cost by Model:")
            # Sort by cost descending
            sorted_models = sorted(
                cost_summary.by_model.items(), key=lambda x: x[1], reverse=True
            )
            for model, cost in sorted_models:
                percentage = (cost / cost_summary.total_cost * 100) if cost_summary.total_cost > 0 else 0
                bar = "█" * int(percentage / 2)  # Scale to 50 chars max
                click.echo(f"  {model:<30} ${cost:>8.2f}  {bar} {percentage:.1f}%")
            click.echo()

        # Cost by agent type
        if cost_summary.by_agent:
            click.echo("Cost by Agent Type:")
            # Sort by cost descending
            sorted_agents = sorted(
                cost_summary.by_agent.items(), key=lambda x: x[1], reverse=True
            )
            for agent, cost in sorted_agents:
                percentage = (cost / cost_summary.total_cost * 100) if cost_summary.total_cost > 0 else 0
                bar = "█" * int(percentage / 2)  # Scale to 50 chars max
                click.echo(f"  {agent:<30} ${cost:>8.2f}  {bar} {percentage:.1f}%")
            click.echo()

        # Daily cost trend (last 7 days)
        if cost_summary.by_day:
            click.echo("Daily Cost Trend:")
            # Sort by date
            sorted_days = sorted(cost_summary.by_day.items())
            for day, cost in sorted_days[-7:]:  # Last 7 days
                bar = "█" * max(1, int(cost * 10))  # Scale bars
                click.echo(f"  {day}  ${cost:>8.2f}  {bar}")
            click.echo()

    else:
        # Show costs for all projects
        all_costs = cost_tracker.get_total_costs()

        if not all_costs:
            click.echo("No cost data available.")
            click.echo()
            click.echo("Create a project with: bob project create")
            return

        # Calculate grand totals
        grand_total_cost = sum(c.total_cost for c in all_costs.values())
        grand_total_tokens = sum(c.total_tokens for c in all_costs.values())
        grand_total_sessions = sum(c.session_count for c in all_costs.values())

        # Aggregate by model and agent across all projects
        grand_by_model = {}
        grand_by_agent = {}
        grand_by_day = {}

        for cost_summary in all_costs.values():
            for model, cost in cost_summary.by_model.items():
                grand_by_model[model] = grand_by_model.get(model, 0.0) + cost
            for agent, cost in cost_summary.by_agent.items():
                grand_by_agent[agent] = grand_by_agent.get(agent, 0.0) + cost
            for day, cost in cost_summary.by_day.items():
                grand_by_day[day] = grand_by_day.get(day, 0.0) + cost

        # JSON output
        if json_output:
            output = {
                "summary": {
                    "total_cost": round(grand_total_cost, 2),
                    "total_tokens": grand_total_tokens,
                    "total_sessions": grand_total_sessions,
                    "project_count": len(all_costs),
                },
                "by_model": {k: round(v, 2) for k, v in grand_by_model.items()},
                "by_agent": {k: round(v, 2) for k, v in grand_by_agent.items()},
                "by_day": {k: round(v, 2) for k, v in grand_by_day.items()},
                "projects": [
                    {
                        "id": c.project_id,
                        "name": c.project_name,
                        "cost": round(c.total_cost, 2),
                        "tokens": c.total_tokens,
                        "sessions": c.session_count,
                    }
                    for c in all_costs.values()
                ],
            }
            click.echo(json.dumps(output, indent=2))
            return

        # Human-readable output
        click.echo()
        click.echo("=" * 80)
        click.echo("Cost Report: All Projects")
        click.echo("=" * 80)
        click.echo()

        # Grand totals
        click.echo("Total Cost:")
        cost_color = "green" if grand_total_cost < 5.0 else "yellow"
        if grand_total_cost > 50.0:
            cost_color = "red"
        click.echo(
            f"  "
            + click.style(f"${grand_total_cost:.2f}", fg=cost_color, bold=True)
        )
        click.echo()

        # Statistics
        click.echo("Statistics:")
        click.echo(f"  Projects: {len(all_costs)}")
        click.echo(f"  Sessions: {grand_total_sessions}")
        click.echo(f"  Total tokens: {grand_total_tokens:,}")
        if grand_total_sessions > 0:
            avg_cost = grand_total_cost / grand_total_sessions
            click.echo(f"  Avg cost per session: ${avg_cost:.2f}")
        click.echo()

        # Cost by project
        click.echo("Cost by Project:")
        # Sort by cost descending
        sorted_projects = sorted(
            all_costs.values(), key=lambda x: x.total_cost, reverse=True
        )
        for cost_summary in sorted_projects:
            percentage = (cost_summary.total_cost / grand_total_cost * 100) if grand_total_cost > 0 else 0
            bar = "█" * int(percentage / 2)  # Scale to 50 chars max
            click.echo(
                f"  {cost_summary.project_name:<30} ${cost_summary.total_cost:>8.2f}  {bar} {percentage:.1f}%"
            )
        click.echo()

        # Cost by model
        if grand_by_model:
            click.echo("Cost by Model:")
            # Sort by cost descending
            sorted_models = sorted(
                grand_by_model.items(), key=lambda x: x[1], reverse=True
            )
            for model, cost in sorted_models:
                percentage = (cost / grand_total_cost * 100) if grand_total_cost > 0 else 0
                bar = "█" * int(percentage / 2)  # Scale to 50 chars max
                click.echo(f"  {model:<30} ${cost:>8.2f}  {bar} {percentage:.1f}%")
            click.echo()

        # Cost by agent type
        if grand_by_agent:
            click.echo("Cost by Agent Type:")
            # Sort by cost descending
            sorted_agents = sorted(
                grand_by_agent.items(), key=lambda x: x[1], reverse=True
            )
            for agent, cost in sorted_agents:
                percentage = (cost / grand_total_cost * 100) if grand_total_cost > 0 else 0
                bar = "█" * int(percentage / 2)  # Scale to 50 chars max
                click.echo(f"  {agent:<30} ${cost:>8.2f}  {bar} {percentage:.1f}%")
            click.echo()

        # Daily cost trend (last 7 days)
        if grand_by_day:
            click.echo("Daily Cost Trend:")
            # Sort by date
            sorted_days = sorted(grand_by_day.items())
            for day, cost in sorted_days[-7:]:  # Last 7 days
                bar = "█" * max(1, int(cost * 10))  # Scale bars
                click.echo(f"  {day}  ${cost:>8.2f}  {bar}")
            click.echo()
