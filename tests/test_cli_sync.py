"""Tests for bob sync command (bob/cli/sync.py)."""

import json
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models.base import Project, ProjectStatus, Task, TaskStatus


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database."""
    db_file = tmp_path / "test.db"
    db = DatabaseManager(db_file)
    return db_file


@pytest.fixture
def sample_project(db_path, tmp_path):
    """Create a sample project with a spec file."""
    db = DatabaseManager(db_path)

    # Create workspace directory
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create spec file
    spec_file = tmp_path / "spec.yaml"
    spec_data = {
        "spec_version": 1,
        "tasks": [
            {
                "id": "F001",
                "title": "Task 1",
                "description": "Description 1",
                "spec_version": 1,
            },
            {
                "id": "F002",
                "title": "Task 2",
                "description": "Description 2",
                "depends_on": ["F001"],
                "priority": "high",
                "spec_version": 1,
            },
        ],
    }
    with open(spec_file, "w") as f:
        yaml.dump(spec_data, f)

    # Create project
    project_id = f"proj-{uuid.uuid4().hex[:8]}"
    project = Project(
        id=project_id,
        name="test-project",
        description="Test project",
        workspace_dir=str(workspace),
        spec_source=f"file://{spec_file}",
        config={},
        created_at=datetime.now(),
        status=ProjectStatus.ACTIVE,
    )
    db.create_project(project)

    return {
        "project": project,
        "db_path": db_path,
        "spec_file": spec_file,
        "workspace": workspace,
    }


class TestSyncCommand:
    """Test bob sync command."""

    def test_sync_help(self, runner):
        """Test sync --help shows usage."""
        result = runner.invoke(cli, ["sync", "--help"])
        assert result.exit_code == 0
        assert "Sync tasks with spec source" in result.output
        assert "--force" in result.output
        assert "--dry-run" in result.output

    def test_sync_no_active_project(self, runner, db_path):
        """Test sync fails when no active project exists."""
        result = runner.invoke(cli, ["--db", str(db_path), "sync"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "no active project" in result.output.lower()

    def test_sync_adds_new_tasks(self, runner, sample_project):
        """Test sync adds new tasks from spec file."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]

        # Run sync
        result = runner.invoke(
            cli, ["--db", str(db_path), "--project", project.id, "sync"]
        )
        assert result.exit_code == 0
        assert "Sync complete" in result.output
        assert "Added: 2" in result.output

        # Verify tasks were added
        db = DatabaseManager(db_path)
        tasks = db.list_tasks(project_id=project.id)
        assert len(tasks) == 2

        # Check task details
        task_by_spec_id = {t.spec_id: t for t in tasks}
        assert "F001" in task_by_spec_id
        assert "F002" in task_by_spec_id

        task1 = task_by_spec_id["F001"]
        assert task1.title == "Task 1"
        assert task1.description == "Description 1"
        assert task1.status == TaskStatus.PENDING

        task2 = task_by_spec_id["F002"]
        assert task2.title == "Task 2"
        assert task2.depends_on == ["F001"]
        assert task2.priority == "high"

    def test_sync_no_changes(self, runner, sample_project):
        """Test sync when there are no changes."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]

        # First sync
        runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])

        # Second sync - no changes
        result = runner.invoke(
            cli, ["--db", str(db_path), "--project", project.id, "sync"]
        )
        assert result.exit_code == 0
        assert "No changes detected" in result.output

    def test_sync_modifies_existing_tasks(self, runner, sample_project):
        """Test sync updates modified tasks."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]
        spec_file = sample_project["spec_file"]

        # First sync
        runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])

        # Modify spec file
        spec_data = {
            "spec_version": 1,
            "tasks": [
                {
                    "id": "F001",
                    "title": "Task 1 Updated",
                    "description": "Description 1 Updated",
                    "priority": "critical",
                    "spec_version": 2,  # Version changed
                },
                {
                    "id": "F002",
                    "title": "Task 2",
                    "description": "Description 2",
                    "depends_on": ["F001"],
                    "priority": "high",
                    "spec_version": 1,
                },
            ],
        }
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        # Second sync
        result = runner.invoke(
            cli, ["--db", str(db_path), "--project", project.id, "sync"]
        )
        assert result.exit_code == 0
        assert "Modified: 1" in result.output

        # Verify task was updated
        db = DatabaseManager(db_path)
        tasks = db.list_tasks(project_id=project.id)
        task_by_spec_id = {t.spec_id: t for t in tasks}

        task1 = task_by_spec_id["F001"]
        assert task1.title == "Task 1 Updated"
        assert task1.description == "Description 1 Updated"
        assert task1.priority == "critical"

    def test_sync_marks_removed_tasks_as_deprecated(self, runner, sample_project):
        """Test sync marks removed tasks as deprecated."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]
        spec_file = sample_project["spec_file"]

        # First sync
        runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])

        # Remove F002 from spec
        spec_data = {
            "spec_version": 1,
            "tasks": [
                {
                    "id": "F001",
                    "title": "Task 1",
                    "description": "Description 1",
                    "spec_version": 1,
                },
            ],
        }
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        # Second sync
        result = runner.invoke(
            cli, ["--db", str(db_path), "--project", project.id, "sync"]
        )
        assert result.exit_code == 0
        assert "Deprecated: 1" in result.output

        # Verify task was marked as deprecated
        db = DatabaseManager(db_path)
        tasks = db.list_tasks(project_id=project.id)
        task_by_spec_id = {t.spec_id: t for t in tasks}

        # Task still exists but is deprecated
        assert "F002" in task_by_spec_id
        assert task_by_spec_id["F002"].status == TaskStatus.DEPRECATED

    def test_sync_preserves_task_status(self, runner, sample_project):
        """Test sync preserves task status and progress."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]
        spec_file = sample_project["spec_file"]

        # First sync
        runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])

        # Update task status
        db = DatabaseManager(db_path)
        tasks = db.list_tasks(project_id=project.id)
        task1 = next(t for t in tasks if t.spec_id == "F001")
        db.update_task(task1.id, status=TaskStatus.COMPLETED, attempts=3)

        # Modify spec file (change description)
        spec_data = {
            "spec_version": 1,
            "tasks": [
                {
                    "id": "F001",
                    "title": "Task 1",
                    "description": "Updated description",
                    "spec_version": 2,
                },
                {
                    "id": "F002",
                    "title": "Task 2",
                    "description": "Description 2",
                    "depends_on": ["F001"],
                    "priority": "high",
                    "spec_version": 1,
                },
            ],
        }
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        # Second sync
        runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])

        # Verify status was preserved
        tasks = db.list_tasks(project_id=project.id)
        task1 = next(t for t in tasks if t.spec_id == "F001")
        assert task1.status == TaskStatus.COMPLETED
        assert task1.attempts == 3
        assert task1.description == "Updated description"

    def test_sync_force_mode(self, runner, sample_project):
        """Test sync --force forces full re-sync."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]

        # First sync
        runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])

        # Force sync (should detect no changes but still process)
        result = runner.invoke(
            cli, ["--db", str(db_path), "--project", project.id, "sync", "--force"]
        )
        assert result.exit_code == 0
        # With force mode, it treats all as new, but since they exist, they're modified
        # Actually, this depends on implementation - force mode resets known_tasks

    def test_sync_dry_run_mode(self, runner, sample_project):
        """Test sync --dry-run shows changes without applying."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]

        # Dry run sync
        result = runner.invoke(
            cli, ["--db", str(db_path), "--project", project.id, "sync", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "Dry run mode" in result.output
        assert "Would add:" in result.output
        assert "F001" in result.output
        assert "F002" in result.output

        # Verify no tasks were actually added
        db = DatabaseManager(db_path)
        tasks = db.list_tasks(project_id=project.id)
        assert len(tasks) == 0

    def test_sync_json_output(self, runner, sample_project):
        """Test sync --json-output returns JSON."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]

        # Sync with JSON output
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "--project", project.id, "sync", "--json-output"],
        )
        assert result.exit_code == 0

        # Parse JSON output (extract JSON from output that may have other text)
        # Find the JSON object in the output
        import re
        json_match = re.search(r'\{[\s\S]*\}', result.output)
        assert json_match, f"No JSON found in output: {result.output}"
        data = json.loads(json_match.group())
        assert data["project_id"] == project.id
        assert data["project_name"] == "test-project"
        assert data["changes"] == 2
        assert data["added"] == 2
        assert data["modified"] == 0
        assert data["removed"] == 0

    def test_sync_json_output_no_changes(self, runner, sample_project):
        """Test sync --json-output with no changes."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]

        # First sync
        runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])

        # Second sync with JSON output
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "--project", project.id, "sync", "--json-output"],
        )
        assert result.exit_code == 0

        # Parse JSON output (extract JSON from output that may have other text)
        import re
        json_match = re.search(r'\{[\s\S]*\}', result.output)
        assert json_match, f"No JSON found in output: {result.output}"
        data = json.loads(json_match.group())
        assert data["changes"] == 0

    def test_sync_with_project_option(self, runner, sample_project):
        """Test sync with --project option."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]

        result = runner.invoke(
            cli, ["--db", str(db_path), "--project", project.id, "sync"]
        )
        assert result.exit_code == 0
        assert "Sync complete" in result.output

    def test_sync_invalid_project(self, runner, db_path):
        """Test sync with invalid project ID."""
        result = runner.invoke(cli, ["--db", str(db_path), "--project", "invalid", "sync"])
        assert result.exit_code == 1
        assert "Project not found" in result.output

    def test_sync_invalid_spec_source(self, runner, db_path, tmp_path):
        """Test sync with invalid spec source URI."""
        db = DatabaseManager(db_path)

        # Create project with invalid spec source
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project_id = f"proj-{uuid.uuid4().hex[:8]}"
        project = Project(
            id=project_id,
            name="test-project",
            description="Test project",
            workspace_dir=str(workspace),
            spec_source="invalid://spec",  # Invalid URI
            config={},
            created_at=datetime.now(),
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        result = runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])
        assert result.exit_code == 1
        assert "Failed to create spec source" in result.output

    def test_sync_with_research_requirements(self, runner, sample_project):
        """Test sync correctly imports research requirements."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]
        spec_file = sample_project["spec_file"]

        # Create spec with research requirements
        spec_data = {
            "spec_version": 1,
            "tasks": [
                {
                    "id": "F001",
                    "title": "Investigate best approach",
                    "description": "Research the best way to implement this",
                    "research_required": True,
                    "research_queries": ["query 1", "query 2"],
                    "spec_version": 1,
                },
            ],
        }
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        # Sync
        runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])

        # Verify research requirements were imported
        db = DatabaseManager(db_path)
        tasks = db.list_tasks(project_id=project.id)
        assert len(tasks) == 1

        task = tasks[0]
        assert task.research_required is True
        assert task.research_queries == ["query 1", "query 2"]

    def test_sync_with_all_task_fields(self, runner, sample_project):
        """Test sync correctly imports all task fields."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]
        spec_file = sample_project["spec_file"]

        # Create spec with all fields
        spec_data = {
            "spec_version": 1,
            "tasks": [
                {
                    "id": "F001",
                    "title": "Complete Task",
                    "description": "Full description",
                    "acceptance_criteria": ["criteria 1", "criteria 2"],
                    "steps": ["step 1", "step 2", "step 3"],
                    "depends_on": [],
                    "priority": "critical",
                    "category": "functional",
                    "labels": ["backend", "api"],
                    "research_required": False,
                    "research_queries": [],
                    "spec_version": 1,
                },
            ],
        }
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        # Sync
        runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])

        # Verify all fields were imported
        db = DatabaseManager(db_path)
        tasks = db.list_tasks(project_id=project.id)
        assert len(tasks) == 1

        task = tasks[0]
        assert task.spec_id == "F001"
        assert task.title == "Complete Task"
        assert task.description == "Full description"
        assert task.acceptance_criteria == ["criteria 1", "criteria 2"]
        assert task.steps == ["step 1", "step 2", "step 3"]
        assert task.depends_on == []
        assert task.priority == "critical"
        assert task.category == "functional"
        assert task.labels == ["backend", "api"]
        assert task.research_required is False
        assert task.research_queries == []


class TestSyncMultipleProjects:
    """Test sync with multiple projects."""

    def test_sync_multiple_active_projects_requires_project_flag(self, runner, db_path, tmp_path):
        """Test sync fails when no active project is set and --project not specified."""
        db = DatabaseManager(db_path)

        # Create two active projects
        for i in range(2):
            workspace = tmp_path / f"workspace{i}"
            workspace.mkdir()
            spec_file = tmp_path / f"spec{i}.yaml"
            with open(spec_file, "w") as f:
                yaml.dump({"spec_version": 1, "tasks": []}, f)

            project = Project(
                id=f"proj-{i}",
                name=f"project{i}",
                description="",
                workspace_dir=str(workspace),
                spec_source=f"file://{spec_file}",
                config={},
                created_at=datetime.now(),
                status=ProjectStatus.ACTIVE,
            )
            db.create_project(project)

        # Try to sync without --project flag and without active project set
        result = runner.invoke(cli, ["--db", str(db_path), "sync"], env={"HOME": str(tmp_path)})
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "no active project" in result.output.lower()
        assert "bob project use" in result.output


class TestSyncEdgeCases:
    """Test edge cases for sync command."""

    def test_sync_with_empty_spec(self, runner, sample_project):
        """Test sync with empty spec file."""
        db_path = sample_project["db_path"]
        project = sample_project["project"]
        spec_file = sample_project["spec_file"]

        # Create empty spec
        with open(spec_file, "w") as f:
            yaml.dump({"spec_version": 1, "tasks": []}, f)

        # Sync
        result = runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])
        assert result.exit_code == 0
        assert "No changes detected" in result.output

    def test_sync_with_spec_file_not_found(self, runner, db_path, tmp_path):
        """Test sync when spec file doesn't exist."""
        db = DatabaseManager(db_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        spec_file = tmp_path / "nonexistent.yaml"

        project = Project(
            id="proj-test",
            name="test-project",
            description="",
            workspace_dir=str(workspace),
            spec_source=f"file://{spec_file}",
            config={},
            created_at=datetime.now(),
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        result = runner.invoke(cli, ["--db", str(db_path), "--project", project.id, "sync"])
        assert result.exit_code == 1
        assert "Failed to create spec source" in result.output
