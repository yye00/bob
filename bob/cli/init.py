"""Init command for BOB - Initialize BOB environment."""

from pathlib import Path
from typing import Optional

import click

from bob.config import ConfigManager, DEFAULT_CONFIG
from bob.database.manager import DatabaseManager


@click.command()
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force initialization even if ~/.bob already exists",
)
@click.option(
    "--db-only",
    is_flag=True,
    help="Only initialize database, skip config creation",
)
@click.option(
    "--config-only",
    is_flag=True,
    help="Only create config file, skip database initialization",
)
def init(force: bool, db_only: bool, config_only: bool) -> None:
    """Initialize BOB environment.

    Creates the ~/.bob directory structure with:
    - config.yaml: Default configuration file
    - bob.db: SQLite database with schema
    - plugins/: Directory for custom plugins
    - cache/: Directory for caching data

    \b
    Examples:
      bob init
      bob init --force
      bob init --db-only
      bob init --config-only
    """
    bob_home = Path.home() / ".bob"

    # Check if already initialized (unless --force)
    if bob_home.exists() and not force:
        click.echo(f"✗ BOB is already initialized at {bob_home}")
        click.echo("  Use --force to reinitialize")
        raise click.Abort()

    click.echo("🤖 Initializing BOB environment...")
    click.echo()

    # Create main directory
    if not bob_home.exists():
        bob_home.mkdir(parents=True)
        click.echo(f"✓ Created {bob_home}")

    # Create subdirectories
    subdirs = ["plugins", "cache", "logs"]
    for subdir in subdirs:
        subdir_path = bob_home / subdir
        if not subdir_path.exists():
            subdir_path.mkdir(parents=True)
            click.echo(f"✓ Created {subdir_path}")

    # Initialize config (unless --db-only)
    if not db_only:
        config_path = bob_home / "config.yaml"
        config_manager = ConfigManager(config_path)

        if not config_path.exists() or force:
            config_manager.save(DEFAULT_CONFIG)
            click.echo(f"✓ Created configuration at {config_path}")
        else:
            click.echo(f"✓ Configuration already exists at {config_path}")

    # Initialize database (unless --config-only)
    if not config_only:
        db_path = bob_home / "bob.db"

        # If --force, remove existing database
        if force and db_path.exists():
            db_path.unlink()
            click.echo(f"  Removed existing database")

        # Initialize database (creates schema automatically)
        db_manager = DatabaseManager(db_path)
        click.echo(f"✓ Initialized database at {db_path}")

    click.echo()
    click.echo("✅ BOB environment initialized successfully!")
    click.echo()
    click.echo("Configuration location: ~/.bob/config.yaml")
    click.echo("Database location: ~/.bob/bob.db")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Set your API key: export ANTHROPIC_API_KEY=your-key-here")
    click.echo("  2. Create a project: bob project create <name> <workspace> <spec-source>")
    click.echo("  3. Run the agent: bob run")
    click.echo()
    click.echo("For more help: bob --help")
