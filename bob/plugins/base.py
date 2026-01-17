"""Base classes for BOB plugin system.

This module defines the plugin architecture for extending BOB with custom
agents, spec sources, and tools.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

# Plugin type constants
PLUGIN_TYPE_AGENT = "agent"
PLUGIN_TYPE_SPEC_SOURCE = "spec_source"
PLUGIN_TYPE_TOOL = "tool"


class Plugin(ABC):
    """Base class for all BOB plugins.

    Plugins extend BOB functionality by providing custom agents, spec sources,
    or tools. Each plugin must implement on_load() and on_unload() methods.

    Attributes:
        name: Unique identifier for the plugin
        version: Plugin version string
        description: Human-readable description
        plugin_type: Type of plugin (agent, spec_source, tool)
    """

    def __init__(
        self,
        name: str,
        version: str,
        description: str,
        plugin_type: str,
    ) -> None:
        """Initialize plugin.

        Args:
            name: Unique plugin identifier
            version: Version string (e.g., "1.0.0")
            description: Human-readable description
            plugin_type: One of PLUGIN_TYPE_* constants
        """
        self.name = name
        self.version = version
        self.description = description
        self.plugin_type = plugin_type
        self._loaded = False

    @abstractmethod
    def on_load(self) -> None:
        """Called when plugin is loaded.

        Use this method to:
        - Initialize resources
        - Register handlers
        - Validate configuration

        Raises:
            Exception: If plugin fails to load
        """
        pass

    @abstractmethod
    def on_unload(self) -> None:
        """Called when plugin is unloaded.

        Use this method to:
        - Clean up resources
        - Save state
        - Unregister handlers
        """
        pass

    @property
    def is_loaded(self) -> bool:
        """Check if plugin is currently loaded."""
        return self._loaded

    def to_dict(self) -> Dict[str, Any]:
        """Convert plugin metadata to dictionary.

        Returns:
            Dictionary with plugin metadata
        """
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "type": self.plugin_type,
            "loaded": self._loaded,
        }


class AgentPlugin(Plugin):
    """Plugin that provides a custom agent implementation.

    Agent plugins extend BOB with new agent types (e.g., specialized
    agents for debugging, optimization, documentation).

    Example:
        class MyDebugAgent(AgentPlugin):
            def __init__(self):
                super().__init__(
                    name="debug-agent",
                    version="1.0.0",
                    description="Agent specialized for debugging",
                    plugin_type=PLUGIN_TYPE_AGENT
                )

            def on_load(self):
                # Register agent with orchestrator
                pass

            def on_unload(self):
                # Cleanup
                pass

            def run(self, task, context):
                # Agent logic
                pass
    """

    def __init__(
        self,
        name: str,
        version: str,
        description: str,
    ) -> None:
        """Initialize agent plugin.

        Args:
            name: Unique agent name
            version: Version string
            description: Agent description
        """
        super().__init__(
            name=name,
            version=version,
            description=description,
            plugin_type=PLUGIN_TYPE_AGENT,
        )

    @abstractmethod
    def run(self, task: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute agent on a task.

        Args:
            task: Task dictionary with id, description, etc.
            context: Execution context with project info, config, etc.

        Returns:
            Result dictionary with status, output, etc.
        """
        pass


class SpecSourcePlugin(Plugin):
    """Plugin that provides a custom specification source.

    Spec source plugins allow BOB to read task specifications from
    custom sources (e.g., Notion, Asana, custom issue trackers).

    Example:
        class NotionSpecSource(SpecSourcePlugin):
            def __init__(self):
                super().__init__(
                    name="notion",
                    version="1.0.0",
                    description="Read specs from Notion databases"
                )

            def on_load(self):
                # Initialize Notion API client
                pass

            def on_unload(self):
                # Cleanup
                pass

            def fetch_tasks(self, source_uri):
                # Fetch tasks from Notion
                pass
    """

    def __init__(
        self,
        name: str,
        version: str,
        description: str,
    ) -> None:
        """Initialize spec source plugin.

        Args:
            name: Unique source name
            version: Version string
            description: Source description
        """
        super().__init__(
            name=name,
            version=version,
            description=description,
            plugin_type=PLUGIN_TYPE_SPEC_SOURCE,
        )

    @abstractmethod
    def fetch_tasks(self, source_uri: str) -> List[Dict[str, Any]]:
        """Fetch tasks from the spec source.

        Args:
            source_uri: URI identifying the spec source (e.g., "notion://database/abc123")

        Returns:
            List of task dictionaries
        """
        pass

    @abstractmethod
    def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Update a task in the spec source.

        Args:
            task_id: Task identifier
            updates: Dictionary of fields to update

        Returns:
            True if update succeeded, False otherwise
        """
        pass


class ToolPlugin(Plugin):
    """Plugin that provides custom tools for agents.

    Tool plugins extend the agent's capabilities with new tools
    (e.g., custom API clients, specialized analysis tools).

    Example:
        class DatabaseToolPlugin(ToolPlugin):
            def __init__(self):
                super().__init__(
                    name="database-tools",
                    version="1.0.0",
                    description="SQL database query tools"
                )

            def on_load(self):
                # Initialize database connections
                pass

            def on_unload(self):
                # Close connections
                pass

            def get_tools(self):
                return [
                    {
                        "name": "query_database",
                        "description": "Execute SQL query",
                        "function": self.query_database
                    }
                ]
    """

    def __init__(
        self,
        name: str,
        version: str,
        description: str,
    ) -> None:
        """Initialize tool plugin.

        Args:
            name: Unique tool plugin name
            version: Version string
            description: Plugin description
        """
        super().__init__(
            name=name,
            version=version,
            description=description,
            plugin_type=PLUGIN_TYPE_TOOL,
        )

    @abstractmethod
    def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of tools provided by this plugin.

        Returns:
            List of tool definitions, each with:
                - name: Tool name
                - description: Tool description
                - function: Callable tool function
        """
        pass


class PluginRegistry:
    """Registry for managing BOB plugins.

    The registry handles plugin discovery, loading, and lifecycle management.
    Plugins are discovered from ~/.bob/plugins/ directory.

    Example:
        registry = PluginRegistry()
        registry.discover_plugins()
        registry.load_plugin("my-plugin")

        # Get loaded plugins
        agents = registry.get_plugins_by_type(PLUGIN_TYPE_AGENT)

        # Unload plugin
        registry.unload_plugin("my-plugin")
    """

    def __init__(self, plugin_dir: Optional[Path] = None) -> None:
        """Initialize plugin registry.

        Args:
            plugin_dir: Directory to search for plugins
                       (default: ~/.bob/plugins/)
        """
        if plugin_dir is None:
            plugin_dir = Path.home() / ".bob" / "plugins"

        self.plugin_dir = Path(plugin_dir)
        self._plugins: Dict[str, Plugin] = {}
        self._discovered: Dict[str, Type[Plugin]] = {}

    def discover_plugins(self) -> List[str]:
        """Discover available plugins in plugin directory.

        Scans the plugin directory for Python modules that define Plugin
        subclasses. Does not load the plugins.

        Returns:
            List of discovered plugin names
        """
        discovered = []

        if not self.plugin_dir.exists():
            return discovered

        # For now, return empty list since we need to implement
        # dynamic module loading. This will be enhanced in future.
        return discovered

    def register_plugin(self, plugin_class: Type[Plugin]) -> None:
        """Register a plugin class for later loading.

        Args:
            plugin_class: Plugin class (not instance)
        """
        # Instantiate plugin to get metadata
        instance = plugin_class()
        self._discovered[instance.name] = plugin_class

    def load_plugin(self, plugin_name: str) -> bool:
        """Load a plugin by name.

        Args:
            plugin_name: Name of plugin to load

        Returns:
            True if loaded successfully, False otherwise
        """
        if plugin_name in self._plugins:
            # Already loaded
            return True

        if plugin_name not in self._discovered:
            return False

        try:
            plugin_class = self._discovered[plugin_name]
            plugin = plugin_class()
            plugin.on_load()
            plugin._loaded = True
            self._plugins[plugin_name] = plugin
            return True
        except Exception:
            return False

    def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin by name.

        Args:
            plugin_name: Name of plugin to unload

        Returns:
            True if unloaded successfully, False otherwise
        """
        if plugin_name not in self._plugins:
            return False

        try:
            plugin = self._plugins[plugin_name]
            plugin.on_unload()
            plugin._loaded = False
            del self._plugins[plugin_name]
            return True
        except Exception:
            return False

    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """Get a loaded plugin by name.

        Args:
            plugin_name: Name of plugin

        Returns:
            Plugin instance or None if not loaded
        """
        return self._plugins.get(plugin_name)

    def get_all_plugins(self) -> List[Plugin]:
        """Get all loaded plugins.

        Returns:
            List of loaded plugin instances
        """
        return list(self._plugins.values())

    def get_plugins_by_type(self, plugin_type: str) -> List[Plugin]:
        """Get all loaded plugins of a specific type.

        Args:
            plugin_type: Plugin type (PLUGIN_TYPE_*)

        Returns:
            List of plugins matching the type
        """
        return [
            p for p in self._plugins.values()
            if p.plugin_type == plugin_type
        ]

    def list_discovered(self) -> List[str]:
        """List all discovered plugin names.

        Returns:
            List of plugin names that can be loaded
        """
        return list(self._discovered.keys())

    def list_loaded(self) -> List[str]:
        """List all loaded plugin names.

        Returns:
            List of currently loaded plugin names
        """
        return list(self._plugins.keys())
