"""Main CLI entry point for BOB framework.

This module defines the main 'bob' command and all subcommands.
"""

import sys
from pathlib import Path
from typing import Optional

import click

# Import project commands
from bob.cli import config as config_commands
from bob.cli import costs as costs_commands
from bob.cli import init as init_commands
from bob.cli import logs as logs_commands
from bob.cli import metrics as metrics_commands
from bob.cli import plugin as plugin_commands
from bob.cli import project as project_commands
from bob.cli import research as research_commands
from bob.cli import run as run_commands
from bob.cli import status as status_commands
from bob.cli import sync as sync_commands
from bob.cli import task as task_commands

# Version info
__version__ = "0.1.0"


# ============================================================================
# Global Context Object
# ============================================================================


class GlobalContext:
    """Global context passed between commands."""

    def __init__(self) -> None:
        self.verbose: bool = False
        self.quiet: bool = False
        self.json_output: bool = False
        self.project_id: Optional[str] = None
        self.db_path: Optional[Path] = None


# Global context instance
pass_context = click.make_pass_decorator(GlobalContext, ensure=True)


# ============================================================================
# Main Command Group
# ============================================================================


@click.group()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output (detailed logging)",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress all non-essential output",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format (for scripting)",
)
@click.option(
    "--project",
    "-p",
    "project_id",
    help="Project ID to operate on (overrides active project)",
)
@click.option(
    "--db",
    "db_path",
    type=click.Path(path_type=Path),
    help="Path to database file (default: ~/.bob/bob.db)",
)
@click.version_option(version=__version__, prog_name="bob")
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: bool,
    quiet: bool,
    json_output: bool,
    project_id: Optional[str],
    db_path: Optional[Path],
) -> None:
    """BOB - Build Orchestration Bot.

    A generalized autonomous coding framework for managing AI-assisted
    software development projects.

    \b
    Quick Start:
      bob project create my-app ./workspace file://spec.yaml
      bob project use my-app
      bob run

    \b
    Common Commands:
      project     Manage projects
      task        View and manage tasks
      run         Run the autonomous coding agent
      status      View project and task status
      logs        View session logs
      costs       View cost reports
      config      Manage configuration

    For detailed help on any command, use:
      bob COMMAND --help
    """
    # Create and populate global context
    ctx.ensure_object(GlobalContext)
    ctx.obj.verbose = verbose
    ctx.obj.quiet = quiet
    ctx.obj.json_output = json_output
    ctx.obj.project_id = project_id

    # Determine database path
    if db_path:
        ctx.obj.db_path = db_path
    else:
        # Default to ~/.bob/bob.db
        bob_dir = Path.home() / ".bob"
        # Only create directory if not running init command
        # (init will create it properly)
        if bob_dir.exists():
            ctx.obj.db_path = bob_dir / "bob.db"
        else:
            # Set path but don't create yet - init will handle it
            ctx.obj.db_path = bob_dir / "bob.db"


# ============================================================================
# Command Groups
# ============================================================================


@cli.group()
def project() -> None:
    """Manage projects.

    \b
    Commands for creating, listing, and managing projects.
    A project is the top-level container for tasks and sessions.

    \b
    Examples:
      bob project create my-app ./workspace file://spec.yaml
      bob project list
      bob project use my-app
      bob project status
    """
    pass


# Add project subcommands
project.add_command(project_commands.create)
project.add_command(project_commands.list)
project.add_command(project_commands.use)
project.add_command(project_commands.status)
project.add_command(project_commands.delete)

# Add sync command directly (not a subcommand group, just a command)
cli.add_command(sync_commands.sync)

# Add plan command (Opus-powered feature generation)
from bob.cli import plan as plan_commands
cli.add_command(plan_commands.plan)


@cli.group()
def task() -> None:
    """View and manage tasks.

    \b
    Commands for viewing task status, filtering by priority,
    and manually updating task state.

    \b
    Examples:
      bob task list
      bob task list --status pending --priority critical
      bob task show F001
      bob task update F001 --status completed
    """
    pass


# Add task subcommands
task.add_command(task_commands.list)
task.add_command(task_commands.show)
task.add_command(task_commands.retry)
task.add_command(task_commands.skip)
task.add_command(task_commands.add)

# Add run command
cli.add_command(run_commands.run)

# Add research command
cli.add_command(research_commands.research)

# Add status command
cli.add_command(status_commands.status)

# Sync command is added directly from sync_commands module

# Add logs command
cli.add_command(logs_commands.logs)

# Add costs command directly (not a group, just a command)
cli.add_command(costs_commands.costs)

# Add metrics command
cli.add_command(metrics_commands.metrics)


@cli.group()
def config() -> None:
    """Manage configuration.

    \b
    View and update BOB configuration, including agent settings,
    model selection, and tool permissions.

    \b
    Examples:
      bob config show
      bob config set agent.coding.model claude-opus-4
      bob config set agent.coding.max_turns 100
    """
    pass


# Add config subcommands
config.add_command(config_commands.show)
config.add_command(config_commands.set_config)
config.add_command(config_commands.edit)


# Add plugin command group directly (it's already a group)
cli.add_command(plugin_commands.plugin)


# ============================================================================
# Standalone Commands
# ============================================================================

# Add init command
cli.add_command(init_commands.init)


@cli.command()
def version() -> None:
    """Show version information.

    Displays BOB version and Python version.
    """
    click.echo(f"BOB version {__version__}")
    click.echo(f"Python {sys.version}")


@cli.command()
def examples() -> None:
    """Show usage examples.

    Displays common usage patterns and workflows.
    """
    examples_text = """
🤖 BOB - Build Orchestration Bot
Common Usage Examples

═══════════════════════════════════════════════════════════════
GETTING STARTED
═══════════════════════════════════════════════════════════════

1. Create a new project:
   $ bob project create my-app ./workspace file://spec.yaml

2. Activate the project:
   $ bob project use my-app

3. Run the autonomous agent:
   $ bob run

═══════════════════════════════════════════════════════════════
PROJECT MANAGEMENT
═══════════════════════════════════════════════════════════════

List all projects:
  $ bob project list

Show project status:
  $ bob project status

Pause a project:
  $ bob project pause my-app

Resume a project:
  $ bob project resume my-app

═══════════════════════════════════════════════════════════════
TASK MANAGEMENT
═══════════════════════════════════════════════════════════════

List all tasks:
  $ bob task list

List critical tasks:
  $ bob task list --priority critical

List pending tasks:
  $ bob task list --status pending

Show task details:
  $ bob task show F001

═══════════════════════════════════════════════════════════════
RUNNING AGENTS
═══════════════════════════════════════════════════════════════

Run on active project:
  $ bob run

Run a specific task:
  $ bob run --task F001

Run with custom max turns:
  $ bob run --max-turns 50

Run with specific agent:
  $ bob run --agent coding

═══════════════════════════════════════════════════════════════
MONITORING & LOGS
═══════════════════════════════════════════════════════════════

View recent session logs:
  $ bob logs

View logs for specific session:
  $ bob logs --session sess-123

View logs for a task:
  $ bob logs --task F001

Follow latest session:
  $ bob logs --tail

═══════════════════════════════════════════════════════════════
COST TRACKING
═══════════════════════════════════════════════════════════════

View total costs:
  $ bob costs

View costs for a project:
  $ bob costs --project my-app

View costs for a task:
  $ bob costs --task F001

View costs since date:
  $ bob costs --since 2024-01-01

═══════════════════════════════════════════════════════════════
CONFIGURATION
═══════════════════════════════════════════════════════════════

Show configuration:
  $ bob config show

Set agent model:
  $ bob config set agent.coding.model claude-opus-4

Set max turns:
  $ bob config set agent.coding.max_turns 100

═══════════════════════════════════════════════════════════════
For more help, use: bob COMMAND --help
═══════════════════════════════════════════════════════════════
    """
    click.echo(examples_text)


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> None:
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
