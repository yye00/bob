"""Base classes and interfaces for spec source plugins.

This module defines the pluggable architecture for spec sources. BOB can
pull task specifications from various sources (files, GitHub issues, Jira,
Linear, etc.) by implementing the SpecSource abstract base class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class TaskSpec:
    """Specification for a task from a spec source.

    This is the spec-level representation of a task, before it's converted
    to a Task model in the database. It contains all information needed to
    create or update a task.
    """
    spec_id: str  # Unique ID in the spec (e.g., "F001", issue number, etc.)
    title: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)  # spec_ids of dependencies
    priority: str = "medium"  # critical, high, medium, low
    category: str = "functional"  # functional, non-functional, infrastructure
    labels: list[str] = field(default_factory=list)
    research_required: bool = False
    research_queries: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)  # Source-specific metadata
    spec_version: int = 1  # Version of the spec when this task was added/updated
    deprecated: bool = False  # If true, task is no longer active


@dataclass
class SyncResult:
    """Result of syncing tasks from a spec source.

    Contains lists of tasks that were added, modified, or removed during
    a sync operation. This allows the caller to react appropriately
    (e.g., create new tasks, update existing ones, mark removed as deprecated).
    """
    added: list[TaskSpec] = field(default_factory=list)
    modified: list[TaskSpec] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)  # spec_ids of removed tasks
    spec_version: int = 1  # Current version of the spec
    synced_at: datetime = field(default_factory=datetime.now)
    errors: list[str] = field(default_factory=list)  # Any errors during sync

    @property
    def has_changes(self) -> bool:
        """Returns True if there were any changes detected."""
        return bool(self.added or self.modified or self.removed)

    @property
    def total_changes(self) -> int:
        """Returns total number of changes."""
        return len(self.added) + len(self.modified) + len(self.removed)


class SpecSource(ABC):
    """Abstract base class for spec source plugins.

    A spec source is responsible for:
    1. Fetching task specifications from an external source
    2. Detecting changes to the spec over time (sync)
    3. Optionally reporting task completion back to the source

    Each spec source implementation handles a different type of source:
    - FileSpecSource: Local YAML/JSON files
    - GitHubIssuesSource: GitHub Issues
    - JiraSource: Jira tickets
    - LinearSource: Linear issues
    - etc.
    """

    def __init__(self, source_uri: str, config: Optional[dict[str, Any]] = None):
        """Initialize the spec source.

        Args:
            source_uri: URI identifying the spec source
                       (e.g., "file://spec.yaml", "github://org/repo/issues")
            config: Optional configuration dict for the source
        """
        self.source_uri = source_uri
        self.config = config or {}
        self._last_sync: Optional[datetime] = None
        self._last_spec_version: int = 0

    @abstractmethod
    async def fetch_tasks(self) -> list[TaskSpec]:
        """Fetch all current tasks from the spec source.

        This method should return the complete current state of tasks
        in the spec source. It's used for initial setup and full refreshes.

        Returns:
            List of TaskSpec objects representing all tasks in the source.

        Raises:
            SpecSourceError: If there's an error fetching tasks.
        """
        pass

    @abstractmethod
    async def sync(self, known_tasks: dict[str, int]) -> SyncResult:
        """Sync tasks with the spec source, detecting changes.

        This method compares the current state of the spec source with
        the known tasks (provided as spec_id -> task version mapping)
        and returns what has changed.

        Args:
            known_tasks: Dict mapping spec_id to task version/hash.
                        Used to detect which tasks have been modified.

        Returns:
            SyncResult containing lists of added, modified, and removed tasks.

        Raises:
            SpecSourceError: If there's an error during sync.
        """
        pass

    @abstractmethod
    async def mark_completed(self, spec_id: str, metadata: Optional[dict[str, Any]] = None) -> bool:
        """Mark a task as completed in the spec source (if supported).

        Some spec sources support marking tasks as complete (e.g., closing
        GitHub issues, updating Jira status). This method provides a way
        to report completion back to the source.

        Args:
            spec_id: The spec_id of the task to mark complete.
            metadata: Optional metadata about the completion (e.g., PR link).

        Returns:
            True if the task was successfully marked complete, False otherwise.

        Note:
            This method is optional. Implementations that don't support
            completion tracking should return False.
        """
        pass

    @property
    def last_sync(self) -> Optional[datetime]:
        """Returns the timestamp of the last successful sync."""
        return self._last_sync

    @property
    def last_spec_version(self) -> int:
        """Returns the spec version from the last sync."""
        return self._last_spec_version

    def __str__(self) -> str:
        """String representation of the spec source."""
        return f"{self.__class__.__name__}({self.source_uri})"


class SpecSourceError(Exception):
    """Base exception for spec source errors."""
    pass


class SpecSourceRegistry:
    """Registry for spec source plugins.

    This registry allows different spec source implementations to be
    registered and instantiated by URI scheme.

    Example:
        registry = SpecSourceRegistry()
        registry.register("file", FileSpecSource)
        registry.register("github", GitHubIssuesSource)

        source = registry.create("file://spec.yaml")
    """

    def __init__(self):
        """Initialize empty registry."""
        self._sources: dict[str, type[SpecSource]] = {}

    def register(self, scheme: str, source_class: type[SpecSource]) -> None:
        """Register a spec source class for a URI scheme.

        Args:
            scheme: URI scheme (e.g., "file", "github", "jira")
            source_class: Class that implements SpecSource

        Raises:
            ValueError: If scheme is already registered or source_class
                       is not a subclass of SpecSource.
        """
        if scheme in self._sources:
            raise ValueError(f"Scheme '{scheme}' is already registered")

        if not issubclass(source_class, SpecSource):
            raise ValueError(
                f"{source_class.__name__} must be a subclass of SpecSource"
            )

        self._sources[scheme] = source_class

    def unregister(self, scheme: str) -> None:
        """Unregister a spec source scheme.

        Args:
            scheme: URI scheme to unregister
        """
        self._sources.pop(scheme, None)

    def get(self, scheme: str) -> Optional[type[SpecSource]]:
        """Get the spec source class for a scheme.

        Args:
            scheme: URI scheme (e.g., "file", "github")

        Returns:
            The SpecSource class registered for this scheme, or None.
        """
        return self._sources.get(scheme)

    def create(
        self,
        source_uri: str,
        config: Optional[dict[str, Any]] = None
    ) -> SpecSource:
        """Create a spec source instance from a URI.

        Args:
            source_uri: Full URI (e.g., "file://spec.yaml")
            config: Optional config dict to pass to the source

        Returns:
            Instantiated spec source.

        Raises:
            ValueError: If the URI scheme is not registered or URI is invalid.
        """
        if "://" not in source_uri:
            raise ValueError(
                f"Invalid source URI '{source_uri}': must contain '://'"
            )

        scheme, _ = source_uri.split("://", 1)

        source_class = self.get(scheme)
        if source_class is None:
            raise ValueError(
                f"No spec source registered for scheme '{scheme}'. "
                f"Available schemes: {', '.join(self.list_schemes())}"
            )

        return source_class(source_uri, config)

    def list_schemes(self) -> list[str]:
        """List all registered URI schemes.

        Returns:
            Sorted list of registered scheme names.
        """
        return sorted(self._sources.keys())

    def is_registered(self, scheme: str) -> bool:
        """Check if a scheme is registered.

        Args:
            scheme: URI scheme to check

        Returns:
            True if the scheme is registered, False otherwise.
        """
        return scheme in self._sources


# Global registry instance
_global_registry = SpecSourceRegistry()


def get_registry() -> SpecSourceRegistry:
    """Get the global spec source registry.

    Returns:
        The global SpecSourceRegistry instance.
    """
    return _global_registry
