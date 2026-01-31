"""Tests for TaskDecomposer."""

import pytest
from bob.orchestrator.task_decomposer import (
    TaskDecomposer,
    SubTask,
    DecompositionResult,
    generate_decomposition_prompt,
    analyze_task_for_decomposition,
    validate_decomposition,
    suggest_decomposition,
)
from bob.models.base import Task, TaskStatus, Project
from bob.database.manager import DatabaseManager


@pytest.fixture
def sample_project(tmp_path):
    """Create a sample project with database."""
    db_path = tmp_path / "test.db"
    db_manager = DatabaseManager(str(db_path))

    # Create project
    project = Project(
        id="proj-test",
        name="test-project",
        description="Test project",
        workspace_dir=str(tmp_path),
        spec_source="file://spec.yaml",
    )
    db_manager.create_project(project)

    return project, db_manager


class TestSubTask:
    """Test SubTask dataclass."""

    def test_subtask_creation(self):
        """Test creating a SubTask."""
        subtask = SubTask(
            spec_id="F042",
            title="Sub-task title",
            description="Sub-task description",
            steps=["Step 1", "Step 2"],
            depends_on=["F041"],
            parent_spec_id="F040",
            priority="high",
            category="functional",
        )

        assert subtask.spec_id == "F042"
        assert subtask.title == "Sub-task title"
        assert subtask.description == "Sub-task description"
        assert subtask.steps == ["Step 1", "Step 2"]
        assert subtask.depends_on == ["F041"]
        assert subtask.parent_spec_id == "F040"
        assert subtask.priority == "high"
        assert subtask.category == "functional"
        assert subtask.created_from_decomposition is True

    def test_subtask_to_dict(self):
        """Test SubTask.to_dict()."""
        subtask = SubTask(
            spec_id="F042",
            title="Sub-task title",
            description="Sub-task description",
            steps=["Step 1"],
            depends_on=[],
            parent_spec_id="F040",
        )

        result = subtask.to_dict()
        assert result["spec_id"] == "F042"
        assert result["title"] == "Sub-task title"
        assert result["description"] == "Sub-task description"
        assert result["steps"] == ["Step 1"]
        assert result["depends_on"] == []
        assert result["parent_spec_id"] == "F040"
        assert result["created_from_decomposition"] is True


class TestTaskDecomposer:
    """Test TaskDecomposer class."""

    def test_init(self, sample_project):
        """Test TaskDecomposer initialization."""
        project, db_manager = sample_project
        decomposer = TaskDecomposer(db_manager)

        assert decomposer.db_manager == db_manager

    def test_get_task_by_id(self, sample_project):
        """Test getting a task by ID."""
        project, db_manager = sample_project
        decomposer = TaskDecomposer(db_manager)

        # Create a task
        task = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Test task",
            description="Test description",
            steps=["Step 1"],
        )
        db_manager.create_task(task)

        # Get task
        retrieved = decomposer.get_task_by_id("task-001")
        assert retrieved is not None
        assert retrieved.id == "task-001"
        assert retrieved.spec_id == "F001"

        # Non-existent task
        retrieved = decomposer.get_task_by_id("nonexistent")
        assert retrieved is None

    def test_get_next_spec_id(self, sample_project):
        """Test getting next spec ID."""
        project, db_manager = sample_project
        decomposer = TaskDecomposer(db_manager)

        # Empty project should start at 1
        next_id = decomposer.get_next_spec_id(project.id)
        assert next_id == 1

        # Create some tasks
        task1 = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Task 1",
            description="Description",
            steps=[],
        )
        db_manager.create_task(task1)

        task5 = Task(
            id="task-005",
            project_id=project.id,
            spec_id="F005",
            title="Task 5",
            description="Description",
            steps=[],
        )
        db_manager.create_task(task5)

        # Next ID should be 6
        next_id = decomposer.get_next_spec_id(project.id)
        assert next_id == 6

    def test_decompose_task_simple(self, sample_project):
        """Test decomposing a task into sub-tasks."""
        project, db_manager = sample_project
        decomposer = TaskDecomposer(db_manager)

        # Create parent task
        parent = Task(
            id="task-parent",
            project_id=project.id,
            spec_id="F001",
            title="Complex task",
            description="A complex task that needs decomposition",
            steps=["Step 1", "Step 2", "Step 3", "Step 4"],
            priority="high",
            category="functional",
        )
        db_manager.create_task(parent)

        # Decompose into 2 sub-tasks
        sub_tasks = [
            {
                "internal_name": "setup",
                "title": "Set up infrastructure",
                "description": "Set up the infrastructure",
                "steps": ["Step 1", "Step 2"],
                "internal_deps": [],
                "priority": "high",
                "category": "functional",
            },
            {
                "internal_name": "implement",
                "title": "Implement feature",
                "description": "Implement the feature",
                "steps": ["Step 3", "Step 4"],
                "internal_deps": ["setup"],
                "priority": "high",
                "category": "functional",
            },
        ]

        result = decomposer.decompose_task(
            task_id="task-parent",
            sub_tasks=sub_tasks,
            reasoning="Task is too complex",
        )

        assert result.success is True
        assert result.parent_task_id == "task-parent"
        assert result.parent_spec_id == "F001"
        # 2 sub-tasks + 1 integration task = 3
        assert len(result.sub_tasks) == 3
        assert result.reasoning == "Task is too complex"

        # Check sub-task IDs use parent's ID + letter suffix
        assert result.sub_tasks[0].spec_id == "F001a"
        assert result.sub_tasks[1].spec_id == "F001b"
        assert result.sub_tasks[2].spec_id == "F001-integration"

        # Check dependencies
        assert result.sub_tasks[0].depends_on == []
        assert result.sub_tasks[1].depends_on == ["F001a"]
        # Integration depends on both sub-tasks
        assert set(result.sub_tasks[2].depends_on) == {"F001a", "F001b"}

        # Check parent is decomposed
        parent_updated = db_manager.get_task("task-parent")
        assert parent_updated.status in (TaskStatus.DEPRECATED, TaskStatus.DECOMPOSED)

        # Check sub-tasks + integration are in database
        tasks = db_manager.list_tasks(project.id)
        assert len(tasks) == 4  # parent + 2 subs + 1 integration

        # Find sub-tasks
        sub1 = next((t for t in tasks if t.spec_id == "F001a"), None)
        sub2 = next((t for t in tasks if t.spec_id == "F001b"), None)
        integration = next((t for t in tasks if t.spec_id == "F001-integration"), None)

        assert sub1 is not None
        assert sub1.title == "Set up infrastructure"
        assert sub1.status == TaskStatus.PENDING
        assert "decomposed-subtask" in sub1.labels

        assert sub2 is not None
        assert sub2.title == "Implement feature"
        assert sub2.depends_on == ["F001a"]

        assert integration is not None
        assert "integration-task" in integration.labels
        assert set(integration.depends_on) == {"F001a", "F001b"}


class TestGenerateDecompositionPrompt:
    """Test generate_decomposition_prompt function."""

    def test_generate_prompt(self):
        """Test generating decomposition prompt."""
        task = Task(
            id="task-123",
            project_id="proj-1",
            spec_id="F001",
            title="Complex task",
            description="A very complex task",
            steps=["Step 1", "Step 2", "Step 3"],
            depends_on=["F000"],
            priority="high",
            category="functional",
        )

        prompt = generate_decomposition_prompt(task, "Task failed 3 times")

        assert "F001" in prompt
        assert "Complex task" in prompt
        assert "A very complex task" in prompt
        assert "Step 1" in prompt
        assert "Step 2" in prompt
        assert "Step 3" in prompt
        assert "F000" in prompt
        assert "high" in prompt
        assert "functional" in prompt
        assert "Task failed 3 times" in prompt
        assert "decomposition_plan.json" in prompt
        assert "internal_name" in prompt


class TestAnalyzeTaskForDecomposition:
    """Test analyze_task_for_decomposition function."""

    def test_simple_task_no_decomposition(self):
        """Test analyzing a simple task."""
        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Simple task",
            description="Simple description",
            steps=["Step 1", "Step 2"],
        )

        analysis = analyze_task_for_decomposition(task)

        assert analysis["should_decompose"] is False
        assert len(analysis["complexity_factors"]) == 0

    def test_task_with_many_steps(self):
        """Test analyzing a task with many steps."""
        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Complex task",
            description="Description",
            steps=[f"Step {i}" for i in range(1, 11)],  # 10 steps
        )

        analysis = analyze_task_for_decomposition(task)

        assert analysis["should_decompose"] is True
        assert "Many steps" in str(analysis["complexity_factors"])
        assert analysis["suggested_sub_count"] >= 2


class TestValidateDecomposition:
    """Test validate_decomposition function."""

    def test_valid_decomposition(self):
        """Test validating a valid decomposition."""
        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Task",
            description="Description",
            steps=["Step 1", "Step 2"],
        )

        sub_tasks = [
            {
                "internal_name": "sub1",
                "title": "Sub 1",
                "description": "First sub-task",
                "steps": ["Step 1"],
                "internal_deps": [],
            },
            {
                "internal_name": "sub2",
                "title": "Sub 2",
                "description": "Second sub-task",
                "steps": ["Step 2"],
                "internal_deps": ["sub1"],
            },
        ]

        is_valid, issues = validate_decomposition(sub_tasks, task)

        assert is_valid is True
        assert len(issues) == 0

    def test_no_subtasks(self):
        """Test validation with no sub-tasks."""
        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Task",
            description="Description",
            steps=["Step 1"],
        )

        is_valid, issues = validate_decomposition([], task)

        assert is_valid is False
        assert "No sub-tasks provided" in issues


class TestSuggestDecomposition:
    """Test suggest_decomposition function."""

    def test_suggest_for_small_task(self):
        """Test suggesting decomposition for a small task."""
        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Small task",
            description="Small description",
            steps=["Step 1", "Step 2"],
            priority="high",
            category="functional",
        )

        suggestions = suggest_decomposition(task)

        assert len(suggestions) == 2
        assert suggestions[0]["internal_name"] == "foundation"
        assert suggestions[1]["internal_name"] == "completion"
        assert suggestions[1]["internal_deps"] == ["foundation"]
