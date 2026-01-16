"""Project management commands for BOB CLI.

This module implements all 'bob project' subcommands for managing projects.
"""

import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import yaml

from bob.database.manager import DatabaseManager
from bob.models.base import Project, ProjectStatus, TaskStatus
from bob.state import StateManager


def validate_project_name(name: str) -> bool:
    """Validate project name is a valid slug format.

    Args:
        name: Project name to validate

    Returns:
        True if valid, False otherwise

    Valid format:
        - Lowercase letters, numbers, hyphens only
        - Must start with a letter
        - Must end with a letter or number
        - No consecutive hyphens
    """
    # Pattern: starts with letter, contains letters/numbers/hyphens, ends with letter/number
    pattern = r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$'
    return bool(re.match(pattern, name))


def create_workspace_structure(workspace_dir: Path, project_id: str, project_name: str) -> None:
    """Create the workspace directory structure for a project.

    Args:
        workspace_dir: Path to workspace directory
        project_id: Project ID
        project_name: Project name

    Creates:
        workspace_dir/
        ├── .bob/
        │   ├── project.yaml    # Project configuration
        │   ├── logs/           # Session logs
        │   └── state/          # Temporary state files
    """
    # Create main workspace directory
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Create .bob subdirectory
    bob_dir = workspace_dir / ".bob"
    bob_dir.mkdir(exist_ok=True)

    # Create subdirectories
    (bob_dir / "logs").mkdir(exist_ok=True)
    (bob_dir / "state").mkdir(exist_ok=True)

    # Create project.yaml config file
    project_config = {
        "project": {
            "id": project_id,
            "name": project_name,
            "created_at": datetime.now().isoformat(),
        },
        "agent": {
            "coding": {
                "model": "claude-sonnet-4-5-20250929",
                "max_turns": 100,
                "temperature": 1.0,
            },
            "research": {
                "model": "claude-sonnet-4-5-20250929",
                "max_turns": 20,
            },
        },
        "escalation": {
            "enabled": True,
            "max_retries": 3,
            "tier2_model": "claude-opus-4-20250514",
        },
        "cost_limits": {
            "per_session": 10.0,  # USD
            "per_day": 50.0,
            "per_project": 1000.0,
        },
    }

    config_path = bob_dir / "project.yaml"
    with open(config_path, "w") as f:
        yaml.dump(project_config, f, default_flow_style=False, sort_keys=False)


@click.command()
@click.argument("name")
@click.argument("workspace", type=click.Path(path_type=Path))
@click.argument("spec_source")
@click.option("--description", "-d", default="", help="Project description")
@click.option("--config", type=click.Path(exists=True, path_type=Path), help="Custom project config file")
@click.pass_context
def create(
    ctx: click.Context,
    name: str,
    workspace: Path,
    spec_source: str,
    description: str,
    config: Optional[Path],
) -> None:
    """Create a new project.

    \b
    Arguments:
        NAME         Project name (slug format: lowercase, hyphens allowed)
        WORKSPACE    Path to project workspace directory
        SPEC_SOURCE  Spec source URI (e.g., file://spec.yaml, github://org/repo/issues)

    \b
    Examples:
        bob project create my-app ./workspace file://spec.yaml
        bob project create api-server ~/projects/api file://features.yaml -d "REST API"
        bob project create web-app /opt/web github://myorg/myrepo/issues

    The create command will:
        1. Validate the project name
        2. Create the workspace directory structure
        3. Initialize the .bob/ subdirectory with config
        4. Register the project in the database
        5. Set the project as active
    """
    # Get database path from context
    db_path = ctx.obj.db_path

    # Validate project name
    if not validate_project_name(name):
        click.echo(f"✗ Invalid project name: {name}", err=True)
        click.echo()
        click.echo("Project name must:", err=True)
        click.echo("  - Start with a lowercase letter", err=True)
        click.echo("  - Contain only lowercase letters, numbers, and hyphens", err=True)
        click.echo("  - Not have consecutive hyphens", err=True)
        click.echo("  - End with a letter or number", err=True)
        click.echo()
        click.echo("Examples: my-app, api-server, web-v2", err=True)
        sys.exit(1)

    # Initialize database manager
    db = DatabaseManager(db_path)

    # Check if project already exists
    existing_projects = db.list_projects()
    if any(p.name == name for p in existing_projects):
        click.echo(f"✗ Project '{name}' already exists", err=True)
        sys.exit(1)

    # Generate project ID
    project_id = f"proj-{uuid.uuid4().hex[:8]}"

    # Create workspace structure
    try:
        create_workspace_structure(workspace, project_id, name)
    except Exception as e:
        click.echo(f"✗ Failed to create workspace structure: {e}", err=True)
        sys.exit(1)

    # Load custom config if provided
    project_config = {}
    if config:
        try:
            with open(config) as f:
                project_config = yaml.safe_load(f) or {}
        except Exception as e:
            click.echo(f"✗ Failed to load config file: {e}", err=True)
            sys.exit(1)

    # Create project object
    project = Project(
        id=project_id,
        name=name,
        description=description,
        workspace_dir=str(workspace.resolve()),
        spec_source=spec_source,
        config=project_config,
        created_at=datetime.now(),
        status=ProjectStatus.ACTIVE,
    )

    # Save to database
    try:
        db.create_project(project)
    except Exception as e:
        click.echo(f"✗ Failed to save project to database: {e}", err=True)
        sys.exit(1)

    # Output success
    click.echo(f"✓ Created project '{name}' ({project_id})")
    click.echo(f"  Workspace: {workspace.resolve()}")
    click.echo(f"  Spec source: {spec_source}")
    click.echo(f"  Config: {workspace.resolve() / '.bob' / 'project.yaml'}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Review the configuration: cat {workspace.resolve() / '.bob' / 'project.yaml'}")
    click.echo(f"  2. Activate the project: bob project use {name}")
    click.echo(f"  3. Sync with spec source: bob sync")
    click.echo(f"  4. Run the agent: bob run")


@click.command()
@click.option(
    "--status",
    "-s",
    type=click.Choice(["active", "paused", "completed", "archived"]),
    help="Filter by project status",
)
@click.option(
    "--json-output",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def list(
    ctx: click.Context,
    status: Optional[str],
    json_output: bool,
) -> None:
    """List all projects.

    \b
    Displays a table of all projects with:
      - Project ID and name
      - Current status
      - Task completion (completed/total)
      - Total cost (USD)

    \b
    Examples:
        bob project list
        bob project list --status active
        bob project list --json

    \b
    Filter by status:
        active      Projects currently active
        paused      Projects temporarily paused
        completed   Projects marked as complete
        archived    Projects archived for reference
    """
    # Get database path from context
    db_path = ctx.obj.db_path

    # Initialize database manager
    db = DatabaseManager(db_path)

    # Query projects with optional status filter
    if status:
        project_status = ProjectStatus(status)
        projects = db.list_projects(status=project_status)
    else:
        projects = db.list_projects()

    # If no projects found
    if not projects:
        if json_output:
            click.echo(json.dumps({"projects": []}))
        else:
            if status:
                click.echo(f"No projects found with status: {status}")
            else:
                click.echo("No projects found. Create one with: bob project create")
        return

    # For JSON output
    if json_output:
        projects_data = []
        for project in projects:
            # Get task statistics
            tasks = db.list_tasks(project_id=project.id)
            completed_tasks = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
            total_tasks = len(tasks)

            # Get cost statistics
            sessions = db.list_sessions(project_id=project.id)
            total_cost = sum(s.cost for s in sessions)

            projects_data.append({
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "status": project.status.value,
                "workspace_dir": project.workspace_dir,
                "spec_source": project.spec_source,
                "created_at": project.created_at.isoformat(),
                "tasks": {
                    "completed": completed_tasks,
                    "total": total_tasks,
                },
                "cost": round(total_cost, 2),
            })

        click.echo(json.dumps({"projects": projects_data}, indent=2))
        return

    # Table output
    click.echo()
    click.echo("Projects:")
    click.echo("=" * 100)
    click.echo(
        f"{'ID':<15} {'Name':<20} {'Status':<12} {'Tasks':<15} {'Cost':<10} {'Description':<25}"
    )
    click.echo("-" * 100)

    for project in projects:
        # Get task statistics
        tasks = db.list_tasks(project_id=project.id)
        completed_tasks = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        total_tasks = len(tasks)

        # Get cost statistics
        sessions = db.list_sessions(project_id=project.id)
        total_cost = sum(s.cost for s in sessions)

        # Format task completion
        if total_tasks > 0:
            task_str = f"{completed_tasks}/{total_tasks}"
        else:
            task_str = "-"

        # Format cost
        cost_str = f"${total_cost:.2f}"

        # Truncate description
        description = project.description[:25] if project.description else "-"

        # Status formatting with color
        status_str = project.status.value
        if project.status == ProjectStatus.ACTIVE:
            status_str = click.style(status_str, fg="green")
        elif project.status == ProjectStatus.PAUSED:
            status_str = click.style(status_str, fg="yellow")
        elif project.status == ProjectStatus.COMPLETED:
            status_str = click.style(status_str, fg="blue")
        else:
            status_str = click.style(status_str, fg="bright_black")

        click.echo(
            f"{project.id:<15} {project.name:<20} {status_str:<20} {task_str:<15} {cost_str:<10} {description:<25}"
        )

    click.echo("=" * 100)
    click.echo(f"Total: {len(projects)} project(s)")
    click.echo()


@click.command()
@click.argument("name")
@click.pass_context
def use(ctx: click.Context, name: str) -> None:
    """Set the active project.

    \b
    Arguments:
        NAME  Project name or ID to activate

    \b
    Examples:
        bob project use my-app
        bob project use proj-a1b2c3d4

    The use command will:
        1. Validate the project exists in the database
        2. Store the project ID in ~/.bob/state.json
        3. Display confirmation message

    Once a project is active, commands like 'bob sync' and 'bob run'
    will operate on that project by default.
    """
    # Get database path from context
    db_path = ctx.obj.db_path

    # Initialize database manager
    db = DatabaseManager(db_path)

    # Try to find project by name or ID
    project = None

    # First try by ID
    if name.startswith("proj-"):
        project = db.get_project(name)

    # If not found, try by name
    if not project:
        projects = db.list_projects()
        matching_projects = [p for p in projects if p.name == name]
        if matching_projects:
            project = matching_projects[0]

    # If still not found, error
    if not project:
        click.echo(f"✗ Project not found: {name}", err=True)
        click.echo()
        click.echo("Available projects:", err=True)
        projects = db.list_projects()
        if projects:
            for p in projects:
                click.echo(f"  {p.name} ({p.id})", err=True)
        else:
            click.echo("  No projects found. Create one with: bob project create", err=True)
        sys.exit(1)

    # Initialize state manager
    state = StateManager()

    # Set active project
    state.set_active_project(project.id)

    # Display confirmation
    click.echo(f"✓ Activated project: {project.name} ({project.id})")
    click.echo(f"  Workspace: {project.workspace_dir}")
    click.echo(f"  Spec source: {project.spec_source}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Sync tasks: bob sync")
    click.echo("  2. View tasks: bob task list")
    click.echo("  3. Run the agent: bob run")


@click.command()
@click.argument("name", required=False)
@click.option(
    "--json-output",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def status(ctx: click.Context, name: Optional[str], json_output: bool) -> None:
    """Show detailed project status.

    \b
    Arguments:
        NAME  Project name or ID (optional, uses active project if not specified)

    \b
    Examples:
        bob project status              # Show active project status
        bob project status my-app       # Show specific project status
        bob project status --json       # JSON output

    Displays:
        - Project information (name, description, workspace, spec source)
        - Task breakdown by status (pending, in_progress, completed, failed, blocked)
        - Cost summary (total, by model, by agent type)
        - Recent activity (last 5 sessions)
    """
    # Get database path from context
    db_path = ctx.obj.db_path

    # Initialize database manager
    db = DatabaseManager(db_path)

    # Determine which project to show status for
    project = None
    if name:
        # Try to find by ID first
        if name.startswith("proj-"):
            project = db.get_project(name)

        # If not found, try by name
        if not project:
            projects = db.list_projects()
            matching_projects = [p for p in projects if p.name == name]
            if matching_projects:
                project = matching_projects[0]
    else:
        # Use active project
        state = StateManager()
        active_project_id = state.get_active_project()
        if active_project_id:
            project = db.get_project(active_project_id)

    # If still not found, error
    if not project:
        if name:
            click.echo(f"✗ Project not found: {name}", err=True)
        else:
            click.echo("✗ No active project found", err=True)
            click.echo("  Set a project with: bob project use <name>", err=True)
            click.echo("  Or specify with: bob project status <name>", err=True)
        sys.exit(1)

    # Get all tasks for this project
    tasks = db.list_tasks(project_id=project.id)

    # Get all sessions for this project
    sessions = db.list_sessions(project_id=project.id)

    # Calculate task breakdown by status
    task_breakdown = {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
        "blocked": 0,
    }
    for task in tasks:
        status_key = task.status.value
        if status_key in task_breakdown:
            task_breakdown[status_key] += 1

    # Calculate cost summary
    total_cost = sum(s.cost for s in sessions)
    cost_by_model = {}
    cost_by_agent = {}
    for session in sessions:
        # Cost by model
        model = session.model or "unknown"
        cost_by_model[model] = cost_by_model.get(model, 0) + session.cost

        # Cost by agent type
        agent = session.agent_type.value if session.agent_type else "unknown"
        cost_by_agent[agent] = cost_by_agent.get(agent, 0) + session.cost

    # Get recent sessions (last 5)
    recent_sessions = sorted(sessions, key=lambda s: s.started_at, reverse=True)[:5]

    # JSON output
    if json_output:
        output = {
            "project": {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "status": project.status.value,
                "workspace_dir": project.workspace_dir,
                "spec_source": project.spec_source,
                "created_at": project.created_at.isoformat(),
            },
            "tasks": {
                "total": len(tasks),
                "breakdown": task_breakdown,
            },
            "costs": {
                "total": round(total_cost, 2),
                "by_model": {k: round(v, 2) for k, v in cost_by_model.items()},
                "by_agent": {k: round(v, 2) for k, v in cost_by_agent.items()},
            },
            "recent_sessions": [
                {
                    "id": s.id,
                    "status": s.status.value,
                    "started_at": s.started_at.isoformat(),
                    "agent_type": s.agent_type.value if s.agent_type else None,
                    "model": s.model,
                    "cost": round(s.cost, 2),
                }
                for s in recent_sessions
            ],
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Human-readable output
    click.echo()
    click.echo("=" * 80)
    click.echo(f"Project: {project.name} ({project.id})")
    click.echo("=" * 80)
    click.echo()

    # Project details
    click.echo("Details:")
    click.echo(f"  Status: {project.status.value}")
    if project.description:
        click.echo(f"  Description: {project.description}")
    click.echo(f"  Workspace: {project.workspace_dir}")
    click.echo(f"  Spec source: {project.spec_source}")
    click.echo(f"  Created: {project.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo()

    # Task breakdown
    click.echo("Tasks:")
    click.echo(f"  Total: {len(tasks)}")
    if tasks:
        click.echo(f"  Pending: {task_breakdown['pending']}")
        click.echo(f"  In progress: {task_breakdown['in_progress']}")
        click.echo(f"  Completed: {click.style(str(task_breakdown['completed']), fg='green')}")
        click.echo(f"  Failed: {click.style(str(task_breakdown['failed']), fg='red')}")
        click.echo(f"  Blocked: {click.style(str(task_breakdown['blocked']), fg='yellow')}")
    click.echo()

    # Cost summary
    click.echo("Costs:")
    click.echo(f"  Total: ${total_cost:.2f}")
    if cost_by_model:
        click.echo("  By model:")
        for model, cost in sorted(cost_by_model.items(), key=lambda x: x[1], reverse=True):
            click.echo(f"    {model}: ${cost:.2f}")
    if cost_by_agent:
        click.echo("  By agent:")
        for agent, cost in sorted(cost_by_agent.items(), key=lambda x: x[1], reverse=True):
            click.echo(f"    {agent}: ${cost:.2f}")
    click.echo()

    # Recent activity
    if recent_sessions:
        click.echo("Recent activity:")
        for session in recent_sessions:
            status_color = "green" if session.status.value == "completed" else "yellow"
            status_str = click.style(session.status.value, fg=status_color)
            agent_str = session.agent_type.value if session.agent_type else "unknown"
            time_str = session.started_at.strftime("%Y-%m-%d %H:%M")
            click.echo(f"  {session.id}: {status_str} | {agent_str} | {time_str} | ${session.cost:.2f}")
    else:
        click.echo("Recent activity: No sessions yet")

    click.echo()
    click.echo("=" * 80)
