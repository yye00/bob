"""Tests for plugin CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bob.cli.main import cli


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_plugin_dir(tmp_path):
    """Create a mock plugin directory."""
    plugin_dir = tmp_path / ".bob" / "plugins"
    plugin_dir.mkdir(parents=True)
    return plugin_dir


class TestPluginListCommand:
    """Test 'bob plugin list' command."""

    def test_plugin_list_help(self, runner):
        """Test plugin list help message."""
        result = runner.invoke(cli, ["plugin", "list", "--help"])
        assert result.exit_code == 0
        assert "List installed plugins" in result.output

    @patch('bob.cli.plugin.PluginRegistry')
    def test_plugin_list_empty(self, mock_registry_class, runner):
        """Test listing plugins when none are installed."""
        mock_registry = MagicMock()
        mock_registry.get_all_plugins.return_value = []
        mock_registry.list_discovered.return_value = []
        mock_registry.list_loaded.return_value = []
        mock_registry_class.return_value = mock_registry

        result = runner.invoke(cli, ["plugin", "list"])
        assert result.exit_code == 0
        assert "No plugins found" in result.output

    @patch('bob.cli.plugin.PluginRegistry')
    def test_plugin_list_loaded_only(self, mock_registry_class, runner):
        """Test listing only loaded plugins."""
        mock_plugin = MagicMock()
        mock_plugin.name = "test-plugin"
        mock_plugin.version = "1.0.0"
        mock_plugin.plugin_type = "agent"
        mock_plugin.description = "Test plugin"
        mock_plugin.is_loaded = True

        mock_registry = MagicMock()
        mock_registry.get_all_plugins.return_value = [mock_plugin]
        mock_registry_class.return_value = mock_registry

        result = runner.invoke(cli, ["plugin", "list", "--loaded-only"])
        assert result.exit_code == 0
        assert "test-plugin" in result.output

    @patch('bob.cli.plugin.PluginRegistry')
    def test_plugin_list_json_output(self, mock_registry_class, runner):
        """Test JSON output for plugin list."""
        mock_plugin = MagicMock()
        mock_plugin.to_dict.return_value = {
            "name": "test-plugin",
            "version": "1.0.0",
            "type": "agent",
            "loaded": True,
        }

        mock_registry = MagicMock()
        mock_registry.get_all_plugins.return_value = [mock_plugin]
        mock_registry_class.return_value = mock_registry

        result = runner.invoke(cli, ["plugin", "list", "--loaded-only", "--json"])
        assert result.exit_code == 0

        # Verify JSON output
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "test-plugin"


class TestPluginInstallCommand:
    """Test 'bob plugin install' command."""

    def test_plugin_install_help(self, runner):
        """Test plugin install help message."""
        result = runner.invoke(cli, ["plugin", "install", "--help"])
        assert result.exit_code == 0
        assert "Install a plugin" in result.output

    def test_plugin_install_file(self, runner, tmp_path, monkeypatch):
        """Test installing a plugin from a file."""
        # Set HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        # Create a plugin file
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("# Test plugin")

        result = runner.invoke(cli, ["plugin", "install", str(plugin_file)])
        assert result.exit_code == 0
        assert "Plugin installed" in result.output

        # Verify plugin was copied
        installed = tmp_path / ".bob" / "plugins" / "test_plugin.py"
        assert installed.exists()

    def test_plugin_install_directory(self, runner, tmp_path, monkeypatch):
        """Test installing a plugin from a directory."""
        # Set HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        # Create a plugin directory
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# Test plugin")

        result = runner.invoke(cli, ["plugin", "install", str(plugin_dir)])
        assert result.exit_code == 0
        assert "Plugin installed" in result.output

        # Verify plugin was copied
        installed = tmp_path / ".bob" / "plugins" / "test_plugin"
        assert installed.exists()
        assert (installed / "__init__.py").exists()

    def test_plugin_install_already_exists(self, runner, tmp_path, monkeypatch):
        """Test installing when plugin already exists."""
        # Set HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        # Create plugin file
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("# Test plugin")

        # Install once
        runner.invoke(cli, ["plugin", "install", str(plugin_file)])

        # Try to install again
        result = runner.invoke(cli, ["plugin", "install", str(plugin_file)])
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_plugin_install_force(self, runner, tmp_path, monkeypatch):
        """Test forcing plugin installation."""
        # Set HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        # Create plugin file
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("# Test plugin v1")

        # Install once
        runner.invoke(cli, ["plugin", "install", str(plugin_file)])

        # Update plugin content
        plugin_file.write_text("# Test plugin v2")

        # Force install
        result = runner.invoke(cli, ["plugin", "install", str(plugin_file), "--force"])
        assert result.exit_code == 0
        assert "Plugin installed" in result.output

        # Verify new content
        installed = tmp_path / ".bob" / "plugins" / "test_plugin.py"
        assert "v2" in installed.read_text()


class TestPluginUninstallCommand:
    """Test 'bob plugin uninstall' command."""

    def test_plugin_uninstall_help(self, runner):
        """Test plugin uninstall help message."""
        result = runner.invoke(cli, ["plugin", "uninstall", "--help"])
        assert result.exit_code == 0
        assert "Uninstall a plugin" in result.output

    def test_plugin_uninstall_file(self, runner, tmp_path, monkeypatch):
        """Test uninstalling a plugin file."""
        # Set HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        # Create installed plugin
        plugins_dir = tmp_path / ".bob" / "plugins"
        plugins_dir.mkdir(parents=True)
        plugin_file = plugins_dir / "test_plugin.py"
        plugin_file.write_text("# Test plugin")

        # Uninstall with --yes to skip confirmation
        result = runner.invoke(cli, ["plugin", "uninstall", "test_plugin", "--yes"])
        assert result.exit_code == 0
        assert "Plugin uninstalled" in result.output
        assert not plugin_file.exists()

    def test_plugin_uninstall_nonexistent(self, runner, tmp_path, monkeypatch):
        """Test uninstalling a plugin that doesn't exist."""
        # Set HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        # Create plugins directory but no plugin
        plugins_dir = tmp_path / ".bob" / "plugins"
        plugins_dir.mkdir(parents=True)

        result = runner.invoke(cli, ["plugin", "uninstall", "nonexistent", "--yes"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestPluginLoadUnloadCommands:
    """Test 'bob plugin load/unload' commands."""

    def test_plugin_load_help(self, runner):
        """Test plugin load help message."""
        result = runner.invoke(cli, ["plugin", "load", "--help"])
        assert result.exit_code == 0
        assert "Load a plugin" in result.output

    def test_plugin_unload_help(self, runner):
        """Test plugin unload help message."""
        result = runner.invoke(cli, ["plugin", "unload", "--help"])
        assert result.exit_code == 0
        assert "Unload a plugin" in result.output

    @patch('bob.cli.plugin.PluginRegistry')
    def test_plugin_load_success(self, mock_registry_class, runner):
        """Test successfully loading a plugin."""
        mock_registry = MagicMock()
        mock_registry.list_loaded.return_value = []
        mock_registry.load_plugin.return_value = True
        mock_registry_class.return_value = mock_registry

        result = runner.invoke(cli, ["plugin", "load", "test-plugin"])
        assert result.exit_code == 0
        assert "Plugin loaded" in result.output

    @patch('bob.cli.plugin.PluginRegistry')
    def test_plugin_load_failure(self, mock_registry_class, runner):
        """Test failed plugin load."""
        mock_registry = MagicMock()
        mock_registry.list_loaded.return_value = []
        mock_registry.load_plugin.return_value = False
        mock_registry_class.return_value = mock_registry

        result = runner.invoke(cli, ["plugin", "load", "bad-plugin"])
        assert result.exit_code != 0
        assert "Failed to load" in result.output

    @patch('bob.cli.plugin.PluginRegistry')
    def test_plugin_unload_success(self, mock_registry_class, runner):
        """Test successfully unloading a plugin."""
        mock_registry = MagicMock()
        mock_registry.list_loaded.return_value = ["test-plugin"]
        mock_registry.unload_plugin.return_value = True
        mock_registry_class.return_value = mock_registry

        result = runner.invoke(cli, ["plugin", "unload", "test-plugin"])
        assert result.exit_code == 0
        assert "Plugin unloaded" in result.output

    @patch('bob.cli.plugin.PluginRegistry')
    def test_plugin_unload_not_loaded(self, mock_registry_class, runner):
        """Test unloading a plugin that isn't loaded."""
        mock_registry = MagicMock()
        mock_registry.list_loaded.return_value = []
        mock_registry_class.return_value = mock_registry

        result = runner.invoke(cli, ["plugin", "unload", "test-plugin"])
        assert result.exit_code == 0
        assert "not loaded" in result.output


class TestPluginInfoCommand:
    """Test 'bob plugin info' command."""

    def test_plugin_info_help(self, runner):
        """Test plugin info help message."""
        result = runner.invoke(cli, ["plugin", "info", "--help"])
        assert result.exit_code == 0
        assert "Show detailed information" in result.output

    @patch('bob.cli.plugin.PluginRegistry')
    def test_plugin_info_success(self, mock_registry_class, runner):
        """Test showing plugin info."""
        mock_plugin = MagicMock()
        mock_plugin.name = "test-plugin"
        mock_plugin.version = "1.0.0"
        mock_plugin.plugin_type = "agent"
        mock_plugin.description = "Test plugin"
        mock_plugin.is_loaded = True

        mock_registry = MagicMock()
        mock_registry.get_plugin.return_value = mock_plugin
        mock_registry_class.return_value = mock_registry

        result = runner.invoke(cli, ["plugin", "info", "test-plugin"])
        assert result.exit_code == 0
        assert "test-plugin" in result.output
        assert "1.0.0" in result.output

    @patch('bob.cli.plugin.PluginRegistry')
    def test_plugin_info_json(self, mock_registry_class, runner):
        """Test plugin info with JSON output."""
        mock_plugin = MagicMock()
        mock_plugin.to_dict.return_value = {
            "name": "test-plugin",
            "version": "1.0.0",
            "type": "agent",
        }

        mock_registry = MagicMock()
        mock_registry.get_plugin.return_value = mock_plugin
        mock_registry_class.return_value = mock_registry

        result = runner.invoke(cli, ["plugin", "info", "test-plugin", "--json"])
        assert result.exit_code == 0

        # Verify JSON output
        data = json.loads(result.output)
        assert data["name"] == "test-plugin"

    @patch('bob.cli.plugin.PluginRegistry')
    def test_plugin_info_not_found(self, mock_registry_class, runner):
        """Test plugin info for nonexistent plugin."""
        mock_registry = MagicMock()
        mock_registry.get_plugin.return_value = None
        mock_registry.list_discovered.return_value = []
        mock_registry_class.return_value = mock_registry

        result = runner.invoke(cli, ["plugin", "info", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestPluginGroupHelp:
    """Test plugin command group help."""

    def test_plugin_group_help(self, runner):
        """Test main plugin group help."""
        result = runner.invoke(cli, ["plugin", "--help"])
        assert result.exit_code == 0
        assert "Manage plugins" in result.output
        assert "list" in result.output
        assert "install" in result.output
        assert "uninstall" in result.output
        assert "load" in result.output
        assert "unload" in result.output
        assert "info" in result.output
