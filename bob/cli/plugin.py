"""Plugin management commands.

Commands for listing, installing, and uninstalling BOB plugins.
"""

from pathlib import Path
from typing import Optional

import click

from bob.plugins.base import PluginRegistry


@click.group()
def plugin() -> None:
    """Manage plugins.

    Commands for installing, uninstalling, and listing plugins
    that extend BOB functionality.

    Examples:
      bob plugin list
      bob plugin install /path/to/plugin
      bob plugin uninstall my-plugin
    """
    pass


@plugin.command("list")
@click.option(
    "--loaded-only",
    is_flag=True,
    help="Show only loaded plugins",
)
@click.option(
    "--type",
    "plugin_type",
    type=click.Choice(["agent", "spec_source", "tool"], case_sensitive=False),
    help="Filter by plugin type",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
def list_plugins(loaded_only: bool, plugin_type: Optional[str], json_output: bool) -> None:
    """List installed plugins.

    Shows all discovered and loaded plugins. Use --loaded-only to see
    only currently loaded plugins, or --type to filter by plugin type.

    Examples:
      bob plugin list
      bob plugin list --loaded-only
      bob plugin list --type agent
      bob plugin list --json
    """
    registry = PluginRegistry()

    if loaded_only:
        # Show only loaded plugins
        plugins = registry.get_all_plugins()

        if plugin_type:
            plugins = [p for p in plugins if p.plugin_type == plugin_type]

        if json_output:
            import json
            data = [p.to_dict() for p in plugins]
            click.echo(json.dumps(data, indent=2))
        else:
            if not plugins:
                click.echo("No loaded plugins.")
                return

            click.echo("Loaded plugins:")
            for p in plugins:
                status = "✓" if p.is_loaded else " "
                click.echo(f"  [{status}] {p.name} (v{p.version}) - {p.plugin_type}")
                click.echo(f"      {p.description}")
    else:
        # Show all discovered plugins
        registry.discover_plugins()
        discovered = registry.list_discovered()
        loaded = registry.list_loaded()

        if json_output:
            import json
            data = {
                "discovered": discovered,
                "loaded": loaded,
            }
            click.echo(json.dumps(data, indent=2))
        else:
            if not discovered and not loaded:
                click.echo("No plugins found.")
                click.echo()
                click.echo("Plugins should be placed in: ~/.bob/plugins/")
                return

            all_plugins = set(discovered) | set(loaded)

            click.echo("Available plugins:")
            for name in sorted(all_plugins):
                is_loaded = name in loaded
                status = "✓" if is_loaded else " "
                click.echo(f"  [{status}] {name}")

            click.echo()
            click.echo(f"Total: {len(all_plugins)} plugins ({len(loaded)} loaded)")


@plugin.command("install")
@click.argument("plugin_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--force",
    is_flag=True,
    help="Force installation even if plugin already exists",
)
def install_plugin(plugin_path: Path, force: bool) -> None:
    """Install a plugin from a file path.

    Copies the plugin to ~/.bob/plugins/ and registers it for loading.

    Args:
        plugin_path: Path to plugin file or directory

    Examples:
      bob plugin install /path/to/my_plugin.py
      bob plugin install /path/to/plugin_package/
      bob plugin install plugin.py --force
    """
    import shutil

    # Get plugin directory
    plugins_dir = Path.home() / ".bob" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Determine destination
    if plugin_path.is_file():
        dest = plugins_dir / plugin_path.name
    else:
        dest = plugins_dir / plugin_path.name

    # Check if already exists
    if dest.exists() and not force:
        click.echo(f"Error: Plugin already exists at {dest}")
        click.echo("Use --force to overwrite.")
        raise click.Abort()

    # Copy plugin
    try:
        if plugin_path.is_file():
            shutil.copy2(plugin_path, dest)
        else:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(plugin_path, dest)

        click.echo(f"✓ Plugin installed: {plugin_path.name}")
        click.echo(f"  Location: {dest}")
        click.echo()
        click.echo("Run 'bob plugin list' to see installed plugins.")
    except Exception as e:
        click.echo(f"Error installing plugin: {e}", err=True)
        raise click.Abort()


@plugin.command("uninstall")
@click.argument("plugin_name")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt",
)
def uninstall_plugin(plugin_name: str, yes: bool) -> None:
    """Uninstall a plugin by name.

    Removes the plugin from ~/.bob/plugins/ and unloads it if currently loaded.

    Args:
        plugin_name: Name of plugin to uninstall

    Examples:
      bob plugin uninstall my-plugin
      bob plugin uninstall my-plugin --yes
    """
    import shutil

    plugins_dir = Path.home() / ".bob" / "plugins"
    registry = PluginRegistry()

    # Try to unload if loaded
    if plugin_name in registry.list_loaded():
        registry.unload_plugin(plugin_name)
        click.echo(f"Unloaded plugin: {plugin_name}")

    # Find plugin file/directory
    plugin_file = plugins_dir / f"{plugin_name}.py"
    plugin_dir = plugins_dir / plugin_name

    target = None
    if plugin_file.exists():
        target = plugin_file
    elif plugin_dir.exists():
        target = plugin_dir

    if not target:
        click.echo(f"Error: Plugin '{plugin_name}' not found in {plugins_dir}", err=True)
        raise click.Abort()

    # Confirm deletion
    if not yes:
        click.echo(f"This will remove: {target}")
        if not click.confirm("Are you sure?"):
            click.echo("Cancelled.")
            return

    # Remove plugin
    try:
        if target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)

        click.echo(f"✓ Plugin uninstalled: {plugin_name}")
    except Exception as e:
        click.echo(f"Error uninstalling plugin: {e}", err=True)
        raise click.Abort()


@plugin.command("load")
@click.argument("plugin_name")
def load_plugin(plugin_name: str) -> None:
    """Load a plugin.

    Loads a plugin that has been installed but not yet loaded.

    Args:
        plugin_name: Name of plugin to load

    Examples:
      bob plugin load my-plugin
    """
    registry = PluginRegistry()
    registry.discover_plugins()

    if plugin_name in registry.list_loaded():
        click.echo(f"Plugin '{plugin_name}' is already loaded.")
        return

    if registry.load_plugin(plugin_name):
        click.echo(f"✓ Plugin loaded: {plugin_name}")
    else:
        click.echo(f"Error: Failed to load plugin '{plugin_name}'", err=True)
        click.echo("Make sure the plugin is installed and properly formatted.")
        raise click.Abort()


@plugin.command("unload")
@click.argument("plugin_name")
def unload_plugin_cmd(plugin_name: str) -> None:
    """Unload a plugin.

    Unloads a currently loaded plugin without uninstalling it.

    Args:
        plugin_name: Name of plugin to unload

    Examples:
      bob plugin unload my-plugin
    """
    registry = PluginRegistry()

    if plugin_name not in registry.list_loaded():
        click.echo(f"Plugin '{plugin_name}' is not loaded.")
        return

    if registry.unload_plugin(plugin_name):
        click.echo(f"✓ Plugin unloaded: {plugin_name}")
    else:
        click.echo(f"Error: Failed to unload plugin '{plugin_name}'", err=True)
        raise click.Abort()


@plugin.command("info")
@click.argument("plugin_name")
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
def plugin_info(plugin_name: str, json_output: bool) -> None:
    """Show detailed information about a plugin.

    Displays plugin metadata including name, version, description, type,
    and load status.

    Args:
        plugin_name: Name of plugin to show info for

    Examples:
      bob plugin info my-plugin
      bob plugin info my-plugin --json
    """
    registry = PluginRegistry()
    plugin = registry.get_plugin(plugin_name)

    if not plugin:
        # Try to load it first
        registry.discover_plugins()
        if plugin_name in registry.list_discovered():
            click.echo(f"Plugin '{plugin_name}' is installed but not loaded.")
            click.echo("Run 'bob plugin load {plugin_name}' to load it.")
        else:
            click.echo(f"Error: Plugin '{plugin_name}' not found.", err=True)
        raise click.Abort()

    if json_output:
        import json
        click.echo(json.dumps(plugin.to_dict(), indent=2))
    else:
        click.echo(f"Plugin: {plugin.name}")
        click.echo(f"Version: {plugin.version}")
        click.echo(f"Type: {plugin.plugin_type}")
        click.echo(f"Description: {plugin.description}")
        click.echo(f"Loaded: {'Yes' if plugin.is_loaded else 'No'}")
