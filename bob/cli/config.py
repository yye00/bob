#!/usr/bin/env python3
"""
CLI commands for configuration management.

Commands:
- bob config show - Display current configuration
"""

import json
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from bob.config import get_config_manager


console = Console()


@click.group()
def config():
    """Manage BOB configuration."""
    pass


@config.command()
@click.option(
    '--json-output',
    is_flag=True,
    help='Output configuration as JSON'
)
@click.option(
    '--config-path',
    type=click.Path(path_type=Path),
    help='Custom config file path'
)
def show(json_output: bool, config_path: Path | None):
    """
    Display current configuration.

    Shows all configuration values from ~/.bob/config.yaml.
    If the config file doesn't exist, shows default values.

    Examples:
        bob config show
        bob config show --json-output
        bob config show --config-path /path/to/config.yaml
    """
    manager = get_config_manager(config_path)
    config_data = manager.get_all()

    if json_output:
        # JSON output
        output = {
            "config_path": str(manager.config_path),
            "config_exists": manager.config_exists(),
            "config": config_data
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Rich console output
    console.print()

    # Header
    if manager.config_exists():
        console.print(f"[bold cyan]Configuration[/] (from {manager.config_path})", style="bold")
    else:
        console.print(
            f"[bold yellow]Configuration[/] (default - no config file at {manager.config_path})",
            style="bold"
        )

    console.print()

    # Display each section
    _display_models_section(config_data.get("models", {}))
    _display_api_section(config_data.get("api", {}))
    _display_database_section(config_data.get("database", {}))
    _display_logging_section(config_data.get("logging", {}))
    _display_limits_section(config_data.get("limits", {}))
    _display_escalation_section(config_data.get("escalation", {}))

    console.print()

    # Footer
    if not manager.config_exists():
        console.print(
            "[dim]To create a config file with these defaults, run:[/]",
        )
        console.print(
            f"[dim]  mkdir -p {manager.config_path.parent} && cp <defaults> {manager.config_path}[/]"
        )
        console.print()


def _display_models_section(models: dict):
    """Display models configuration section."""
    table = Table(title="Models", show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Default Model", models.get("default", "N/A"))
    table.add_row("Escalation Model", models.get("escalation", "N/A"))

    console.print(table)
    console.print()


def _display_api_section(api: dict):
    """Display API configuration section."""
    table = Table(title="API Configuration", show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    api_key = api.get("anthropic_api_key", "")
    if api_key and api_key != "${ANTHROPIC_API_KEY}":
        # Mask the API key
        masked = f"{api_key[:10]}...{api_key[-4:]}" if len(api_key) > 14 else "***"
        table.add_row("Anthropic API Key", masked)
    else:
        table.add_row("Anthropic API Key", "[dim]${ANTHROPIC_API_KEY}[/]")

    console.print(table)
    console.print()


def _display_database_section(database: dict):
    """Display database configuration section."""
    table = Table(title="Database", show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Type", database.get("type", "N/A"))
    table.add_row("Path", database.get("path", "N/A"))

    console.print(table)
    console.print()


def _display_logging_section(logging: dict):
    """Display logging configuration section."""
    table = Table(title="Logging", show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Level", logging.get("level", "N/A"))
    table.add_row("Format", logging.get("format", "N/A"))

    console.print(table)
    console.print()


def _display_limits_section(limits: dict):
    """Display cost limits configuration section."""
    table = Table(title="Cost Limits", show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    max_project = limits.get("max_cost_per_project", 0)
    max_session = limits.get("max_cost_per_session", 0)
    warn_percent = limits.get("warn_at_percent", 0)

    table.add_row("Max Cost Per Project", f"${max_project:.2f}")
    table.add_row("Max Cost Per Session", f"${max_session:.2f}")
    table.add_row("Warning Threshold", f"{warn_percent}%")

    console.print(table)
    console.print()


def _display_escalation_section(escalation: dict):
    """Display escalation configuration section."""
    table = Table(title="Escalation", show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Max Attempts Per Model", str(escalation.get("max_attempts_per_model", "N/A")))

    models = escalation.get("models", {})
    if models:
        table.add_row("Tier 1 Model", models.get("tier1", "N/A"))
        table.add_row("Tier 2 Model", models.get("tier2", "N/A"))

    console.print(table)
    console.print()


@config.command('set')
@click.argument('key')
@click.argument('value')
@click.option(
    '--config-path',
    type=click.Path(path_type=Path),
    help='Custom config file path'
)
@click.option(
    '--json-output',
    is_flag=True,
    help='Output result as JSON'
)
def set_config(key: str, value: str, config_path: Path | None, json_output: bool):
    """
    Set a configuration value.

    Uses dot notation for nested keys (e.g., 'models.default').
    The value is automatically converted to the appropriate type
    (int, float, bool, or string).

    Examples:
        bob config set models.default claude-opus-4-5-20251101
        bob config set limits.max_cost_per_project 200.0
        bob config set escalation.max_attempts_per_model 5
        bob config set logging.level DEBUG
    """
    manager = get_config_manager(config_path)

    # Validate key exists in default schema
    if not _validate_key(key):
        if json_output:
            output = {
                "error": f"Invalid configuration key: {key}",
                "valid_keys": _get_valid_keys()
            }
            click.echo(json.dumps(output, indent=2))
        else:
            console.print(f"[red]✗ Invalid configuration key:[/] {key}")
            console.print()
            console.print("Valid keys:")
            for valid_key in _get_valid_keys():
                console.print(f"  - {valid_key}")
            console.print()
        raise click.Exit(1)

    # Convert value to appropriate type
    converted_value = _convert_value(value)

    # Load existing config (or defaults)
    current_config = manager.load()

    # Set the value
    manager.set(key, converted_value)

    # Save to file
    manager.save(manager.get_all())

    if json_output:
        output = {
            "status": "success",
            "key": key,
            "value": converted_value,
            "config_path": str(manager.config_path)
        }
        click.echo(json.dumps(output, indent=2))
    else:
        console.print()
        console.print(f"[green]✓ Configuration updated[/]")
        console.print()
        console.print(f"  Key: [cyan]{key}[/]")
        console.print(f"  Value: [yellow]{converted_value}[/]")
        console.print(f"  Config: {manager.config_path}")
        console.print()


def _validate_key(key: str) -> bool:
    """
    Validate that a config key exists in the default schema.

    Args:
        key: Dot-notation config key

    Returns:
        True if valid, False otherwise
    """
    valid_keys = _get_valid_keys()
    return key in valid_keys


def _get_valid_keys() -> list[str]:
    """
    Get list of all valid configuration keys.

    Returns:
        List of valid keys in dot notation
    """
    from bob.config import DEFAULT_CONFIG

    def _flatten_keys(d: dict, prefix: str = "") -> list[str]:
        """Recursively flatten nested dict keys."""
        keys = []
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.extend(_flatten_keys(v, full_key))
            else:
                keys.append(full_key)
        return keys

    return _flatten_keys(DEFAULT_CONFIG)


def _convert_value(value: str) -> int | float | bool | str:
    """
    Convert string value to appropriate type.

    Args:
        value: String value to convert

    Returns:
        Converted value (int, float, bool, or str)
    """
    # Try boolean
    if value.lower() in ('true', 'yes', '1'):
        return True
    if value.lower() in ('false', 'no', '0'):
        return False

    # Try integer
    try:
        return int(value)
    except ValueError:
        pass

    # Try float
    try:
        return float(value)
    except ValueError:
        pass

    # Return as string
    return value
