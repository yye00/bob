"""Tests for task CLI commands."""

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models.base import Project, ProjectStatus, Task, TaskStatus


@pytest.fixture
def sample_project(tmp_path):
    """Create a sample project with tasks."""
    # Create database
    db_path = tmp_path / "test.db"
    db = DatabaseManager(db_path)

    # Create project
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        id="proj-test-123",
        name="test-project",
        description="Test project for task list tests",
        workspace_dir=str(workspace),
        spec_source="file://spec.yaml",
        status=ProjectStatus.ACTIVE,
    )
    db.create_project(project)

    # Create tasks with various statuses, priorities, and categories
    tasks = [
        Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Implement authentication",
            description="Add user authentication system",
            status=TaskStatus.PENDING,
            priority="critical",
            category="functional",
            attempts=0,
        ),
        Task(
            id="task-002",
            project_id=project.id,
            spec_id="F002",
            title="Add user registration",
            description="Create registration form and logic",
            status=TaskStatus.IN_PROGRESS,
            priority="high",
            category="functional",
            attempts=1,
        ),
        Task(
            id="task-003",
            project_id=project.id,
            spec_id="F003",
            title="Create dashboard",
            description="Build admin dashboard",
            status=TaskStatus.COMPLETED,
            priority="medium",
            category="functional",
            attempts=2,
        ),
        Task(
            id="task-004",
            project_id=project.id,
            spec_id="T001",
            title="Write unit tests",
            description="Add comprehensive unit tests",
            status=TaskStatus.PENDING,
            priority="high",
            category="test",
            attempts=0,
        ),
        Task(
            id="task-005",
            project_id=project.id,
            spec_id="I001",
            title="Setup CI/CD pipeline",
            description="Configure GitHub Actions",
            status=TaskStatus.BLOCKED,
            priority="medium",
            category="infra",
            attempts=1,
        ),
        Task(
            id="task-006",
            project_id=project.id,
            spec_id="D001",
            title="Write API documentation",
            description="Document all API endpoints",
            status=TaskStatus.PENDING,
            priority="low",
            category="docs",
            attempts=0,
        ),
        Task(
            id="task-007",
            project_id=project.id,
            spec_id="F004",
            title="Add caching layer",
            description="Implement Redis caching",
            status=TaskStatus.FAILED,
            priority="medium",
            category="functional",
            attempts=3,
        ),
        Task(
            id="task-008",
            project_id=project.id,
            spec_id="F005",
            title="Research ML models",
            description="Research best ML models for recommendations",
            status=TaskStatus.RESEARCH_NEEDED,
            priority="high",
            category="functional",
            attempts=0,
            research_required=True,
            research_complete=False,
        ),
        Task(
            id="task-009",
            project_id=project.id,
            spec_id="F006",
            title="Implement recommendations",
            description="Build recommendation engine",
            status=TaskStatus.PENDING,
            priority="medium",
            category="functional",
            attempts=0,
            research_required=True,
            research_complete=True,
        ),
    ]

    for task in tasks:
        db.create_task(task)

    return {
        "db_path": db_path,
        "project": project,
        "tasks": tasks,
    }


class TestTaskListCommand:
    """Tests for 'bob task list' command."""

    def test_list_help(self):
        """Test task list help text."""
        runner = CliRunner()
        result = runner.invoke(cli, ["task", "list", "--help"])
        assert result.exit_code == 0
        assert "List tasks with optional filters" in result.output
        assert "--status" in result.output
        assert "--priority" in result.output
        assert "--category" in result.output
        assert "--needs-research" in result.output
        assert "--json" in result.output

    def test_list_no_active_project(self, tmp_path):
        """Test list with no active project."""
        runner = CliRunner()
        db_path = tmp_path / "empty.db"
        DatabaseManager(db_path)  # Initialize empty database

        result = runner.invoke(cli, ["--db", str(db_path), "task", "list"])
        assert result.exit_code == 1
        assert "No active project found" in result.output

    def test_list_all_tasks(self, sample_project):
        """Test listing all tasks."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--db", str(sample_project["db_path"]), "task", "list"]
        )
        assert result.exit_code == 0
        # Should show all 9 tasks
        assert "F001" in result.output
        assert "F002" in result.output
        assert "F003" in result.output
        assert "T001" in result.output
        assert "I001" in result.output
        assert "D001" in result.output
        assert "F004" in result.output
        assert "F005" in result.output
        assert "F006" in result.output
        assert "Total tasks: 9" in result.output

    def test_list_with_status_filter(self, sample_project):
        """Test filtering by status."""
        runner = CliRunner()

        # Filter pending tasks
        result = runner.invoke(
            cli,
            ["--db", str(sample_project["db_path"]), "task", "list", "--status", "pending"],
        )
        assert result.exit_code == 0
        assert "F001" in result.output  # pending
        assert "T001" in result.output  # pending
        assert "D001" in result.output  # pending
        assert "F006" in result.output  # pending
        assert "F002" not in result.output  # in_progress
        assert "F003" not in result.output  # completed
        assert "Total tasks: 4" in result.output

    def test_list_with_priority_filter(self, sample_project):
        """Test filtering by priority."""
        runner = CliRunner()

        # Filter critical priority
        result = runner.invoke(
            cli,
            ["--db", str(sample_project["db_path"]), "task", "list", "--priority", "critical"],
        )
        assert result.exit_code == 0
        assert "F001" in result.output  # critical
        assert "F002" not in result.output  # high
        assert "Total tasks: 1" in result.output

        # Filter high priority
        result = runner.invoke(
            cli,
            ["--db", str(sample_project["db_path"]), "task", "list", "--priority", "high"],
        )
        assert result.exit_code == 0
        assert "F002" in result.output  # high
        assert "T001" in result.output  # high
        assert "F005" in result.output  # high
        assert "Total tasks: 3" in result.output

    def test_list_with_category_filter(self, sample_project):
        """Test filtering by category."""
        runner = CliRunner()

        # Filter functional category
        result = runner.invoke(
            cli,
            ["--db", str(sample_project["db_path"]), "task", "list", "--category", "functional"],
        )
        assert result.exit_code == 0
        assert "F001" in result.output
        assert "F002" in result.output
        assert "F003" in result.output
        assert "T001" not in result.output  # test category
        assert "I001" not in result.output  # infra category
        assert "D001" not in result.output  # docs category
        assert "Total tasks: 6" in result.output

        # Filter test category
        result = runner.invoke(
            cli,
            ["--db", str(sample_project["db_path"]), "task", "list", "--category", "test"],
        )
        assert result.exit_code == 0
        assert "T001" in result.output
        assert "F001" not in result.output
        assert "Total tasks: 1" in result.output

    def test_list_with_needs_research_filter(self, sample_project):
        """Test filtering by needs-research flag."""
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ["--db", str(sample_project["db_path"]), "task", "list", "--needs-research"],
        )
        assert result.exit_code == 0
        # Should only show F005 (research_required=True, research_complete=False)
        assert "F005" in result.output
        assert "F006" not in result.output  # research complete
        assert "F001" not in result.output  # no research required
        assert "Total tasks: 1" in result.output

    def test_list_with_combined_filters(self, sample_project):
        """Test combining multiple filters."""
        runner = CliRunner()

        # Pending + high priority
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project["db_path"]),
                "task",
                "list",
                "--status",
                "pending",
                "--priority",
                "high",
            ],
        )
        assert result.exit_code == 0
        assert "T001" in result.output  # pending + high
        assert "F001" not in result.output  # pending but critical
        assert "F002" not in result.output  # high but in_progress
        assert "Total tasks: 1" in result.output

        # Pending + functional category
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project["db_path"]),
                "task",
                "list",
                "--status",
                "pending",
                "--category",
                "functional",
            ],
        )
        assert result.exit_code == 0
        assert "F001" in result.output  # pending + functional
        assert "F006" in result.output  # pending + functional
        assert "T001" not in result.output  # pending but test category
        assert "Total tasks: 2" in result.output

    def test_list_json_output(self, sample_project):
        """Test JSON output format."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--db", str(sample_project["db_path"]), "task", "list", "--json"]
        )
        assert result.exit_code == 0

        # Parse JSON output (may have migration messages before/after JSON)
        lines = result.output.strip().split("\n")
        json_lines = []
        in_json = False
        brace_count = 0

        for line in lines:
            if line.strip().startswith("{"):
                in_json = True
                brace_count += line.count("{") - line.count("}")
                json_lines.append(line)
            elif in_json:
                brace_count += line.count("{") - line.count("}")
                json_lines.append(line)
                if brace_count == 0:
                    # JSON object complete
                    break

        assert json_lines, "No JSON found in output"
        json_str = "\n".join(json_lines)
        data = json.loads(json_str)

        assert "project_id" in data
        assert data["project_id"] == "proj-test-123"
        assert "count" in data
        assert data["count"] == 9
        assert "tasks" in data
        assert len(data["tasks"]) == 9

        # Check first task structure
        task = data["tasks"][0]
        assert "id" in task
        assert "spec_id" in task
        assert "title" in task
        assert "status" in task
        assert "priority" in task
        assert "category" in task
        assert "attempts" in task
        assert "depends_on" in task

    def test_list_json_with_filters(self, sample_project):
        """Test JSON output with filters."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project["db_path"]),
                "task",
                "list",
                "--status",
                "pending",
                "--json",
            ],
        )
        assert result.exit_code == 0

        # Parse JSON (handle migration messages)
        lines = result.output.strip().split("\n")
        json_lines = []
        in_json = False
        brace_count = 0

        for line in lines:
            if line.strip().startswith("{"):
                in_json = True
                brace_count += line.count("{") - line.count("}")
                json_lines.append(line)
            elif in_json:
                brace_count += line.count("{") - line.count("}")
                json_lines.append(line)
                if brace_count == 0:
                    break

        json_str = "\n".join(json_lines)
        data = json.loads(json_str)
        assert data["count"] == 4
        assert len(data["tasks"]) == 4

        # All tasks should be pending
        for task in data["tasks"]:
            assert task["status"] == "pending"

    def test_list_global_json_flag(self, sample_project):
        """Test global --json flag."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--json", "--db", str(sample_project["db_path"]), "task", "list"]
        )
        assert result.exit_code == 0

        # Should output JSON (handle migration messages)
        lines = result.output.strip().split("\n")
        json_lines = []
        in_json = False
        brace_count = 0

        for line in lines:
            if line.strip().startswith("{"):
                in_json = True
                brace_count += line.count("{") - line.count("}")
                json_lines.append(line)
            elif in_json:
                brace_count += line.count("{") - line.count("}")
                json_lines.append(line)
                if brace_count == 0:
                    break

        json_str = "\n".join(json_lines)
        data = json.loads(json_str)
        assert "tasks" in data

    def test_list_with_project_option(self, sample_project):
        """Test using --project option."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project["db_path"]),
                "--project",
                "proj-test-123",
                "task",
                "list",
            ],
        )
        assert result.exit_code == 0
        assert "Total tasks: 9" in result.output

    def test_list_empty_results(self, sample_project):
        """Test list with filters that return no results."""
        runner = CliRunner()

        # No tasks with 'skipped' status
        result = runner.invoke(
            cli,
            ["--db", str(sample_project["db_path"]), "task", "list", "--status", "skipped"],
        )
        assert result.exit_code == 0
        assert "No tasks found matching the filters" in result.output

    def test_list_with_limit(self, sample_project):
        """Test limiting number of results."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--db", str(sample_project["db_path"]), "task", "list", "--limit", "3"],
        )
        assert result.exit_code == 0
        # Should show only 3 tasks (highest priority first)
        assert "Total tasks: 3" in result.output

    def test_list_displays_task_info(self, sample_project):
        """Test that list displays correct task information."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--db", str(sample_project["db_path"]), "task", "list"]
        )
        assert result.exit_code == 0

        # Check table headers
        assert "Spec ID" in result.output
        assert "Title" in result.output
        assert "Status" in result.output
        assert "Priority" in result.output
        assert "Attempts" in result.output
        assert "Model" in result.output

        # Check specific task data (title may be truncated)
        assert "Implement" in result.output or "authenti" in result.output
        assert "critical" in result.output
        assert "pending" in result.output

    def test_list_status_summary(self, sample_project):
        """Test that status summary is displayed."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--db", str(sample_project["db_path"]), "task", "list"]
        )
        assert result.exit_code == 0

        # Check status summary
        assert "Status summary:" in result.output
        assert "pending:" in result.output or "• pending: 4" in result.output


class TestTaskListMultipleProjects:
    """Tests for task list with multiple projects."""

    def test_list_with_multiple_projects(self, tmp_path):
        """Test listing tasks when multiple projects exist."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        # Create two projects
        workspace1 = tmp_path / "workspace1"
        workspace1.mkdir()
        project1 = Project(
            id="proj-001",
            name="project1",
            description="First project",
            workspace_dir=str(workspace1),
            spec_source="file://spec1.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project1)

        workspace2 = tmp_path / "workspace2"
        workspace2.mkdir()
        project2 = Project(
            id="proj-002",
            name="project2",
            description="Second project",
            workspace_dir=str(workspace2),
            spec_source="file://spec2.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project2)

        # Add tasks to project1
        task1 = Task(
            id="task-001",
            project_id=project1.id,
            spec_id="F001",
            title="Task in project 1",
            description="Task 1",
            status=TaskStatus.PENDING,
        )
        db.create_task(task1)

        # Add tasks to project2
        task2 = Task(
            id="task-002",
            project_id=project2.id,
            spec_id="F002",
            title="Task in project 2",
            description="Task 2",
            status=TaskStatus.PENDING,
        )
        db.create_task(task2)

        # List without --project should use first active project (most recent)
        # Projects are ordered by created_at DESC, so project2 is first
        runner = CliRunner()
        result = runner.invoke(cli, ["--db", str(db_path), "task", "list"])
        assert result.exit_code == 0
        assert "project 2" in result.output.lower()
        assert "project 1" not in result.output.lower()

        # List with --project should show only that project's tasks
        result = runner.invoke(
            cli, ["--db", str(db_path), "--project", "proj-001", "task", "list"]
        )
        assert result.exit_code == 0
        assert "project 1" in result.output.lower()
        assert "project 2" not in result.output.lower()


class TestTaskListEdgeCases:
    """Tests for edge cases in task list command."""

    def test_list_with_long_title(self, tmp_path):
        """Test listing tasks with very long titles."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-001",
            name="test-project",
            description="Test",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create task with very long title
        long_title = "A" * 100  # 100 character title
        task = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title=long_title,
            description="Test",
            status=TaskStatus.PENDING,
        )
        db.create_task(task)

        runner = CliRunner()
        result = runner.invoke(cli, ["--db", str(db_path), "task", "list"])
        assert result.exit_code == 0
        # Title should be truncated with ...
        assert "..." in result.output

    def test_list_with_special_characters(self, tmp_path):
        """Test listing tasks with special characters in title."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-001",
            name="test-project",
            description="Test",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        task = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Fix bug: 'NoneType' object has no attribute 'value'",
            description="Test",
            status=TaskStatus.PENDING,
        )
        db.create_task(task)

        runner = CliRunner()
        result = runner.invoke(cli, ["--db", str(db_path), "task", "list"])
        assert result.exit_code == 0
        # Should handle special characters without error
        assert "NoneType" in result.output or "Fix bug" in result.output

    def test_list_case_insensitive_filters(self, sample_project):
        """Test that filters are case-insensitive."""
        runner = CliRunner()

        # Test uppercase status
        result = runner.invoke(
            cli,
            ["--db", str(sample_project["db_path"]), "task", "list", "--status", "PENDING"],
        )
        assert result.exit_code == 0
        assert "Total tasks: 4" in result.output

        # Test uppercase priority
        result = runner.invoke(
            cli,
            ["--db", str(sample_project["db_path"]), "task", "list", "--priority", "HIGH"],
        )
        assert result.exit_code == 0
        assert "Total tasks: 3" in result.output


# ============================================================================
# Task Show Command Tests
# ============================================================================


class TestTaskShowCommand:
    """Tests for 'bob task show' command."""

    def test_show_help(self):
        """Test show command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["task", "show", "--help"])
        assert result.exit_code == 0
        assert "Show detailed information about a specific task" in result.output

    def test_show_by_spec_id(self, sample_project):
        """Test showing task by spec ID."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--db", str(sample_project["db_path"]), "task", "show", "F001"]
        )
        assert result.exit_code == 0
        assert "F001" in result.output
        assert "Implement authentication" in result.output
        assert "Add user authentication system" in result.output
        assert "Status:" in result.output
        assert "Priority:" in result.output

    def test_show_by_database_id(self, sample_project):
        """Test showing task by database ID."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--db", str(sample_project["db_path"]), "task", "show", "task-001"]
        )
        assert result.exit_code == 0
        assert "F001" in result.output
        assert "Implement authentication" in result.output

    def test_show_nonexistent_task(self, sample_project):
        """Test showing nonexistent task."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--db", str(sample_project["db_path"]), "task", "show", "F999"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_show_displays_full_details(self, tmp_path):
        """Test that show displays all task details."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-001",
            name="test-project",
            description="Test",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create task with comprehensive details
        task = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Test Feature",
            description="Detailed description of the feature",
            acceptance_criteria=["Criterion 1", "Criterion 2"],
            steps=["Step 1", "Step 2", "Step 3"],
            depends_on=["F000"],
            priority="high",
            category="functional",
            labels=["auth", "mvp"],
            status=TaskStatus.IN_PROGRESS,
            attempts=2,
        )
        db.create_task(task)

        runner = CliRunner()
        result = runner.invoke(cli, ["--db", str(db_path), "task", "show", "F001"])
        assert result.exit_code == 0

        # Check all sections are displayed
        assert "Description:" in result.output
        assert "Detailed description" in result.output
        assert "Acceptance Criteria:" in result.output
        assert "Criterion 1" in result.output
        assert "Implementation Steps:" in result.output
        assert "Step 1" in result.output
        assert "Dependencies:" in result.output
        assert "F000" in result.output
        assert "Labels:" in result.output
        assert "auth" in result.output
        assert "mvp" in result.output
        assert "Progress:" in result.output
        assert "Attempts: 2" in result.output

    def test_show_with_research_flag(self, tmp_path):
        """Test showing task with research flag."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-001",
            name="test-project",
            description="Test",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        task = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Research Task",
            description="Task requiring research",
            status=TaskStatus.RESEARCH_NEEDED,
            research_required=True,
            research_queries=["query 1", "query 2"],
            research_findings={"finding1": "result1", "finding2": "result2"},
        )
        db.create_task(task)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["--db", str(db_path), "task", "show", "F001", "--research"]
        )
        assert result.exit_code == 0
        assert "Research:" in result.output
        assert "Required: Yes" in result.output
        assert "query 1" in result.output
        assert "Findings:" in result.output
        assert "finding1" in result.output

    def test_show_with_escalation_flag(self, tmp_path):
        """Test showing task with escalation flag."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-001",
            name="test-project",
            description="Test",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        from bob.models.base import ModelTier, FailureType

        task = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Escalated Task",
            description="Task with escalation",
            status=TaskStatus.FAILED,
            escalation_tier=ModelTier.TIER2,
            failure_type=FailureType.TIMEOUT,
        )
        db.create_task(task)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["--db", str(db_path), "task", "show", "F001", "--escalation"]
        )
        assert result.exit_code == 0
        assert "Escalation State:" in result.output
        assert "tier2" in result.output.lower()

    def test_show_json_output(self, sample_project):
        """Test show with JSON output."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--db", str(sample_project["db_path"]), "task", "show", "F001", "--json"]
        )
        assert result.exit_code == 0

        # Parse JSON output (handle migration messages)
        lines = result.output.strip().split("\n")
        json_lines = []
        in_json = False
        brace_count = 0

        for line in lines:
            if line.strip().startswith("{"):
                in_json = True
                brace_count += line.count("{") - line.count("}")
                json_lines.append(line)
            elif in_json:
                brace_count += line.count("{") - line.count("}")
                json_lines.append(line)
                if brace_count == 0:
                    break

        json_str = "\n".join(json_lines)
        data = json.loads(json_str)

        assert data["spec_id"] == "F001"
        assert data["title"] == "Implement authentication"
        assert "description" in data
        assert "status" in data
        assert "priority" in data
        assert "sessions" in data

    def test_show_displays_dependency_graph(self, tmp_path):
        """Test that show displays tasks that this task blocks."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project = Project(
            id="proj-001",
            name="test-project",
            description="Test",
            workspace_dir=str(workspace),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Create task F001
        task1 = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Base Task",
            description="Task that others depend on",
            status=TaskStatus.COMPLETED,
        )
        db.create_task(task1)

        # Create task F002 that depends on F001
        task2 = Task(
            id="task-002",
            project_id=project.id,
            spec_id="F002",
            title="Dependent Task",
            description="Task that depends on F001",
            depends_on=["F001"],
            status=TaskStatus.PENDING,
        )
        db.create_task(task2)

        runner = CliRunner()
        result = runner.invoke(cli, ["--db", str(db_path), "task", "show", "F001"])
        assert result.exit_code == 0

        # Should show that F001 blocks F002
        assert "Blocks:" in result.output
        assert "F002" in result.output

    def test_show_no_active_project(self, tmp_path):
        """Test show when no active project exists."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["--db", str(db_path), "task", "show", "F001"])
        assert result.exit_code != 0
        assert "No active project found" in result.output

    def test_show_global_json_flag(self, sample_project):
        """Test global --json flag with show command."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--json", "--db", str(sample_project["db_path"]), "task", "show", "F001"]
        )
        assert result.exit_code == 0

        # Should output JSON
        lines = result.output.strip().split("\n")
        json_lines = []
        in_json = False
        brace_count = 0

        for line in lines:
            if line.strip().startswith("{"):
                in_json = True
                brace_count += line.count("{") - line.count("}")
                json_lines.append(line)
            elif in_json:
                brace_count += line.count("{") - line.count("}")
                json_lines.append(line)
                if brace_count == 0:
                    break

        json_str = "\n".join(json_lines)
        data = json.loads(json_str)
        assert data["spec_id"] == "F001"
