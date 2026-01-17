#!/usr/bin/env python3
"""
CLI commands for configuration management.

Commands:
- bob config show - Display current configuration
- bob config edit - Open configuration file in editor
"""

import json
import os
import subprocess
from pathlib import Path

import click
import yaml
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


@config.command()
@click.option(
    '--config-path',
    type=click.Path(path_type=Path),
    help='Custom config file path'
)
@click.option(
    '--editor',
    envvar='EDITOR',
    help='Editor to use (defaults to $EDITOR environment variable)'
)
@click.option(
    '--json-output',
    is_flag=True,
    help='Output result as JSON'
)
def edit(config_path: Path | None, editor: str | None, json_output: bool):
    """
    Open configuration file in editor.

    Opens ~/.bob/config.yaml in your preferred text editor.
    Uses $EDITOR environment variable or falls back to sensible defaults.
    After editing, validates the YAML syntax and structure.

    Examples:
        bob config edit
        bob config edit --editor nano
        bob config edit --config-path /path/to/config.yaml
    """
    manager = get_config_manager(config_path)
    config_file = manager.config_path

    # Ensure parent directory exists
    config_file.parent.mkdir(parents=True, exist_ok=True)

    # Create config file with defaults if it doesn't exist
    if not config_file.exists():
        manager.save(manager.get_all())
        if not json_output:
            console.print(f"[yellow]Created new config file:[/] {config_file}")
            console.print()

    # Determine which editor to use
    editor_cmd = editor or os.environ.get('EDITOR') or _get_default_editor()

    if not editor_cmd:
        error_msg = "No editor specified. Set $EDITOR environment variable or use --editor option."
        if json_output:
            output = {
                "status": "error",
                "error": error_msg,
                "config_path": str(config_file)
            }
            click.echo(json.dumps(output, indent=2))
        else:
            console.print(f"[red]✗ {error_msg}[/]")
            console.print()
            console.print("Examples:")
            console.print("  export EDITOR=nano")
            console.print("  bob config edit --editor vim")
            console.print()
        raise click.Exit(1)

    # Store original content for comparison
    original_content = config_file.read_text() if config_file.exists() else ""

    # Open editor
    try:
        if not json_output:
            console.print(f"[cyan]Opening editor:[/] {editor_cmd}")
            console.print(f"[cyan]Config file:[/] {config_file}")
            console.print()

        result = subprocess.run([editor_cmd, str(config_file)])

        if result.returncode != 0:
            error_msg = f"Editor exited with code {result.returncode}"
            if json_output:
                output = {
                    "status": "error",
                    "error": error_msg,
                    "config_path": str(config_file)
                }
                click.echo(json.dumps(output, indent=2))
            else:
                console.print(f"[red]✗ {error_msg}[/]")
                console.print()
            raise click.Exit(1)

    except FileNotFoundError:
        error_msg = f"Editor not found: {editor_cmd}"
        if json_output:
            output = {
                "status": "error",
                "error": error_msg,
                "config_path": str(config_file)
            }
            click.echo(json.dumps(output, indent=2))
        else:
            console.print(f"[red]✗ {error_msg}[/]")
            console.print()
            console.print("Try setting a different editor:")
            console.print("  bob config edit --editor nano")
            console.print("  bob config edit --editor vim")
            console.print()
        raise click.Exit(1)

    # Check if file was modified
    new_content = config_file.read_text() if config_file.exists() else ""
    was_modified = new_content != original_content

    # Validate YAML after editing
    validation_errors = _validate_config_file(config_file)

    if validation_errors:
        if json_output:
            output = {
                "status": "error",
                "error": "Configuration validation failed",
                "validation_errors": validation_errors,
                "config_path": str(config_file),
                "modified": was_modified
            }
            click.echo(json.dumps(output, indent=2))
        else:
            console.print("[red]✗ Configuration validation failed:[/]")
            console.print()
            for error in validation_errors:
                console.print(f"  [red]•[/] {error}")
            console.print()
            console.print(f"[yellow]Please fix the errors in:[/] {config_file}")
            console.print()
        raise click.Exit(1)

    # Success
    if json_output:
        output = {
            "status": "success",
            "config_path": str(config_file),
            "modified": was_modified,
            "validation_errors": []
        }
        click.echo(json.dumps(output, indent=2))
    else:
        if was_modified:
            console.print("[green]✓ Configuration updated successfully[/]")
        else:
            console.print("[dim]No changes made[/]")
        console.print()
        console.print(f"  Config file: {config_file}")
        console.print()


def _get_default_editor() -> str | None:
    """
    Get a sensible default editor based on platform.

    Returns:
        Default editor command or None if none found
    """
    # Try common editors in order of preference
    common_editors = ['nano', 'vim', 'vi', 'emacs', 'code', 'subl']

    for editor in common_editors:
        # Check if editor exists in PATH
        try:
            result = subprocess.run(
                ['which', editor],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return editor
        except (subprocess.SubprocessError, FileNotFoundError):
            continue

    return None


def _validate_config_file(config_file: Path) -> list[str]:
    """
    Validate configuration file for YAML syntax and structure.

    Args:
        config_file: Path to config file

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if not config_file.exists():
        errors.append("Config file does not exist")
        return errors

    # Try to parse YAML
    try:
        with open(config_file) as f:
            config_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        errors.append(f"Invalid YAML syntax: {e}")
        return errors

    # Check that it's a dictionary
    if not isinstance(config_data, dict):
        errors.append("Config file must contain a YAML dictionary")
        return errors

    # Validate structure (optional - basic checks)
    # We could add more validation here, but for now just ensure it's valid YAML

    return errors
