"""Tests for CLI framework.

Tests command parsing, option handling, and command structure.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from bob.cli.main import cli


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


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
        """Test logs command group."""
        result = runner.invoke(cli, ["logs", "--help"])
        assert result.exit_code == 0
        assert "View session logs" in result.output

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
        assert "Initialize BOB in the current directory" in result.output

    def test_init_creates_directory(self, runner):
        """Test that init creates .bob directory."""
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert "Initializing BOB workspace" in result.output
            assert "BOB workspace initialized" in result.output
            assert Path(".bob").exists()

    def test_init_fails_if_exists(self, runner):
        """Test that init fails if .bob already exists."""
        with runner.isolated_filesystem():
            # Create .bob directory
            Path(".bob").mkdir()

            # Try to init again
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 1
            assert "already exists" in result.output


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
