"""Tests for research CLI command."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models.base import Project, ProjectStatus, Task, TaskStatus


@pytest.fixture
def sample_project_with_research(tmp_path):
    """Create a sample project with research tasks."""
    # Create database
    db_path = tmp_path / "test.db"
    db = DatabaseManager(db_path)

    # Create project
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        id="proj-test-123",
        name="test-project",
        description="Test project for research tests",
        workspace_dir=str(workspace),
        spec_source="file://spec.yaml",
        status=ProjectStatus.ACTIVE,
    )
    db.create_project(project)

    # Create task with research required
    task_with_research = Task(
        id="task-001",
        project_id=project.id,
        spec_id="F001",
        title="Research task",
        description="Task requiring research",
        status=TaskStatus.RESEARCH_NEEDED,
        research_required=True,
        research_complete=False,
        research_queries=[
            "What are the best practices for this?",
            "How do other frameworks solve this?",
        ],
    )
    db.create_task(task_with_research)

    # Create task without research
    task_normal = Task(
        id="task-002",
        project_id=project.id,
        spec_id="F002",
        title="Normal task",
        description="Regular task",
        status=TaskStatus.PENDING,
        research_required=False,
    )
    db.create_task(task_normal)

    # Create task with research already complete
    task_research_done = Task(
        id="task-003",
        project_id=project.id,
        spec_id="F003",
        title="Research complete task",
        description="Task with completed research",
        status=TaskStatus.PENDING,
        research_required=True,
        research_complete=True,
        research_queries=["Some query"],
        research_findings={"query": "finding"},
    )
    db.create_task(task_research_done)

    return {
        "db_path": db_path,
        "db": db,
        "project": project,
        "task_with_research": task_with_research,
        "task_normal": task_normal,
        "task_research_done": task_research_done,
    }


class TestResearchCommandHelp:
    """Tests for research command help."""

    def test_research_help(self):
        """Test research command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["research", "--help"])
        assert result.exit_code == 0
        assert "Execute research for a task" in result.output
        assert "--type" in result.output
        assert "--max-queries" in result.output


class TestResearchCommandBasic:
    """Tests for basic research command functionality."""

    def test_research_task_with_queries(self, sample_project_with_research):
        """Test executing research on a task with queries."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project_with_research["db_path"]),
                "research",
                "F001",
            ],
        )

        # Should succeed
        assert result.exit_code == 0
        assert "Research completed successfully" in result.output or "✓" in result.output

    def test_research_nonexistent_task(self, sample_project_with_research):
        """Test research on nonexistent task."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--db", str(sample_project_with_research["db_path"]), "research", "F999"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_research_task_without_research_required(self, sample_project_with_research):
        """Test research on task that doesn't require research."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--db", str(sample_project_with_research["db_path"]), "research", "F002"],
        )
        assert result.exit_code != 0
        assert "does not require research" in result.output

    def test_research_already_complete(self, sample_project_with_research):
        """Test research on task with research already complete."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--db", str(sample_project_with_research["db_path"]), "research", "F003"],
        )
        assert result.exit_code != 0
        assert "already complete" in result.output

    def test_research_task_without_queries(self, tmp_path):
        """Test research on task without research queries."""
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

        # Task with research required but no queries
        task = Task(
            id="task-001",
            project_id=project.id,
            spec_id="F001",
            title="Task",
            description="Task without queries",
            research_required=True,
            research_complete=False,
            research_queries=[],  # Empty queries
        )
        db.create_task(task)

        runner = CliRunner()
        result = runner.invoke(cli, ["--db", str(db_path), "research", "F001"])
        assert result.exit_code != 0
        assert "No research queries" in result.output


class TestResearchCommandOptions:
    """Tests for research command options."""

    def test_research_with_type_option(self, sample_project_with_research):
        """Test research with --type option."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project_with_research["db_path"]),
                "research",
                "F001",
                "--type",
                "deep",
            ],
        )
        assert result.exit_code == 0

    def test_research_with_max_queries(self, sample_project_with_research):
        """Test research with --max-queries option."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project_with_research["db_path"]),
                "research",
                "F001",
                "--max-queries",
                "1",
            ],
        )
        assert result.exit_code == 0

    def test_research_json_output(self, sample_project_with_research):
        """Test research with --json output."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project_with_research["db_path"]),
                "research",
                "F001",
                "--json",
            ],
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

        assert "success" in data
        assert data["task_id"] == "F001"

    def test_research_global_json_flag(self, sample_project_with_research):
        """Test research with global --json flag."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--json",
                "--db",
                str(sample_project_with_research["db_path"]),
                "research",
                "F001",
            ],
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
        assert "task_id" in data


class TestResearchCommandEdgeCases:
    """Tests for edge cases in research command."""

    def test_research_no_active_project(self, tmp_path):
        """Test research when no active project exists."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["--db", str(db_path), "research", "F001"])
        assert result.exit_code != 0
        assert "No active project found" in result.output

    def test_research_by_database_id(self, sample_project_with_research):
        """Test research using database ID instead of spec ID."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project_with_research["db_path"]),
                "research",
                "task-001",
            ],
        )
        assert result.exit_code == 0

    def test_research_updates_database(self, sample_project_with_research):
        """Test that research updates the task in database."""
        db = sample_project_with_research["db"]

        # Run research
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project_with_research["db_path"]),
                "research",
                "F001",
            ],
        )
        assert result.exit_code == 0

        # Verify task was updated
        task = db.get_task("task-001")
        assert task is not None
        assert task.research_complete is True
        # Research findings should be populated (placeholder data)
        assert len(task.research_findings) > 0


class TestResearchCommandValidation:
    """Tests for research command validation."""

    def test_research_invalid_type(self, sample_project_with_research):
        """Test research with invalid type."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project_with_research["db_path"]),
                "research",
                "F001",
                "--type",
                "invalid",
            ],
        )
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid" in result.output.lower()

    def test_research_displays_queries(self, sample_project_with_research):
        """Test that research command displays queries before executing."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--db",
                str(sample_project_with_research["db_path"]),
                "research",
                "F001",
            ],
        )
        assert result.exit_code == 0
        # Should show the queries
        assert "What are the best practices" in result.output or "Queries" in result.output
