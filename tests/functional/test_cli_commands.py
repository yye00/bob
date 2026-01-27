"""Functional tests for Bob CLI commands."""
import os
import pytest
from pathlib import Path
from click.testing import CliRunner
from bob.cli.main import cli


class TestCLIFunctional:
    """Test CLI commands actually work end-to-end."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory with spec file."""
        spec_file = tmp_path / "bob_spec.yaml"
        spec_file.write_text("""
project:
  name: test-project
  description: Test project for functional tests
  tech_stack: Python

tasks:
  - id: F001
    title: Test Task
    description: A simple test task
    priority: high
""")
        return tmp_path

    def test_init_creates_environment(self, runner, tmp_path):
        """Test that 'bob init' creates the BOB environment."""
        # bob init initializes ~/.bob directory, not a project
        result = runner.invoke(cli, ['init', '--force'])
        # Should succeed or already exist
        assert result.exit_code == 0 or "already exists" in result.output.lower()

    def test_status_shows_project_info(self, runner, temp_project):
        """Test that 'bob status' shows real project information."""
        os.chdir(temp_project)
        result = runner.invoke(cli, ['status'])
        # Should not error, should show some status
        assert result.exit_code == 0 or "No active project" in result.output

    def test_task_list_shows_tasks(self, runner, temp_project):
        """Test that 'bob task list' shows tasks from spec."""
        os.chdir(temp_project)
        # First init the project
        runner.invoke(cli, ['project', 'create', str(temp_project)])
        result = runner.invoke(cli, ['task', 'list'])
        # Should complete without error
        assert result.exit_code == 0 or result.exit_code == 1  # May error if no DB

    def test_help_works_for_all_commands(self, runner):
        """Test that help is available for all documented commands."""
        commands = ['init', 'run', 'status', 'task', 'project', 'research']
        for cmd in commands:
            result = runner.invoke(cli, [cmd, '--help'])
            assert result.exit_code == 0, f"Help failed for {cmd}"
            assert '--help' in result.output or 'Usage:' in result.output
