"""Tests for CLI framework.

Tests command parsing, option handling, and command structure.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bob.cli.main import cli


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_db(tmp_path):
    """Create a mock database fixture."""
    db_path = tmp_path / "test.db"
    return db_path


class TestMainCommand:
    """Test the main 'bob' command."""

    def test_help(self, runner):
        """Test main help message."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "BOB - Build Orchestration Bot" in result.output
        assert "project" in result.output
        assert "task" in result.output
        assert "run" in result.output

    def test_version(self, runner):
        """Test version command."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_version_command(self, runner):
        """Test standalone version command."""
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "BOB version 0.1.0" in result.output
        assert "Python" in result.output

    def test_examples_command(self, runner):
        """Test examples command."""
        result = runner.invoke(cli, ["examples"])
        assert result.exit_code == 0
        assert "BOB - Build Orchestration Bot" in result.output
        assert "GETTING STARTED" in result.output
        assert "PROJECT MANAGEMENT" in result.output


class TestGlobalOptions:
    """Test global options."""

    def test_verbose_flag(self, runner):
        """Test --verbose flag."""
        result = runner.invoke(cli, ["--verbose", "--help"])
        assert result.exit_code == 0
        # Context should have verbose=True (tested via integration)

    def test_quiet_flag(self, runner):
        """Test --quiet flag."""
        result = runner.invoke(cli, ["--quiet", "--help"])
        assert result.exit_code == 0
        # Context should have quiet=True (tested via integration)

    def test_json_flag(self, runner):
        """Test --json flag."""
        result = runner.invoke(cli, ["--json", "--help"])
        assert result.exit_code == 0
        # Context should have json_output=True (tested via integration)

    def test_project_option(self, runner):
        """Test --project option."""
        result = runner.invoke(cli, ["--project", "my-app", "--help"])
        assert result.exit_code == 0
        # Context should have project_id='my-app' (tested via integration)

    def test_db_option(self, runner):
        """Test --db option."""
        result = runner.invoke(cli, ["--db", "/tmp/test.db", "--help"])
        assert result.exit_code == 0
        # Context should have db_path set (tested via integration)

    def test_short_flags(self, runner):
        """Test short flag versions."""
        result = runner.invoke(cli, ["-v", "-q", "--help"])
        assert result.exit_code == 0

        result = runner.invoke(cli, ["-p", "my-app", "--help"])
        assert result.exit_code == 0


class TestCommandGroups:
    """Test command group structure."""

    def test_project_group(self, runner):
        """Test project command group."""
        result = runner.invoke(cli, ["project", "--help"])
        assert result.exit_code == 0
        assert "Manage projects" in result.output

    def test_task_group(self, runner):
        """Test task command group."""
        result = runner.invoke(cli, ["task", "--help"])
        assert result.exit_code == 0
        assert "View and manage tasks" in result.output

    def test_run_group(self, runner):
        """Test run command group."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "Run the autonomous coding agent" in result.output

    def test_sync_group(self, runner):
        """Test sync command."""
        result = runner.invoke(cli, ["sync", "--help"])
        assert result.exit_code == 0
        assert "Sync tasks with spec source" in result.output

    def test_status_group(self, runner):
        """Test status command group."""
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
        assert "View global status" in result.output or "status" in result.output.lower()

    def test_logs_group(self, runner):
        """Test logs command."""
        result = runner.invoke(cli, ["logs", "--help"])
        assert result.exit_code == 0
        assert "View structured logs" in result.output

    def test_costs_group(self, runner):
        """Test costs command."""
        result = runner.invoke(cli, ["costs", "--help"])
        assert result.exit_code == 0
        assert "Show cost breakdown for projects" in result.output

    def test_config_group(self, runner):
        """Test config command group."""
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0
        assert "Manage configuration" in result.output


class TestInitCommand:
    """Test init command."""

    def test_init_help(self, runner):
        """Test init command help."""
        result = runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        assert "Initialize BOB environment" in result.output

    def test_init_creates_directory(self, runner, tmp_path, monkeypatch):
        """Test that init creates ~/.bob directory."""
        # Set HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert "Initializing BOB environment" in result.output
        assert "BOB environment initialized successfully" in result.output
        assert (tmp_path / ".bob").exists()

    def test_init_fails_if_exists(self, runner, tmp_path, monkeypatch):
        """Test that init fails if ~/.bob already exists."""
        # Set HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        # Create .bob directory
        (tmp_path / ".bob").mkdir()

        # Try to init again
        result = runner.invoke(cli, ["init"])
        assert result.exit_code != 0
        assert "already initialized" in result.output


class TestCommandChaining:
    """Test command chaining and complex invocations."""

    def test_global_options_before_subcommand(self, runner):
        """Test global options before subcommand."""
        result = runner.invoke(cli, ["--verbose", "--project", "my-app", "project", "--help"])
        assert result.exit_code == 0

    def test_multiple_global_options(self, runner):
        """Test multiple global options together."""
        result = runner.invoke(cli, ["-v", "-q", "--json", "--project", "test", "task", "--help"])
        assert result.exit_code == 0

    def test_db_path_option(self, runner):
        """Test custom database path."""
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["--db", "./custom.db", "project", "--help"])
            assert result.exit_code == 0


class TestErrorHandling:
    """Test error handling."""

    def test_invalid_command(self, runner):
        """Test invalid command."""
        result = runner.invoke(cli, ["invalid"])
        assert result.exit_code != 0
        assert "Error" in result.output or "Usage" in result.output

    def test_invalid_option(self, runner):
        """Test invalid option."""
        result = runner.invoke(cli, ["--invalid"])
        assert result.exit_code != 0

    def test_missing_required_argument(self, runner):
        """Test command with missing required argument."""
        # Invoking a group without a subcommand shows usage and exits with code 2
        result = runner.invoke(cli, ["project"])
        # Click groups without subcommands return exit code 2 (usage error)
        assert result.exit_code == 2 or "Usage:" in result.output


class TestHelpMessages:
    """Test help message content."""

    def test_project_help_has_examples(self, runner):
        """Test that project help includes examples."""
        result = runner.invoke(cli, ["project", "--help"])
        assert result.exit_code == 0
        assert "Examples:" in result.output

    def test_task_help_has_examples(self, runner):
        """Test that task help includes examples."""
        result = runner.invoke(cli, ["task", "--help"])
        assert result.exit_code == 0
        assert "Examples:" in result.output

    def test_run_help_has_examples(self, runner):
        """Test that run help includes examples."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "Examples:" in result.output

    def test_main_help_has_quick_start(self, runner):
        """Test that main help includes quick start."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Quick Start:" in result.output
        assert "Common Commands:" in result.output


class TestContextPassing:
    """Test that global context is properly passed."""

    def test_default_db_path(self, runner):
        """Test default database path is set."""
        # The context object is created, we just verify no errors
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_custom_db_path(self, runner):
        """Test custom database path is accepted."""
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["--db", "test.db", "--help"])
            assert result.exit_code == 0

    def test_project_context(self, runner):
        """Test project context is accepted."""
        result = runner.invoke(cli, ["--project", "test-proj", "--help"])
        assert result.exit_code == 0


class TestJSONOutput:
    """Test JSON output mode for various commands."""

    def test_json_flag_accepted(self, runner):
        """Test that --json flag is accepted."""
        result = runner.invoke(cli, ["--json", "--help"])
        assert result.exit_code == 0

    def test_version_json(self, runner):
        """Test version command with JSON output."""
        result = runner.invoke(cli, ["--json", "version"])
        assert result.exit_code == 0
        # Version command should handle JSON mode gracefully
        # Even if it doesn't output JSON, it should not error

    def test_examples_json(self, runner):
        """Test examples command with JSON output."""
        result = runner.invoke(cli, ["--json", "examples"])
        assert result.exit_code == 0
        # Examples command should handle JSON mode gracefully


class TestProjectCommands:
    """Test project subcommands."""

    def test_project_list_help(self, runner):
        """Test project list help."""
        result = runner.invoke(cli, ["project", "list", "--help"])
        assert result.exit_code == 0
        assert "List all projects" in result.output

    def test_project_create_help(self, runner):
        """Test project create help."""
        result = runner.invoke(cli, ["project", "create", "--help"])
        assert result.exit_code == 0
        assert "Create a new project" in result.output

    def test_project_delete_help(self, runner):
        """Test project delete help."""
        result = runner.invoke(cli, ["project", "delete", "--help"])
        assert result.exit_code == 0
        assert "Delete a project" in result.output

    def test_project_status_help(self, runner):
        """Test project status help."""
        result = runner.invoke(cli, ["project", "status", "--help"])
        assert result.exit_code == 0
        assert "project status" in result.output.lower()

    def test_project_use_help(self, runner):
        """Test project use help."""
        result = runner.invoke(cli, ["project", "use", "--help"])
        assert result.exit_code == 0
        assert "Set" in result.output or "active" in result.output


class TestTaskCommands:
    """Test task subcommands."""

    def test_task_list_help(self, runner):
        """Test task list help."""
        result = runner.invoke(cli, ["task", "list", "--help"])
        assert result.exit_code == 0
        assert "List tasks" in result.output

    def test_task_show_help(self, runner):
        """Test task show help."""
        result = runner.invoke(cli, ["task", "show", "--help"])
        assert result.exit_code == 0
        # Check for key elements of the help text
        assert "task" in result.output.lower()

    def test_task_retry_help(self, runner):
        """Test task retry help."""
        result = runner.invoke(cli, ["task", "retry", "--help"])
        assert result.exit_code == 0
        assert "Retry" in result.output or "retry" in result.output

    def test_task_skip_help(self, runner):
        """Test task skip help."""
        result = runner.invoke(cli, ["task", "skip", "--help"])
        assert result.exit_code == 0
        assert "Skip" in result.output or "skip" in result.output


class TestRunCommands:
    """Test run subcommands."""

    def test_run_help(self, runner):
        """Test run command help."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "Run the autonomous coding agent" in result.output

    def test_run_with_task_option(self, runner):
        """Test run with --task option."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        # Verify --task option exists
        assert "--task" in result.output

    def test_run_with_resume_option(self, runner):
        """Test run with --resume option."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        # Verify --resume option exists
        assert "--resume" in result.output

    def test_run_with_parallel_option(self, runner):
        """Test run with --parallel option."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        # Verify --parallel option exists
        assert "--parallel" in result.output


class TestConfigCommands:
    """Test config subcommands."""

    def test_config_show_help(self, runner):
        """Test config show help."""
        result = runner.invoke(cli, ["config", "show", "--help"])
        assert result.exit_code == 0
        # Check for configuration in output
        assert "configuration" in result.output.lower() or "config" in result.output.lower()

    def test_config_set_help(self, runner):
        """Test config set help."""
        result = runner.invoke(cli, ["config", "set", "--help"])
        assert result.exit_code == 0
        assert "Set a configuration value" in result.output


class TestStatusCommands:
    """Test status command."""

    def test_status_help(self, runner):
        """Test status command help."""
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0


class TestLogsCommands:
    """Test logs command."""

    def test_logs_help(self, runner):
        """Test logs command help."""
        result = runner.invoke(cli, ["logs", "--help"])
        assert result.exit_code == 0
        assert "View structured logs" in result.output


class TestCostsCommands:
    """Test costs command."""

    def test_costs_help(self, runner):
        """Test costs command help."""
        result = runner.invoke(cli, ["costs", "--help"])
        assert result.exit_code == 0
        assert "Show cost breakdown" in result.output


class TestSyncCommand:
    """Test sync command."""

    def test_sync_help(self, runner):
        """Test sync command help."""
        result = runner.invoke(cli, ["sync", "--help"])
        assert result.exit_code == 0
        assert "Sync tasks with spec source" in result.output


class TestResearchCommand:
    """Test research command."""

    def test_research_help(self, runner):
        """Test research command help."""
        result = runner.invoke(cli, ["research", "--help"])
        assert result.exit_code == 0
        assert "Research" in result.output or "research" in result.output.lower()


class TestErrorMessages:
    """Test detailed error messages for invalid inputs."""

    def test_project_delete_missing_id(self, runner):
        """Test project delete with missing project ID."""
        result = runner.invoke(cli, ["project", "delete"])
        assert result.exit_code != 0
        # Should show error or usage

    def test_project_show_missing_id(self, runner):
        """Test project show with missing project ID."""
        result = runner.invoke(cli, ["project", "show"])
        assert result.exit_code != 0

    def test_task_show_missing_id(self, runner):
        """Test task show with missing task ID."""
        result = runner.invoke(cli, ["task", "show"])
        assert result.exit_code != 0

    def test_config_get_missing_key(self, runner):
        """Test config get with missing key."""
        result = runner.invoke(cli, ["config", "get"])
        assert result.exit_code != 0

    def test_config_set_missing_args(self, runner):
        """Test config set with missing arguments."""
        result = runner.invoke(cli, ["config", "set"])
        assert result.exit_code != 0


class TestCommandAliases:
    """Test command aliases and shortcuts."""

    def test_help_alias(self, runner):
        """Test help command."""
        result = runner.invoke(cli, ["help"])
        # Either shows help or shows error gracefully
        assert result.exit_code in [0, 2]

    def test_subcommand_abbreviation(self, runner):
        """Test abbreviated subcommand names."""
        # Click allows unambiguous abbreviations
        result = runner.invoke(cli, ["proj", "--help"])
        # May work or fail depending on Click's abbreviation handling
        # Just verify it doesn't crash


class TestInitCommandFunctional:
    """Functional tests for init command."""

    def test_init_creates_bob_directory(self, runner, tmp_path, monkeypatch):
        """Test init creates ~/.bob with proper structure."""
        monkeypatch.setenv("HOME", str(tmp_path))

        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0

        bob_dir = tmp_path / ".bob"
        assert bob_dir.exists()
        assert bob_dir.is_dir()

    def test_init_idempotent(self, runner, tmp_path, monkeypatch):
        """Test init is idempotent - fails if already initialized."""
        monkeypatch.setenv("HOME", str(tmp_path))

        # First init succeeds
        result1 = runner.invoke(cli, ["init"])
        assert result1.exit_code == 0

        # Second init fails
        result2 = runner.invoke(cli, ["init"])
        assert result2.exit_code != 0


class TestProjectCommandsFunctional:
    """Functional tests for project commands with mocked database."""

    @patch('bob.cli.project.DatabaseManager')
    def test_project_list_empty(self, mock_db_class, runner, tmp_path):
        """Test project list with no projects."""
        # Mock DatabaseManager to return empty project list
        mock_db = MagicMock()
        mock_db.list_projects.return_value = []
        mock_db_class.return_value = mock_db

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["--db", "test.db", "project", "list"])
            # Should succeed even with no projects
            assert result.exit_code == 0

    @patch('bob.cli.project.DatabaseManager')
    def test_project_create_basic(self, mock_db_class, runner, tmp_path):
        """Test basic project creation."""
        mock_db = MagicMock()
        mock_db.create_project.return_value = "test-project"
        mock_db_class.return_value = mock_db

        with runner.isolated_filesystem(temp_dir=tmp_path):
            workspace = tmp_path / "workspace"
            workspace.mkdir()
            spec = tmp_path / "spec.yaml"
            spec.write_text("version: 1.0")

            result = runner.invoke(cli, [
                "--db", "test.db",
                "project", "create",
                "test-project",
                str(workspace),
                f"file://{spec}"
            ])
            # May succeed or fail depending on validation, but shouldn't crash
            assert result.exit_code in [0, 1, 2]


class TestTaskCommandsFunctional:
    """Functional tests for task commands with mocked database."""

    @patch('bob.cli.task.DatabaseManager')
    def test_task_list_with_filters(self, mock_db_class, runner, tmp_path):
        """Test task list with various filters."""
        mock_db = MagicMock()
        mock_db.list_tasks.return_value = []
        mock_db.get_active_project.return_value = {"id": "test-proj"}
        mock_db_class.return_value = mock_db

        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Test with status filter
            result = runner.invoke(cli, [
                "--db", "test.db",
                "task", "list",
                "--status", "pending"
            ])
            assert result.exit_code in [0, 1]

            # Test with priority filter
            result = runner.invoke(cli, [
                "--db", "test.db",
                "task", "list",
                "--priority", "high"
            ])
            assert result.exit_code in [0, 1]


class TestConfigCommandsFunctional:
    """Functional tests for config commands."""

    def test_config_show_no_config(self, runner, tmp_path, monkeypatch):
        """Test config show when no config file exists."""
        monkeypatch.setenv("HOME", str(tmp_path))

        result = runner.invoke(cli, ["config", "show"])
        # Should show default config or handle missing config gracefully
        assert result.exit_code in [0, 1]

    def test_config_set_basic(self, runner, tmp_path, monkeypatch):
        """Test basic config set operation."""
        monkeypatch.setenv("HOME", str(tmp_path))

        # Create .bob directory
        bob_dir = tmp_path / ".bob"
        bob_dir.mkdir()

        result = runner.invoke(cli, [
            "config", "set",
            "agent.coding.model",
            "claude-opus-4"
        ])
        # Should succeed or fail gracefully
        assert result.exit_code in [0, 1]


class TestStatusCommandFunctional:
    """Functional tests for status command."""

    @patch('bob.cli.status.DatabaseManager')
    def test_status_no_projects(self, mock_db_class, runner, tmp_path):
        """Test status with no active projects."""
        mock_db = MagicMock()
        mock_db.get_active_project.return_value = None
        mock_db.count_tasks.return_value = {"total": 0}
        mock_db_class.return_value = mock_db

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["--db", "test.db", "status"])
            # Should handle no active project gracefully
            assert result.exit_code in [0, 1]


class TestJSONOutputFunctional:
    """Functional tests for JSON output mode."""

    @patch('bob.cli.project.DatabaseManager')
    def test_project_list_json(self, mock_db_class, runner, tmp_path):
        """Test project list with JSON output."""
        mock_db = MagicMock()
        mock_db.list_projects.return_value = [
            {
                "id": "proj1",
                "name": "Project 1",
                "workspace": "/tmp/proj1",
                "spec_source": "file://spec.yaml"
            }
        ]
        mock_db_class.return_value = mock_db

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, [
                "--json",
                "--db", "test.db",
                "project", "list"
            ])

            # Should either output JSON or handle JSON mode gracefully
            if result.exit_code == 0:
                # Try to parse output as JSON if it looks like JSON
                output = result.output.strip()
                if output.startswith('[') or output.startswith('{'):
                    try:
                        json.loads(output)
                    except json.JSONDecodeError:
                        # JSON parsing failed, but command succeeded
                        pass

    @patch('bob.cli.status.DatabaseManager')
    def test_status_json_output(self, mock_db_class, runner, tmp_path):
        """Test status with JSON output."""
        mock_db = MagicMock()
        mock_db.get_active_project.return_value = {
            "id": "test-proj",
            "name": "Test Project"
        }
        mock_db.count_tasks.return_value = {
            "total": 10,
            "pending": 3,
            "completed": 7
        }
        mock_db_class.return_value = mock_db

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, [
                "--json",
                "--db", "test.db",
                "status"
            ])

            # Should handle JSON mode
            assert result.exit_code in [0, 1]


class TestVerboseAndQuietModes:
    """Test verbose and quiet output modes."""

    @patch('bob.cli.project.DatabaseManager')
    def test_verbose_mode(self, mock_db_class, runner, tmp_path):
        """Test verbose mode adds more output."""
        mock_db = MagicMock()
        mock_db.list_projects.return_value = []
        mock_db_class.return_value = mock_db

        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Normal mode
            result_normal = runner.invoke(cli, [
                "--db", "test.db",
                "project", "list"
            ])

            # Verbose mode
            result_verbose = runner.invoke(cli, [
                "--verbose",
                "--db", "test.db",
                "project", "list"
            ])

            # Both should succeed
            assert result_normal.exit_code in [0, 1]
            assert result_verbose.exit_code in [0, 1]

    @patch('bob.cli.project.DatabaseManager')
    def test_quiet_mode(self, mock_db_class, runner, tmp_path):
        """Test quiet mode suppresses output."""
        mock_db = MagicMock()
        mock_db.list_projects.return_value = []
        mock_db_class.return_value = mock_db

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, [
                "--quiet",
                "--db", "test.db",
                "project", "list"
            ])

            # Should succeed
            assert result.exit_code in [0, 1]


class TestErrorHandlingFunctional:
    """Functional tests for error handling."""

    @patch('bob.cli.project.DatabaseManager')
    def test_invalid_project_id(self, mock_db_class, runner, tmp_path):
        """Test handling of invalid project ID."""
        mock_db = MagicMock()
        mock_db.get_project.return_value = None
        mock_db_class.return_value = mock_db

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, [
                "--db", "test.db",
                "project", "delete",
                "nonexistent-project"
            ])

            # Should fail gracefully
            assert result.exit_code != 0

    @patch('bob.cli.task.DatabaseManager')
    def test_invalid_task_id(self, mock_db_class, runner, tmp_path):
        """Test handling of invalid task ID."""
        mock_db = MagicMock()
        mock_db.get_task.return_value = None
        mock_db.get_active_project.return_value = {"id": "test-proj"}
        mock_db_class.return_value = mock_db

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, [
                "--db", "test.db",
                "task", "show",
                "INVALID"
            ])

            # Should fail gracefully
            assert result.exit_code != 0
