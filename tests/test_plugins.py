"""Tests for plugin system."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bob.plugins.base import (
    PLUGIN_TYPE_AGENT,
    PLUGIN_TYPE_SPEC_SOURCE,
    PLUGIN_TYPE_TOOL,
    AgentPlugin,
    Plugin,
    PluginRegistry,
    SpecSourcePlugin,
    ToolPlugin,
)


# Mock plugin implementations for testing


class MockPlugin(Plugin):
    """Mock plugin for testing base class."""

    def __init__(self):
        super().__init__(
            name="mock-plugin",
            version="1.0.0",
            description="Mock plugin for testing",
            plugin_type="mock",
        )
        self.on_load_called = False
        self.on_unload_called = False

    def on_load(self):
        self.on_load_called = True

    def on_unload(self):
        self.on_unload_called = True


class MockAgentPlugin(AgentPlugin):
    """Mock agent plugin for testing."""

    def __init__(self):
        super().__init__(
            name="mock-agent",
            version="1.0.0",
            description="Mock agent for testing",
        )
        self.run_called = False

    def on_load(self):
        pass

    def on_unload(self):
        pass

    def run(self, task, context):
        self.run_called = True
        return {"status": "success"}


class MockSpecSourcePlugin(SpecSourcePlugin):
    """Mock spec source plugin for testing."""

    def __init__(self):
        super().__init__(
            name="mock-source",
            version="1.0.0",
            description="Mock spec source for testing",
        )

    def on_load(self):
        pass

    def on_unload(self):
        pass

    def fetch_tasks(self, source_uri):
        return [
            {"id": "1", "title": "Task 1"},
            {"id": "2", "title": "Task 2"},
        ]

    def update_task(self, task_id, updates):
        return True


class MockToolPlugin(ToolPlugin):
    """Mock tool plugin for testing."""

    def __init__(self):
        super().__init__(
            name="mock-tools",
            version="1.0.0",
            description="Mock tools for testing",
        )

    def on_load(self):
        pass

    def on_unload(self):
        pass

    def get_tools(self):
        return [
            {
                "name": "test_tool",
                "description": "A test tool",
                "function": lambda: "tool result",
            }
        ]


# Fixtures


@pytest.fixture
def plugin_dir(tmp_path):
    """Create temporary plugin directory."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    return plugin_dir


@pytest.fixture
def registry(plugin_dir):
    """Create plugin registry with temp directory."""
    return PluginRegistry(plugin_dir)


# Tests for Plugin base class


class TestPluginBase:
    """Test Plugin base class."""

    def test_plugin_initialization(self):
        """Test plugin initialization."""
        plugin = MockPlugin()
        assert plugin.name == "mock-plugin"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Mock plugin for testing"
        assert plugin.plugin_type == "mock"
        assert not plugin.is_loaded

    def test_on_load_called(self):
        """Test on_load is called."""
        plugin = MockPlugin()
        assert not plugin.on_load_called
        plugin.on_load()
        assert plugin.on_load_called

    def test_on_unload_called(self):
        """Test on_unload is called."""
        plugin = MockPlugin()
        assert not plugin.on_unload_called
        plugin.on_unload()
        assert plugin.on_unload_called

    def test_to_dict(self):
        """Test plugin serialization."""
        plugin = MockPlugin()
        data = plugin.to_dict()

        assert data["name"] == "mock-plugin"
        assert data["version"] == "1.0.0"
        assert data["description"] == "Mock plugin for testing"
        assert data["type"] == "mock"
        assert data["loaded"] is False


# Tests for AgentPlugin


class TestAgentPlugin:
    """Test AgentPlugin class."""

    def test_agent_plugin_initialization(self):
        """Test agent plugin initialization."""
        plugin = MockAgentPlugin()
        assert plugin.name == "mock-agent"
        assert plugin.plugin_type == PLUGIN_TYPE_AGENT
        assert not plugin.is_loaded

    def test_agent_run_method(self):
        """Test agent run method."""
        plugin = MockAgentPlugin()
        assert not plugin.run_called

        result = plugin.run({"id": "task1"}, {})
        assert plugin.run_called
        assert result["status"] == "success"


# Tests for SpecSourcePlugin


class TestSpecSourcePlugin:
    """Test SpecSourcePlugin class."""

    def test_spec_source_initialization(self):
        """Test spec source plugin initialization."""
        plugin = MockSpecSourcePlugin()
        assert plugin.name == "mock-source"
        assert plugin.plugin_type == PLUGIN_TYPE_SPEC_SOURCE
        assert not plugin.is_loaded

    def test_fetch_tasks(self):
        """Test fetching tasks from spec source."""
        plugin = MockSpecSourcePlugin()
        tasks = plugin.fetch_tasks("mock://source")

        assert len(tasks) == 2
        assert tasks[0]["id"] == "1"
        assert tasks[1]["title"] == "Task 2"

    def test_update_task(self):
        """Test updating task in spec source."""
        plugin = MockSpecSourcePlugin()
        result = plugin.update_task("task1", {"status": "completed"})
        assert result is True


# Tests for ToolPlugin


class TestToolPlugin:
    """Test ToolPlugin class."""

    def test_tool_plugin_initialization(self):
        """Test tool plugin initialization."""
        plugin = MockToolPlugin()
        assert plugin.name == "mock-tools"
        assert plugin.plugin_type == PLUGIN_TYPE_TOOL
        assert not plugin.is_loaded

    def test_get_tools(self):
        """Test getting tools from plugin."""
        plugin = MockToolPlugin()
        tools = plugin.get_tools()

        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"
        assert tools[0]["description"] == "A test tool"
        assert callable(tools[0]["function"])
        assert tools[0]["function"]() == "tool result"


# Tests for PluginRegistry


class TestPluginRegistry:
    """Test PluginRegistry class."""

    def test_registry_initialization(self, plugin_dir):
        """Test registry initialization."""
        registry = PluginRegistry(plugin_dir)
        assert registry.plugin_dir == plugin_dir

    def test_registry_default_dir(self):
        """Test registry uses default ~/.bob/plugins directory."""
        registry = PluginRegistry()
        expected = Path.home() / ".bob" / "plugins"
        assert registry.plugin_dir == expected

    def test_register_plugin(self, registry):
        """Test registering a plugin class."""
        registry.register_plugin(MockPlugin)
        discovered = registry.list_discovered()
        assert "mock-plugin" in discovered

    def test_load_plugin(self, registry):
        """Test loading a registered plugin."""
        registry.register_plugin(MockPlugin)

        # Plugin not loaded yet
        assert registry.get_plugin("mock-plugin") is None
        assert registry.list_loaded() == []

        # Load plugin
        result = registry.load_plugin("mock-plugin")
        assert result is True

        # Plugin now loaded
        plugin = registry.get_plugin("mock-plugin")
        assert plugin is not None
        assert plugin.is_loaded
        assert plugin.on_load_called
        assert "mock-plugin" in registry.list_loaded()

    def test_load_nonexistent_plugin(self, registry):
        """Test loading a plugin that doesn't exist."""
        result = registry.load_plugin("nonexistent")
        assert result is False

    def test_load_already_loaded_plugin(self, registry):
        """Test loading a plugin that's already loaded."""
        registry.register_plugin(MockPlugin)
        registry.load_plugin("mock-plugin")

        # Load again - should succeed (idempotent)
        result = registry.load_plugin("mock-plugin")
        assert result is True

    def test_unload_plugin(self, registry):
        """Test unloading a plugin."""
        registry.register_plugin(MockPlugin)
        registry.load_plugin("mock-plugin")

        # Plugin is loaded
        plugin = registry.get_plugin("mock-plugin")
        assert plugin.is_loaded

        # Unload plugin
        result = registry.unload_plugin("mock-plugin")
        assert result is True

        # Plugin is unloaded
        assert plugin.on_unload_called
        assert not plugin.is_loaded
        assert registry.get_plugin("mock-plugin") is None

    def test_unload_nonexistent_plugin(self, registry):
        """Test unloading a plugin that isn't loaded."""
        result = registry.unload_plugin("nonexistent")
        assert result is False

    def test_get_all_plugins(self, registry):
        """Test getting all loaded plugins."""
        registry.register_plugin(MockPlugin)
        registry.register_plugin(MockAgentPlugin)

        # No plugins loaded yet
        assert len(registry.get_all_plugins()) == 0

        # Load plugins
        registry.load_plugin("mock-plugin")
        registry.load_plugin("mock-agent")

        # Get all plugins
        plugins = registry.get_all_plugins()
        assert len(plugins) == 2
        assert any(p.name == "mock-plugin" for p in plugins)
        assert any(p.name == "mock-agent" for p in plugins)

    def test_get_plugins_by_type(self, registry):
        """Test filtering plugins by type."""
        registry.register_plugin(MockAgentPlugin)
        registry.register_plugin(MockSpecSourcePlugin)
        registry.register_plugin(MockToolPlugin)

        # Load all plugins
        registry.load_plugin("mock-agent")
        registry.load_plugin("mock-source")
        registry.load_plugin("mock-tools")

        # Get agent plugins
        agents = registry.get_plugins_by_type(PLUGIN_TYPE_AGENT)
        assert len(agents) == 1
        assert agents[0].name == "mock-agent"

        # Get spec source plugins
        sources = registry.get_plugins_by_type(PLUGIN_TYPE_SPEC_SOURCE)
        assert len(sources) == 1
        assert sources[0].name == "mock-source"

        # Get tool plugins
        tools = registry.get_plugins_by_type(PLUGIN_TYPE_TOOL)
        assert len(tools) == 1
        assert tools[0].name == "mock-tools"

    def test_discover_plugins_empty_directory(self, registry):
        """Test discovering plugins from empty directory."""
        # Create plugin directory
        registry.plugin_dir.mkdir(parents=True, exist_ok=True)

        # No plugins to discover
        discovered = registry.discover_plugins()
        assert discovered == []

    def test_discover_plugins_nonexistent_directory(self, registry):
        """Test discovering plugins when directory doesn't exist."""
        # Ensure directory doesn't exist
        if registry.plugin_dir.exists():
            registry.plugin_dir.rmdir()

        discovered = registry.discover_plugins()
        assert discovered == []


class TestPluginLifecycle:
    """Test complete plugin lifecycle."""

    def test_full_lifecycle(self, registry):
        """Test full plugin lifecycle: register, load, use, unload."""
        # Register plugin
        registry.register_plugin(MockAgentPlugin)
        assert "mock-agent" in registry.list_discovered()

        # Load plugin
        result = registry.load_plugin("mock-agent")
        assert result is True
        plugin = registry.get_plugin("mock-agent")
        assert plugin.is_loaded

        # Use plugin
        result = plugin.run({"id": "task1"}, {})
        assert result["status"] == "success"

        # Unload plugin
        result = registry.unload_plugin("mock-agent")
        assert result is True
        assert not plugin.is_loaded

    def test_multiple_plugin_types(self, registry):
        """Test loading multiple types of plugins simultaneously."""
        # Register plugins
        registry.register_plugin(MockAgentPlugin)
        registry.register_plugin(MockSpecSourcePlugin)
        registry.register_plugin(MockToolPlugin)

        # Load all
        registry.load_plugin("mock-agent")
        registry.load_plugin("mock-source")
        registry.load_plugin("mock-tools")

        # Verify all loaded
        assert len(registry.get_all_plugins()) == 3
        assert len(registry.get_plugins_by_type(PLUGIN_TYPE_AGENT)) == 1
        assert len(registry.get_plugins_by_type(PLUGIN_TYPE_SPEC_SOURCE)) == 1
        assert len(registry.get_plugins_by_type(PLUGIN_TYPE_TOOL)) == 1


class TestPluginMetadata:
    """Test plugin metadata handling."""

    def test_plugin_versioning(self):
        """Test plugin version information."""
        plugin = MockPlugin()
        assert plugin.version == "1.0.0"

        data = plugin.to_dict()
        assert data["version"] == "1.0.0"

    def test_plugin_description(self):
        """Test plugin description."""
        plugin = MockPlugin()
        assert "Mock plugin" in plugin.description

        data = plugin.to_dict()
        assert "Mock plugin" in data["description"]

    def test_plugin_type_constants(self):
        """Test plugin type constants are defined."""
        assert PLUGIN_TYPE_AGENT == "agent"
        assert PLUGIN_TYPE_SPEC_SOURCE == "spec_source"
        assert PLUGIN_TYPE_TOOL == "tool"
