"""Project management commands for BOB CLI.

This module implements all 'bob project' subcommands for managing projects.
"""

import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import yaml

from bob.database.manager import DatabaseManager
from bob.models.base import Project, ProjectStatus


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
