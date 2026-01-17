"""Tests for the init CLI command."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.config import DEFAULT_CONFIG


class TestInitCommand:
    """Tests for the 'bob init' command."""

    def test_init_creates_directory_structure(self, tmp_path, monkeypatch):
        """Test that init creates all required directories."""
        # Set HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert "Initializing BOB environment" in result.output

        # Verify directory structure
        bob_home = tmp_path / ".bob"
        assert bob_home.exists()
        assert (bob_home / "plugins").exists()
        assert (bob_home / "cache").exists()
        assert (bob_home / "logs").exists()

    def test_init_creates_config_file(self, tmp_path, monkeypatch):
        """Test that init creates config.yaml with default values."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0

        # Verify config file
        config_path = tmp_path / ".bob" / "config.yaml"
        assert config_path.exists()

        # Verify config content
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert "models" in config
        assert "api" in config
        assert "database" in config
        assert "logging" in config
        assert "limits" in config
        assert "escalation" in config

    def test_init_creates_database(self, tmp_path, monkeypatch):
        """Test that init creates and initializes the database."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0

        # Verify database file
        db_path = tmp_path / ".bob" / "bob.db"
        assert db_path.exists()

        # Verify database has schema
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Should have all required tables
        assert "projects" in tables
        assert "tasks" in tables
        assert "sessions" in tables

    def test_init_displays_success_message(self, tmp_path, monkeypatch):
        """Test that init displays helpful success message."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert "BOB environment initialized successfully" in result.output
        assert "Configuration location: ~/.bob/config.yaml" in result.output
        assert "Database location: ~/.bob/bob.db" in result.output
        assert "Next steps:" in result.output
        assert "Set your API key" in result.output
        assert "Create a project" in result.output

    def test_init_fails_if_already_initialized(self, tmp_path, monkeypatch):
        """Test that init fails if ~/.bob already exists (without --force)."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()

        # First init should succeed
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0

        # Second init should fail
        result = runner.invoke(cli, ["init"])
        assert result.exit_code != 0
        assert "already initialized" in result.output
        assert "--force" in result.output

    def test_init_force_reinitializes(self, tmp_path, monkeypatch):
        """Test that init --force reinitializes existing installation."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()

        # First init
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0

        # Modify config to test that force recreates it
        config_path = tmp_path / ".bob" / "config.yaml"
        config_path.write_text("modified: true\n")

        # Force reinit
        result = runner.invoke(cli, ["init", "--force"])
        assert result.exit_code == 0

        # Config should be back to defaults
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert "modified" not in config
        assert "models" in config

    def test_init_db_only(self, tmp_path, monkeypatch):
        """Test that init --db-only only initializes database."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--db-only"])

        assert result.exit_code == 0

        # Database should exist
        db_path = tmp_path / ".bob" / "bob.db"
        assert db_path.exists()

        # Config should not exist
        config_path = tmp_path / ".bob" / "config.yaml"
        assert not config_path.exists()

        # Directories should still be created
        bob_home = tmp_path / ".bob"
        assert bob_home.exists()

    def test_init_config_only(self, tmp_path, monkeypatch):
        """Test that init --config-only only creates config file."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--config-only"])

        assert result.exit_code == 0

        # Config should exist
        config_path = tmp_path / ".bob" / "config.yaml"
        assert config_path.exists()

        # Database should not exist
        db_path = tmp_path / ".bob" / "bob.db"
        assert not db_path.exists()

    def test_init_with_force_removes_old_database(self, tmp_path, monkeypatch):
        """Test that init --force removes old database before reinit."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()

        # First init
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0

        db_path = tmp_path / ".bob" / "bob.db"

        # Add some data to database
        from bob.database.manager import DatabaseManager
        from bob.models.base import Project, ProjectStatus
        db = DatabaseManager(db_path)
        project = Project(
            id="test-001",
            name="test-project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
            description="Test project",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Verify project exists in database
        projects_before = db.list_projects()
        assert len(projects_before) == 1
        assert projects_before[0].name == "test-project"

        # Force reinit
        result = runner.invoke(cli, ["init", "--force"])
        assert result.exit_code == 0
        assert "Removed existing database" in result.output

        # Create new database manager to verify fresh database
        db2 = DatabaseManager(db_path)
        projects_after = db2.list_projects()

        # Database should be empty after force reinit
        assert len(projects_after) == 0

    def test_init_creates_all_subdirectories(self, tmp_path, monkeypatch):
        """Test that all required subdirectories are created."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0

        bob_home = tmp_path / ".bob"

        # All subdirectories should exist
        required_dirs = ["plugins", "cache", "logs"]
        for dir_name in required_dirs:
            dir_path = bob_home / dir_name
            assert dir_path.exists(), f"Missing directory: {dir_name}"
            assert dir_path.is_dir(), f"Not a directory: {dir_name}"

    def test_init_config_has_all_required_sections(self, tmp_path, monkeypatch):
        """Test that config file has all required sections."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0

        config_path = tmp_path / ".bob" / "config.yaml"

        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Check all required sections
        required_sections = ["models", "api", "database", "logging", "limits", "escalation"]
        for section in required_sections:
            assert section in config, f"Missing config section: {section}"

        # Check specific keys in sections
        assert "default" in config["models"]
        assert "escalation" in config["models"]
        assert "anthropic_api_key" in config["api"]
        assert "max_cost_per_project" in config["limits"]
        assert "max_attempts_per_model" in config["escalation"]

    def test_init_database_has_schema(self, tmp_path, monkeypatch):
        """Test that database is initialized with proper schema."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0

        db_path = tmp_path / ".bob" / "bob.db"

        import sqlite3
        conn = sqlite3.connect(db_path)

        # Check for required tables
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}

        required_tables = {"projects", "tasks", "sessions"}
        assert required_tables.issubset(tables), f"Missing tables: {required_tables - tables}"

        # Check projects table structure
        cursor = conn.execute("PRAGMA table_info(projects)")
        project_columns = {row[1] for row in cursor.fetchall()}
        assert "id" in project_columns
        assert "name" in project_columns
        assert "workspace_dir" in project_columns
        assert "status" in project_columns

        # Check tasks table structure
        cursor = conn.execute("PRAGMA table_info(tasks)")
        task_columns = {row[1] for row in cursor.fetchall()}
        assert "id" in task_columns
        assert "project_id" in task_columns
        assert "spec_id" in task_columns
        assert "status" in task_columns

        # Check sessions table structure
        cursor = conn.execute("PRAGMA table_info(sessions)")
        session_columns = {row[1] for row in cursor.fetchall()}
        assert "id" in session_columns
        assert "project_id" in session_columns
        assert "task_id" in session_columns
        assert "status" in session_columns

        conn.close()

    def test_init_output_formatting(self, tmp_path, monkeypatch):
        """Test that init command output is well-formatted and helpful."""
        monkeypatch.setenv("HOME", str(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0

        output = result.output

        # Check for emoji and formatting
        assert "🤖" in output
        assert "✓" in output
        assert "✅" in output

        # Check for key information
        assert "Created" in output
        assert "Initialized database" in output
        assert "configuration" in output.lower()

        # Check for helpful next steps
        assert "ANTHROPIC_API_KEY" in output
        assert "bob project create" in output
        assert "bob run" in output
        assert "bob --help" in output
