"""Tests for spec source plugin system."""

import pytest
from datetime import datetime
from bob.spec_sources import (
    SpecSource,
    SpecSourceError,
    SpecSourceRegistry,
    SyncResult,
    TaskSpec,
    get_registry,
)


# Mock implementation for testing

class MockSpecSource(SpecSource):
    """Mock spec source for testing."""

    def __init__(self, source_uri: str, config: dict | None = None):
        super().__init__(source_uri, config)
        self._tasks: list[TaskSpec] = []
        self._version_counter = 0

    async def fetch_tasks(self) -> list[TaskSpec]:
        """Fetch all tasks."""
        return self._tasks.copy()

    async def sync(self, known_tasks: dict[str, int]) -> SyncResult:
        """Sync tasks."""
        result = SyncResult(spec_version=self._version_counter)

        # Determine added, modified, removed
        current_ids = {task.spec_id for task in self._tasks}
        known_ids = set(known_tasks.keys())

        # Added tasks (in current but not in known)
        added_ids = current_ids - known_ids
        result.added = [t for t in self._tasks if t.spec_id in added_ids]

        # Removed tasks (in known but not in current)
        result.removed = list(known_ids - current_ids)

        # Modified tasks (in both but version changed)
        for task in self._tasks:
            if task.spec_id in known_ids:
                if known_tasks[task.spec_id] != task.spec_version:
                    result.modified.append(task)

        self._last_sync = datetime.now()
        self._last_spec_version = self._version_counter
        return result

    async def mark_completed(self, spec_id: str, metadata: dict | None = None) -> bool:
        """Mark task as complete."""
        for task in self._tasks:
            if task.spec_id == spec_id:
                task.metadata["completed"] = True
                if metadata:
                    task.metadata.update(metadata)
                return True
        return False

    # Helper methods for testing
    def add_task(self, task: TaskSpec) -> None:
        """Add a task to the mock source."""
        self._tasks.append(task)
        self._version_counter += 1

    def remove_task(self, spec_id: str) -> None:
        """Remove a task from the mock source."""
        self._tasks = [t for t in self._tasks if t.spec_id != spec_id]
        self._version_counter += 1

    def update_task(self, spec_id: str, **updates) -> None:
        """Update a task in the mock source."""
        for task in self._tasks:
            if task.spec_id == spec_id:
                for key, value in updates.items():
                    setattr(task, key, value)
                task.spec_version += 1
                self._version_counter += 1
                break


class TestTaskSpec:
    """Tests for TaskSpec dataclass."""

    def test_task_spec_minimal(self):
        """Test creating a minimal TaskSpec."""
        spec = TaskSpec(spec_id="F001", title="Test Task", description="Test description")

        assert spec.spec_id == "F001"
        assert spec.title == "Test Task"
        assert spec.description == "Test description"
        assert spec.acceptance_criteria == []
        assert spec.steps == []
        assert spec.depends_on == []
        assert spec.priority == "medium"
        assert spec.category == "functional"
        assert spec.labels == []
        assert spec.research_required is False
        assert spec.research_queries == []
        assert spec.metadata == {}
        assert spec.spec_version == 1
        assert spec.deprecated is False

    def test_task_spec_with_all_fields(self):
        """Test creating a TaskSpec with all fields."""
        spec = TaskSpec(
            spec_id="F042",
            title="Implement Feature X",
            description="Add feature X to the system",
            acceptance_criteria=["Criterion 1", "Criterion 2"],
            steps=["Step 1", "Step 2", "Step 3"],
            depends_on=["F001", "F010"],
            priority="high",
            category="functional",
            labels=["frontend", "ui"],
            research_required=True,
            research_queries=["How to implement X?"],
            metadata={"source": "github", "issue_number": 42},
            spec_version=2,
            deprecated=False,
        )

        assert spec.spec_id == "F042"
        assert spec.title == "Implement Feature X"
        assert len(spec.acceptance_criteria) == 2
        assert len(spec.steps) == 3
        assert spec.depends_on == ["F001", "F010"]
        assert spec.priority == "high"
        assert spec.category == "functional"
        assert spec.labels == ["frontend", "ui"]
        assert spec.research_required is True
        assert len(spec.research_queries) == 1
        assert spec.metadata["issue_number"] == 42
        assert spec.spec_version == 2


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_sync_result_empty(self):
        """Test empty SyncResult."""
        result = SyncResult()

        assert result.added == []
        assert result.modified == []
        assert result.removed == []
        assert result.spec_version == 1
        assert result.errors == []
        assert result.has_changes is False
        assert result.total_changes == 0

    def test_sync_result_with_changes(self):
        """Test SyncResult with changes."""
        task1 = TaskSpec(spec_id="F001", title="Task 1", description="Desc 1")
        task2 = TaskSpec(spec_id="F002", title="Task 2", description="Desc 2")

        result = SyncResult(
            added=[task1],
            modified=[task2],
            removed=["F003"],
            spec_version=5,
        )

        assert len(result.added) == 1
        assert len(result.modified) == 1
        assert len(result.removed) == 1
        assert result.spec_version == 5
        assert result.has_changes is True
        assert result.total_changes == 3

    def test_sync_result_properties(self):
        """Test SyncResult computed properties."""
        result = SyncResult()
        assert result.has_changes is False
        assert result.total_changes == 0

        result.added = [TaskSpec(spec_id="F001", title="T1", description="D1")]
        assert result.has_changes is True
        assert result.total_changes == 1

        result.removed = ["F002", "F003"]
        assert result.total_changes == 3


class TestSpecSource:
    """Tests for SpecSource abstract base class."""

    @pytest.mark.asyncio
    async def test_spec_source_initialization(self):
        """Test SpecSource initialization."""
        source = MockSpecSource("mock://test", {"key": "value"})

        assert source.source_uri == "mock://test"
        assert source.config == {"key": "value"}
        assert source.last_sync is None
        assert source.last_spec_version == 0

    @pytest.mark.asyncio
    async def test_fetch_tasks(self):
        """Test fetching tasks."""
        source = MockSpecSource("mock://test")

        task1 = TaskSpec(spec_id="F001", title="Task 1", description="Desc 1")
        task2 = TaskSpec(spec_id="F002", title="Task 2", description="Desc 2")
        source.add_task(task1)
        source.add_task(task2)

        tasks = await source.fetch_tasks()
        assert len(tasks) == 2
        assert tasks[0].spec_id == "F001"
        assert tasks[1].spec_id == "F002"

    @pytest.mark.asyncio
    async def test_sync_added_tasks(self):
        """Test syncing with added tasks."""
        source = MockSpecSource("mock://test")

        # Initial sync with no known tasks
        task1 = TaskSpec(spec_id="F001", title="Task 1", description="Desc 1")
        source.add_task(task1)

        result = await source.sync({})

        assert len(result.added) == 1
        assert result.added[0].spec_id == "F001"
        assert len(result.modified) == 0
        assert len(result.removed) == 0
        assert result.has_changes is True
        assert source.last_sync is not None

    @pytest.mark.asyncio
    async def test_sync_removed_tasks(self):
        """Test syncing with removed tasks."""
        source = MockSpecSource("mock://test")

        task1 = TaskSpec(spec_id="F001", title="Task 1", description="Desc 1")
        source.add_task(task1)

        # First sync - task is known
        await source.sync({})

        # Remove task
        source.remove_task("F001")

        # Sync again with known task
        result = await source.sync({"F001": 1})

        assert len(result.added) == 0
        assert len(result.modified) == 0
        assert len(result.removed) == 1
        assert result.removed[0] == "F001"
        assert result.has_changes is True

    @pytest.mark.asyncio
    async def test_sync_modified_tasks(self):
        """Test syncing with modified tasks."""
        source = MockSpecSource("mock://test")

        task1 = TaskSpec(spec_id="F001", title="Task 1", description="Desc 1", spec_version=1)
        source.add_task(task1)

        # Update the task
        source.update_task("F001", title="Task 1 Updated")

        # Sync with old version
        result = await source.sync({"F001": 1})

        assert len(result.added) == 0
        assert len(result.modified) == 1
        assert result.modified[0].spec_id == "F001"
        assert result.modified[0].title == "Task 1 Updated"
        assert len(result.removed) == 0
        assert result.has_changes is True

    @pytest.mark.asyncio
    async def test_sync_no_changes(self):
        """Test syncing with no changes."""
        source = MockSpecSource("mock://test")

        task1 = TaskSpec(spec_id="F001", title="Task 1", description="Desc 1", spec_version=1)
        source.add_task(task1)

        # Sync with same version
        result = await source.sync({"F001": 1})

        assert len(result.added) == 0
        assert len(result.modified) == 0
        assert len(result.removed) == 0
        assert result.has_changes is False

    @pytest.mark.asyncio
    async def test_mark_completed(self):
        """Test marking a task as completed."""
        source = MockSpecSource("mock://test")

        task1 = TaskSpec(spec_id="F001", title="Task 1", description="Desc 1")
        source.add_task(task1)

        success = await source.mark_completed("F001", {"pr": "https://github.com/org/repo/pull/123"})

        assert success is True
        tasks = await source.fetch_tasks()
        assert tasks[0].metadata["completed"] is True
        assert tasks[0].metadata["pr"] == "https://github.com/org/repo/pull/123"

    @pytest.mark.asyncio
    async def test_mark_completed_not_found(self):
        """Test marking a non-existent task as completed."""
        source = MockSpecSource("mock://test")

        success = await source.mark_completed("F999")
        assert success is False

    @pytest.mark.asyncio
    async def test_spec_source_str(self):
        """Test string representation."""
        source = MockSpecSource("mock://test")
        assert str(source) == "MockSpecSource(mock://test)"


class TestSpecSourceRegistry:
    """Tests for SpecSourceRegistry."""

    def test_registry_initialization(self):
        """Test registry initialization."""
        registry = SpecSourceRegistry()
        assert registry.list_schemes() == []

    def test_register_source(self):
        """Test registering a spec source."""
        registry = SpecSourceRegistry()
        registry.register("mock", MockSpecSource)

        assert "mock" in registry.list_schemes()
        assert registry.is_registered("mock") is True
        assert registry.get("mock") == MockSpecSource

    def test_register_duplicate_scheme(self):
        """Test registering duplicate scheme raises error."""
        registry = SpecSourceRegistry()
        registry.register("mock", MockSpecSource)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("mock", MockSpecSource)

    def test_register_invalid_class(self):
        """Test registering non-SpecSource class raises error."""
        registry = SpecSourceRegistry()

        class NotASpecSource:
            pass

        with pytest.raises(ValueError, match="must be a subclass"):
            registry.register("invalid", NotASpecSource)

    def test_unregister_source(self):
        """Test unregistering a spec source."""
        registry = SpecSourceRegistry()
        registry.register("mock", MockSpecSource)

        assert registry.is_registered("mock") is True

        registry.unregister("mock")

        assert registry.is_registered("mock") is False
        assert "mock" not in registry.list_schemes()

    def test_get_source(self):
        """Test getting a spec source class."""
        registry = SpecSourceRegistry()
        registry.register("mock", MockSpecSource)

        source_class = registry.get("mock")
        assert source_class == MockSpecSource

    def test_get_nonexistent_source(self):
        """Test getting a non-existent source returns None."""
        registry = SpecSourceRegistry()
        assert registry.get("nonexistent") is None

    def test_create_source(self):
        """Test creating a spec source instance."""
        registry = SpecSourceRegistry()
        registry.register("mock", MockSpecSource)

        source = registry.create("mock://test", {"key": "value"})

        assert isinstance(source, MockSpecSource)
        assert source.source_uri == "mock://test"
        assert source.config == {"key": "value"}

    def test_create_source_invalid_uri(self):
        """Test creating source with invalid URI."""
        registry = SpecSourceRegistry()

        with pytest.raises(ValueError, match="must contain"):
            registry.create("invalid-uri")

    def test_create_source_unregistered_scheme(self):
        """Test creating source with unregistered scheme."""
        registry = SpecSourceRegistry()

        with pytest.raises(ValueError, match="No spec source registered"):
            registry.create("unknown://test")

    def test_list_schemes(self):
        """Test listing schemes."""
        registry = SpecSourceRegistry()
        registry.register("mock", MockSpecSource)
        registry.register("test", MockSpecSource)

        schemes = registry.list_schemes()
        assert schemes == ["mock", "test"]  # Should be sorted

    def test_is_registered(self):
        """Test checking if scheme is registered."""
        registry = SpecSourceRegistry()

        assert registry.is_registered("mock") is False

        registry.register("mock", MockSpecSource)

        assert registry.is_registered("mock") is True


class TestGlobalRegistry:
    """Tests for global registry."""

    def test_get_registry(self):
        """Test getting global registry."""
        registry1 = get_registry()
        registry2 = get_registry()

        # Should return same instance
        assert registry1 is registry2

    def test_global_registry_isolation(self):
        """Test that global registry changes persist."""
        registry = get_registry()

        # Clear any existing registrations for this test
        if registry.is_registered("test_global"):
            registry.unregister("test_global")

        registry.register("test_global", MockSpecSource)

        # Get registry again
        registry2 = get_registry()
        assert registry2.is_registered("test_global") is True

        # Clean up
        registry.unregister("test_global")
