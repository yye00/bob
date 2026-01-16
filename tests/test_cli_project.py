"""Tests for bob.cli.project module (project management commands)."""

import tempfile
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from bob.cli.main import cli
from bob.cli.project import validate_project_name, create_workspace_structure
from bob.database.manager import DatabaseManager
from bob.models.base import ProjectStatus


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
