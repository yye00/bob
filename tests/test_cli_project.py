"""Tests for bob.cli.project module (project management commands)."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from bob.cli.main import cli
from bob.cli.project import validate_project_name, create_workspace_structure
from bob.database.manager import DatabaseManager
from bob.models.base import Project, ProjectStatus, Task, TaskStatus, Session, SessionStatus, AgentType
from datetime import datetime


class TestProjectNameValidation:
    """Test project name validation function."""

    def test_valid_simple_name(self) -> None:
        """Test simple valid project name."""
        assert validate_project_name("myapp")

    def test_valid_name_with_hyphens(self) -> None:
        """Test valid name with hyphens."""
        assert validate_project_name("my-app")
        assert validate_project_name("api-server-v2")

    def test_valid_name_with_numbers(self) -> None:
        """Test valid name with numbers."""
        assert validate_project_name("app2")
        assert validate_project_name("v2-app")
        assert validate_project_name("my-app-v2")

    def test_invalid_uppercase(self) -> None:
        """Test invalid name with uppercase letters."""
        assert not validate_project_name("MyApp")
        assert not validate_project_name("my-App")

    def test_invalid_start_with_number(self) -> None:
        """Test invalid name starting with number."""
        assert not validate_project_name("2app")
        assert not validate_project_name("123-app")

    def test_invalid_start_with_hyphen(self) -> None:
        """Test invalid name starting with hyphen."""
        assert not validate_project_name("-app")

    def test_invalid_end_with_hyphen(self) -> None:
        """Test invalid name ending with hyphen."""
        assert not validate_project_name("app-")

    def test_invalid_consecutive_hyphens(self) -> None:
        """Test invalid name with consecutive hyphens."""
        assert not validate_project_name("my--app")
        assert not validate_project_name("my---app")

    def test_invalid_special_characters(self) -> None:
        """Test invalid name with special characters."""
        assert not validate_project_name("my_app")
        assert not validate_project_name("my.app")
        assert not validate_project_name("my@app")
        assert not validate_project_name("my app")

    def test_empty_string(self) -> None:
        """Test empty string."""
        assert not validate_project_name("")


class TestWorkspaceStructure:
    """Test workspace structure creation."""

    def test_creates_workspace_directory(self, tmp_path: Path) -> None:
        """Test that workspace directory is created."""
        workspace = tmp_path / "workspace"
        create_workspace_structure(workspace, "proj-123", "test-app")

        assert workspace.exists()
        assert workspace.is_dir()

    def test_creates_bob_subdirectory(self, tmp_path: Path) -> None:
        """Test that .bob subdirectory is created."""
        workspace = tmp_path / "workspace"
        create_workspace_structure(workspace, "proj-123", "test-app")

        bob_dir = workspace / ".bob"
        assert bob_dir.exists()
        assert bob_dir.is_dir()

    def test_creates_logs_directory(self, tmp_path: Path) -> None:
        """Test that logs directory is created."""
        workspace = tmp_path / "workspace"
        create_workspace_structure(workspace, "proj-123", "test-app")

        logs_dir = workspace / ".bob" / "logs"
        assert logs_dir.exists()
        assert logs_dir.is_dir()

    def test_creates_state_directory(self, tmp_path: Path) -> None:
        """Test that state directory is created."""
        workspace = tmp_path / "workspace"
        create_workspace_structure(workspace, "proj-123", "test-app")

        state_dir = workspace / ".bob" / "state"
        assert state_dir.exists()
        assert state_dir.is_dir()

    def test_creates_project_yaml(self, tmp_path: Path) -> None:
        """Test that project.yaml is created."""
        workspace = tmp_path / "workspace"
        create_workspace_structure(workspace, "proj-123", "test-app")

        config_file = workspace / ".bob" / "project.yaml"
        assert config_file.exists()
        assert config_file.is_file()

    def test_project_yaml_structure(self, tmp_path: Path) -> None:
        """Test project.yaml has correct structure."""
        workspace = tmp_path / "workspace"
        project_id = "proj-123"
        project_name = "test-app"
        create_workspace_structure(workspace, project_id, project_name)

        config_file = workspace / ".bob" / "project.yaml"
        with open(config_file) as f:
            config = yaml.safe_load(f)

        # Check top-level keys
        assert "project" in config
        assert "agent" in config
        assert "escalation" in config
        assert "cost_limits" in config

        # Check project section
        assert config["project"]["id"] == project_id
        assert config["project"]["name"] == project_name
        assert "created_at" in config["project"]

        # Check agent section
        assert "coding" in config["agent"]
        assert "research" in config["agent"]

        # Check escalation section
        assert config["escalation"]["enabled"] is True

        # Check cost_limits section
        assert "per_session" in config["cost_limits"]
        assert "per_day" in config["cost_limits"]
        assert "per_project" in config["cost_limits"]

    def test_idempotent_creation(self, tmp_path: Path) -> None:
        """Test that creating workspace structure is idempotent."""
        workspace = tmp_path / "workspace"

        # Create twice
        create_workspace_structure(workspace, "proj-123", "test-app")
        create_workspace_structure(workspace, "proj-123", "test-app")

        # Should not raise error, directory should still exist
        assert workspace.exists()
        assert (workspace / ".bob").exists()


class TestProjectCreateCommand:
    """Test 'bob project create' command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_create_help(self) -> None:
        """Test project create help text."""
        result = self.runner.invoke(cli, ["project", "create", "--help"])
        assert result.exit_code == 0
        assert "Create a new project" in result.output
        assert "NAME" in result.output
        assert "WORKSPACE" in result.output
        assert "SPEC_SOURCE" in result.output

    def test_create_minimal_project(self, tmp_path: Path) -> None:
        """Test creating a minimal project."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            assert result.exit_code == 0
            assert "Created project 'test-app'" in result.output
            assert workspace.exists()
            assert (workspace / ".bob").exists()
            assert (workspace / ".bob" / "project.yaml").exists()

            # Verify in database
            db = DatabaseManager(db_path)
            projects = db.list_projects()
            assert len(projects) == 1
            assert projects[0].name == "test-app"
            assert projects[0].spec_source == "file://spec.yaml"
            assert projects[0].status == ProjectStatus.ACTIVE

    def test_create_project_with_description(self, tmp_path: Path) -> None:
        """Test creating project with description."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            result = self.runner.invoke(
                cli,
                [
                    "--db", str(db_path),
                    "project", "create",
                    "test-app", str(workspace), "file://spec.yaml",
                    "-d", "Test application"
                ]
            )

            assert result.exit_code == 0

            # Verify description in database
            db = DatabaseManager(db_path)
            projects = db.list_projects()
            assert len(projects) == 1
            assert projects[0].description == "Test application"

    def test_create_project_with_custom_config(self, tmp_path: Path) -> None:
        """Test creating project with custom config file."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")
            config_file = Path("custom.yaml")

            # Create custom config
            custom_config = {"custom_key": "custom_value"}
            with open(config_file, "w") as f:
                yaml.dump(custom_config, f)

            result = self.runner.invoke(
                cli,
                [
                    "--db", str(db_path),
                    "project", "create",
                    "test-app", str(workspace), "file://spec.yaml",
                    "--config", str(config_file)
                ]
            )

            assert result.exit_code == 0

            # Verify config in database
            db = DatabaseManager(db_path)
            projects = db.list_projects()
            assert len(projects) == 1
            assert projects[0].config == custom_config

    def test_create_project_invalid_name(self, tmp_path: Path) -> None:
        """Test creating project with invalid name."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Try with uppercase
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "TestApp", str(workspace), "file://spec.yaml"]
            )

            assert result.exit_code == 1
            assert "Invalid project name" in result.output

    def test_create_project_duplicate_name(self, tmp_path: Path) -> None:
        """Test creating project with duplicate name."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace1 = Path("workspace1")
            workspace2 = Path("workspace2")

            # Create first project
            result1 = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace1), "file://spec.yaml"]
            )
            assert result1.exit_code == 0

            # Try to create second project with same name
            result2 = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace2), "file://spec.yaml"]
            )

            assert result2.exit_code == 1
            assert "already exists" in result2.output

    def test_create_project_with_different_spec_sources(self, tmp_path: Path) -> None:
        """Test creating projects with different spec sources."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            # File spec source
            result1 = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "app1", "workspace1", "file://spec.yaml"]
            )
            assert result1.exit_code == 0

            # GitHub spec source
            result2 = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "app2", "workspace2", "github://org/repo/issues"]
            )
            assert result2.exit_code == 0

            # Verify both in database
            db = DatabaseManager(db_path)
            projects = db.list_projects()
            assert len(projects) == 2
            assert projects[0].spec_source == "github://org/repo/issues"  # Newest first
            assert projects[1].spec_source == "file://spec.yaml"

    def test_create_project_workspace_absolute_path(self, tmp_path: Path) -> None:
        """Test creating project with absolute workspace path."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "absolute-workspace"

            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            assert result.exit_code == 0
            assert workspace.exists()

            # Verify absolute path stored in database
            db = DatabaseManager(db_path)
            projects = db.list_projects()
            assert len(projects) == 1
            assert Path(projects[0].workspace_dir).is_absolute()

    def test_create_project_next_steps_shown(self, tmp_path: Path) -> None:
        """Test that next steps are shown after creation."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            assert result.exit_code == 0
            assert "Next steps:" in result.output
            assert "bob project use test-app" in result.output
            assert "bob sync" in result.output
            assert "bob run" in result.output

    def test_create_project_output_format(self, tmp_path: Path) -> None:
        """Test the output format includes all key information."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            assert result.exit_code == 0
            # Should show project ID
            assert "proj-" in result.output
            # Should show workspace path
            assert "Workspace:" in result.output
            # Should show spec source
            assert "Spec source:" in result.output
            # Should show config path
            assert "Config:" in result.output
            assert "project.yaml" in result.output


class TestProjectListCommand:
    """Test 'bob project list' command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_list_help(self) -> None:
        """Test project list help text."""
        result = self.runner.invoke(cli, ["project", "list", "--help"])
        assert result.exit_code == 0
        assert "List all projects" in result.output

    def test_list_no_projects(self, tmp_path: Path) -> None:
        """Test listing when no projects exist."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            result = self.runner.invoke(cli, ["--db", str(db_path), "project", "list"])

            assert result.exit_code == 0
            assert "No projects found" in result.output

    def test_list_single_project(self, tmp_path: Path) -> None:
        """Test listing with a single project."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            # List projects
            result = self.runner.invoke(cli, ["--db", str(db_path), "project", "list"])

            assert result.exit_code == 0
            assert "test-app" in result.output
            assert "proj-" in result.output
            assert "Total: 1 project(s)" in result.output

    def test_list_multiple_projects(self, tmp_path: Path) -> None:
        """Test listing with multiple projects."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            # Create multiple projects
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "app1", "workspace1", "file://spec1.yaml"]
            )
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "app2", "workspace2", "file://spec2.yaml"]
            )
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "app3", "workspace3", "file://spec3.yaml"]
            )

            # List projects
            result = self.runner.invoke(cli, ["--db", str(db_path), "project", "list"])

            assert result.exit_code == 0
            assert "app1" in result.output
            assert "app2" in result.output
            assert "app3" in result.output
            assert "Total: 3 project(s)" in result.output

    def test_list_with_status_filter(self, tmp_path: Path) -> None:
        """Test listing with status filter."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            db = DatabaseManager(db_path)

            # Create projects with different statuses
            project1 = Project(
                id="proj-1",
                name="active-app",
                description="",
                workspace_dir=str(tmp_path / "w1"),
                spec_source="file://spec.yaml",
                status=ProjectStatus.ACTIVE,
            )
            project2 = Project(
                id="proj-2",
                name="paused-app",
                description="",
                workspace_dir=str(tmp_path / "w2"),
                spec_source="file://spec.yaml",
                status=ProjectStatus.PAUSED,
            )
            project3 = Project(
                id="proj-3",
                name="completed-app",
                description="",
                workspace_dir=str(tmp_path / "w3"),
                spec_source="file://spec.yaml",
                status=ProjectStatus.COMPLETED,
            )

            db.create_project(project1)
            db.create_project(project2)
            db.create_project(project3)

            # List only active projects
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "list", "--status", "active"]
            )

            assert result.exit_code == 0
            assert "active-app" in result.output
            assert "paused-app" not in result.output
            assert "completed-app" not in result.output

    def test_list_json_output(self, tmp_path: Path) -> None:
        """Test JSON output format."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml", "-d", "Test project"]
            )

            # List with JSON output
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "list", "--json-output"],
            )

            assert result.exit_code == 0

            # Extract JSON from output (filter out non-JSON lines like migration messages)
            # The JSON starts with { and we need to track braces to find the end
            json_lines = []
            brace_count = 0
            in_json = False

            for line in result.output.split('\n'):
                if not in_json and line.strip().startswith('{'):
                    in_json = True

                if in_json:
                    json_lines.append(line)
                    brace_count += line.count('{') - line.count('}')

                    # When brace count returns to 0, JSON is complete
                    if brace_count == 0:
                        break

            json_output = '\n'.join(json_lines)
            data = json.loads(json_output)
            assert "projects" in data
            assert len(data["projects"]) == 1

            project = data["projects"][0]
            assert project["name"] == "test-app"
            assert project["description"] == "Test project"
            assert project["status"] == "active"
            assert "id" in project
            assert "workspace_dir" in project
            assert "spec_source" in project
            assert "tasks" in project
            assert "cost" in project

    def test_list_json_output_no_projects(self, tmp_path: Path) -> None:
        """Test JSON output with no projects."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "list", "--json-output"],
            )

            assert result.exit_code == 0

            # Extract JSON from output (filter out non-JSON lines like migration messages)
            # The JSON starts with { and we need to track braces to find the end
            json_lines = []
            brace_count = 0
            in_json = False

            for line in result.output.split('\n'):
                if not in_json and line.strip().startswith('{'):
                    in_json = True

                if in_json:
                    json_lines.append(line)
                    brace_count += line.count('{') - line.count('}')

                    # When brace count returns to 0, JSON is complete
                    if brace_count == 0:
                        break

            json_output = '\n'.join(json_lines)
            data = json.loads(json_output)
            assert data == {"projects": []}

    def test_list_with_task_statistics(self, tmp_path: Path) -> None:
        """Test that task statistics are displayed."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            db = DatabaseManager(db_path)

            # Create a project
            project = Project(
                id="proj-1",
                name="test-app",
                description="",
                workspace_dir=str(tmp_path / "workspace"),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # Create tasks
            task1 = Task(
                id="task-1",
                project_id="proj-1",
                spec_id="F001",
                title="Task 1",
                description="Test task 1",
                status=TaskStatus.COMPLETED,
            )
            task2 = Task(
                id="task-2",
                project_id="proj-1",
                spec_id="F002",
                title="Task 2",
                description="Test task 2",
                status=TaskStatus.PENDING,
            )
            task3 = Task(
                id="task-3",
                project_id="proj-1",
                spec_id="F003",
                title="Task 3",
                description="Test task 3",
                status=TaskStatus.COMPLETED,
            )

            db.create_task(task1)
            db.create_task(task2)
            db.create_task(task3)

            # List projects
            result = self.runner.invoke(cli, ["--db", str(db_path), "project", "list"])

            assert result.exit_code == 0
            assert "2/3" in result.output  # 2 completed out of 3 total

    def test_list_with_cost_statistics(self, tmp_path: Path) -> None:
        """Test that cost statistics are displayed."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            db = DatabaseManager(db_path)

            # Create a project
            project = Project(
                id="proj-1",
                name="test-app",
                description="",
                workspace_dir=str(tmp_path / "workspace"),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # Create sessions with costs
            session1 = Session(
                id="sess-1",
                project_id="proj-1",
                task_id=None,
                agent_type=AgentType.CODING,
                model="claude-sonnet-4",
                status=SessionStatus.COMPLETED,
                cost=1.50,
            )
            session2 = Session(
                id="sess-2",
                project_id="proj-1",
                task_id=None,
                agent_type=AgentType.CODING,
                model="claude-sonnet-4",
                status=SessionStatus.COMPLETED,
                cost=2.75,
            )

            db.create_session(session1)
            db.create_session(session2)

            # List projects
            result = self.runner.invoke(cli, ["--db", str(db_path), "project", "list"])

            assert result.exit_code == 0
            assert "$4.25" in result.output  # Total cost

    def test_list_table_headers(self, tmp_path: Path) -> None:
        """Test that table headers are displayed."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            # List projects
            result = self.runner.invoke(cli, ["--db", str(db_path), "project", "list"])

            assert result.exit_code == 0
            assert "ID" in result.output
            assert "Name" in result.output
            assert "Status" in result.output
            assert "Tasks" in result.output
            assert "Cost" in result.output
            assert "Description" in result.output


class TestProjectUseCommand:
    """Test 'bob project use' command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_use_help(self) -> None:
        """Test that use command shows help."""
        result = self.runner.invoke(cli, ["project", "use", "--help"])
        assert result.exit_code == 0
        assert "Set the active project" in result.output
        assert "NAME" in result.output

    def test_use_by_name(self, tmp_path: Path) -> None:
        """Test activating a project by name."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")
            state_dir = Path(".bob-state")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            # Use the project by name
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "use", "test-app"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "✓ Activated project: test-app" in result.output
            assert "Next steps:" in result.output

            # Verify state file was created
            state_file = tmp_path / ".bob" / "state.json"
            assert state_file.exists()

            # Verify state file contains the project ID
            with open(state_file) as f:
                state = json.load(f)
                assert state["active_project"] is not None
                assert state["active_project"].startswith("proj-")

    def test_use_by_id(self, tmp_path: Path) -> None:
        """Test activating a project by ID."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            create_result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            # Extract project ID from output
            # Output format: "✓ Created project 'test-app' (proj-XXXXXXXX)"
            import re
            match = re.search(r"proj-[a-f0-9]{8}", create_result.output)
            assert match
            project_id = match.group(0)

            # Use the project by ID
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "use", project_id],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert f"✓ Activated project: test-app ({project_id})" in result.output

    def test_use_nonexistent_project(self, tmp_path: Path) -> None:
        """Test using a project that doesn't exist."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            # Try to use nonexistent project
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "use", "nonexistent"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 1
            assert "✗ Project not found: nonexistent" in result.output
            assert "Available projects:" in result.output

    def test_use_shows_available_projects_on_error(self, tmp_path: Path) -> None:
        """Test that use command shows available projects when project not found."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create two projects
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "app1", str(workspace / "app1"), "file://spec.yaml"]
            )
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "app2", str(workspace / "app2"), "file://spec.yaml"]
            )

            # Try to use nonexistent project
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "use", "nonexistent"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 1
            assert "app1" in result.output
            assert "app2" in result.output

    def test_use_updates_state_file(self, tmp_path: Path) -> None:
        """Test that use command updates state file correctly."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create two projects
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "app1", str(workspace / "app1"), "file://spec.yaml"]
            )
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "app2", str(workspace / "app2"), "file://spec.yaml"]
            )

            # Use first project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "use", "app1"],
                env={"HOME": str(tmp_path)}
            )

            # Verify state file
            state_file = tmp_path / ".bob" / "state.json"
            with open(state_file) as f:
                state = json.load(f)
                first_project_id = state["active_project"]

            # Use second project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "use", "app2"],
                env={"HOME": str(tmp_path)}
            )

            # Verify state file was updated
            with open(state_file) as f:
                state = json.load(f)
                second_project_id = state["active_project"]

            assert first_project_id != second_project_id

    def test_use_displays_project_info(self, tmp_path: Path) -> None:
        """Test that use command displays project information."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            # Use the project
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "use", "test-app"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Workspace:" in result.output
            assert "Spec source: file://spec.yaml" in result.output

    def test_use_shows_next_steps(self, tmp_path: Path) -> None:
        """Test that use command shows next steps."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            # Use the project
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "use", "test-app"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Next steps:" in result.output
            assert "bob sync" in result.output
            assert "bob task list" in result.output
            assert "bob run" in result.output


class TestProjectStatusCommand:
    """Test 'bob project status' command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_status_help(self) -> None:
        """Test that status command shows help."""
        result = self.runner.invoke(cli, ["project", "status", "--help"])
        assert result.exit_code == 0
        assert "Show detailed project status" in result.output
        assert "NAME" in result.output

    def test_status_no_active_project(self, tmp_path: Path) -> None:
        """Test status command with no active project."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "status"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 1
            assert "No active project found" in result.output
            assert "bob project use" in result.output

    def test_status_by_name(self, tmp_path: Path) -> None:
        """Test status command for project by name."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml", "-d", "Test application"]
            )

            # Get status by name
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "status", "test-app"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Project: test-app" in result.output
            assert "Test application" in result.output
            assert "Details:" in result.output
            assert "Tasks:" in result.output
            assert "Costs:" in result.output

    def test_status_active_project(self, tmp_path: Path) -> None:
        """Test status command uses active project."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create and activate a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "use", "test-app"],
                env={"HOME": str(tmp_path)}
            )

            # Get status without specifying project
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "status"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Project: test-app" in result.output

    def test_status_displays_project_details(self, tmp_path: Path) -> None:
        """Test that status displays all project details."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml", "-d", "My description"]
            )

            # Get status
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "status", "test-app"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Status: active" in result.output
            assert "Description: My description" in result.output
            assert f"Workspace: {workspace.resolve()}" in result.output
            assert "Spec source: file://spec.yaml" in result.output
            assert "Created:" in result.output

    def test_status_displays_task_breakdown(self, tmp_path: Path) -> None:
        """Test that status displays task breakdown."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            db = DatabaseManager(db_path)
            workspace = Path("workspace")

            # Create a project
            workspace.mkdir()
            project = Project(
                id="proj-test",
                name="test-app",
                description="",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
                config={},
                created_at=datetime.now(),
                status=ProjectStatus.ACTIVE,
            )
            db.create_project(project)

            # Add tasks with different statuses
            for i, status in enumerate([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.FAILED]):
                task = Task(
                    id=f"task-{i}",
                    project_id=project.id,
                    spec_id=f"T{i}",
                    title=f"Task {i}",
                    description="",
                    status=status,
                    priority="medium",
                )
                db.create_task(task)

            # Get status
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "status", "test-app"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Total: 4" in result.output
            assert "Pending: 1" in result.output
            assert "In progress: 1" in result.output
            assert "Completed: 1" in result.output
            assert "Failed: 1" in result.output

    def test_status_displays_cost_summary(self, tmp_path: Path) -> None:
        """Test that status displays cost summary."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            db = DatabaseManager(db_path)
            workspace = Path("workspace")

            # Create a project
            workspace.mkdir()
            project = Project(
                id="proj-test",
                name="test-app",
                description="",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
                config={},
                created_at=datetime.now(),
                status=ProjectStatus.ACTIVE,
            )
            db.create_project(project)

            # Add sessions with costs
            sessions = [
                Session(
                    id="sess-1",
                    project_id=project.id,
                    task_id=None,
                    agent_type=AgentType.CODING,
                    model="claude-sonnet-4",
                    started_at=datetime.now(),
                    status=SessionStatus.COMPLETED,
                    cost=1.50,
                ),
                Session(
                    id="sess-2",
                    project_id=project.id,
                    task_id=None,
                    agent_type=AgentType.RESEARCH,
                    model="claude-sonnet-4",
                    started_at=datetime.now(),
                    status=SessionStatus.COMPLETED,
                    cost=0.75,
                ),
            ]
            for session in sessions:
                db.create_session(session)

            # Get status
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "status", "test-app"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Total: $2.25" in result.output
            assert "By model:" in result.output
            assert "claude-sonnet-4: $2.25" in result.output
            assert "By agent:" in result.output
            assert "coding: $1.50" in result.output
            assert "research: $0.75" in result.output

    def test_status_displays_recent_activity(self, tmp_path: Path) -> None:
        """Test that status displays recent activity."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            db = DatabaseManager(db_path)
            workspace = Path("workspace")

            # Create a project
            workspace.mkdir()
            project = Project(
                id="proj-test",
                name="test-app",
                description="",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
                config={},
                created_at=datetime.now(),
                status=ProjectStatus.ACTIVE,
            )
            db.create_project(project)

            # Add a session
            session = Session(
                id="sess-test",
                project_id=project.id,
                task_id=None,
                agent_type=AgentType.CODING,
                model="claude-sonnet-4",
                started_at=datetime.now(),
                status=SessionStatus.COMPLETED,
                cost=1.50,
            )
            db.create_session(session)

            # Get status
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "status", "test-app"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Recent activity:" in result.output
            assert "sess-test" in result.output
            assert "coding" in result.output
            assert "$1.50" in result.output

    def test_status_json_output(self, tmp_path: Path) -> None:
        """Test status command with JSON output."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml", "-d", "Test app"]
            )

            # Get status with JSON output
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "status", "test-app", "--json-output"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0

            # Parse JSON (extract JSON from mixed output with database messages)
            import re
            json_match = re.search(r'\{[\s\S]*\}', result.output)
            assert json_match, f"No JSON found in output: {result.output}"
            output = json.loads(json_match.group())

            # Verify structure
            assert "project" in output
            assert output["project"]["name"] == "test-app"
            assert output["project"]["description"] == "Test app"
            assert "tasks" in output
            assert "total" in output["tasks"]
            assert "pending" in output["tasks"]
            assert "completed" in output["tasks"]
            assert "costs" in output
            assert "total" in output["costs"]
            assert "recent_sessions" in output

    def test_status_no_tasks_or_sessions(self, tmp_path: Path) -> None:
        """Test status with project that has no tasks or sessions."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"]
            )

            # Get status
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "status", "test-app"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Total: 0" in result.output
            assert "Total: $0.00" in result.output
            assert "No sessions yet" in result.output

    def test_status_nonexistent_project(self, tmp_path: Path) -> None:
        """Test status for nonexistent project."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "status", "nonexistent"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 1
            assert "Project not found: nonexistent" in result.output


class TestProjectDeleteCommand:
    """Test project delete command."""

    def setup_method(self) -> None:
        """Set up test runner."""
        self.runner = CliRunner()

    def test_delete_help(self) -> None:
        """Test delete command help text."""
        result = self.runner.invoke(cli, ["project", "delete", "--help"])

        assert result.exit_code == 0
        assert "Delete a project and all associated data" in result.output
        assert "--yes" in result.output
        assert "--delete-workspace" in result.output

    def test_delete_nonexistent_project(self, tmp_path: Path) -> None:
        """Test deleting a project that doesn't exist."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "delete", "nonexistent", "--yes"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 1
            assert "Project not found: nonexistent" in result.output

    def test_delete_with_confirmation_skip(self, tmp_path: Path) -> None:
        """Test deleting a project with --yes flag."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project first
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"],
                env={"HOME": str(tmp_path)}
            )

            # Delete with --yes flag
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "delete", "test-app", "--yes"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Project deletion complete" in result.output
            assert "Deleted project from database: test-app" in result.output

    def test_delete_with_confirmation_prompt(self, tmp_path: Path) -> None:
        """Test deleting a project with confirmation prompt."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project first
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"],
                env={"HOME": str(tmp_path)}
            )

            # Delete with confirmation (input matches)
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "delete", "test-app"],
                input="test-app\n",
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Project deletion complete" in result.output

    def test_delete_cancels_on_wrong_confirmation(self, tmp_path: Path) -> None:
        """Test that deletion is cancelled if confirmation doesn't match."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project first
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"],
                env={"HOME": str(tmp_path)}
            )

            # Delete with wrong confirmation
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "delete", "test-app"],
                input="wrong-name\n",
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Deletion cancelled" in result.output

            # Verify project still exists
            list_result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "list"],
                env={"HOME": str(tmp_path)}
            )
            assert "test-app" in list_result.output

    def test_delete_with_workspace(self, tmp_path: Path) -> None:
        """Test deleting a project with workspace directory deletion."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project first
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"],
                env={"HOME": str(tmp_path)}
            )

            # Verify workspace exists
            assert workspace.exists()

            # Delete with --delete-workspace
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "delete", "test-app", "--yes", "--delete-workspace"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Deleted workspace directory" in result.output

            # Verify workspace was deleted
            assert not workspace.exists()

    def test_delete_displays_project_details(self, tmp_path: Path) -> None:
        """Test that delete command displays project details before deletion."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml", "-d", "Test description"],
                env={"HOME": str(tmp_path)}
            )

            # Delete and check output
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "delete", "test-app", "--yes"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Project to delete: test-app" in result.output
            assert "Description: Test description" in result.output
            assert "Tasks: 0" in result.output
            assert "Sessions: 0" in result.output

    def test_delete_by_project_id(self, tmp_path: Path) -> None:
        """Test deleting a project by ID instead of name."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = Path("workspace")
            db = DatabaseManager(db_path)

            # Create a project
            self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.yaml"],
                env={"HOME": str(tmp_path)}
            )

            # Get the project ID
            projects = db.list_projects()
            project_id = projects[0].id

            # Delete by ID
            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "project", "delete", project_id, "--yes"],
                env={"HOME": str(tmp_path)}
            )

            assert result.exit_code == 0
            assert "Project deletion complete" in result.output
