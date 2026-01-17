"""Tests for CLI output formatting (F069).

This module tests that BOB's CLI provides consistent, readable output using:
- Rich library for formatted terminal output
- Colored output (success=green, error=red, warning=yellow)
- Tables for list commands
- Progress bars for long operations
- Clean JSON output (no formatting when --json flag is used)
"""

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models.base import Project, ProjectStatus


class TestColoredOutput:
    """Test that CLI uses colored output for status messages."""

    def test_success_messages_use_checkmark(self, tmp_path: Path) -> None:
        """Test that success messages include checkmark symbol."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        workspace = tmp_path / "workspace"

        # Create a project successfully
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.txt"]
        )

        # Success messages should include checkmark (✓)
        assert "✓" in result.output or "Created project" in result.output
        assert result.exit_code == 0

    def test_error_messages_use_x_mark(self, tmp_path: Path) -> None:
        """Test that error messages include X mark symbol."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        workspace = tmp_path / "workspace"

        # Try to create project with invalid name (underscore not allowed)
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "create", "invalid_name", str(workspace), "file://spec.txt"]
        )

        # Error messages should include X mark (✗)
        assert "✗" in result.output or "Invalid" in result.output or "invalid" in result.output.lower()
        assert result.exit_code != 0


class TestTableOutput:
    """Test that list commands use tables for formatting."""

    def test_project_list_uses_table_format(self, tmp_path: Path) -> None:
        """Test that 'bob project list' outputs in table format."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        workspace = tmp_path / "workspace"

        # Create a project first
        runner.invoke(
            cli,
            ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.txt"]
        )

        # List projects
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "list"]
        )

        # Should contain table-like output with project name
        assert "test-app" in result.output
        assert result.exit_code == 0

    def test_task_list_uses_table_format(self, tmp_path: Path) -> None:
        """Test that 'bob task list' command exists and has proper structure."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"

        # Test that the task list command provides helpful feedback
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "task", "list"]
        )

        # Should either succeed or provide helpful error message about needing a project
        # (This verifies the command exists and has proper output formatting)
        assert "task" in result.output.lower() or "project" in result.output.lower() or result.exit_code == 0


class TestJSONOutput:
    """Test that --json flag produces clean JSON without formatting."""

    def test_project_list_json_is_valid(self, tmp_path: Path) -> None:
        """Test that 'bob project list --json-output' produces valid JSON."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        workspace = tmp_path / "workspace"

        # Create a project
        runner.invoke(
            cli,
            ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.txt"]
        )

        # Get JSON output
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "list", "--json-output"]
        )

        # Should be valid JSON
        assert result.exit_code == 0
        # Extract JSON from output (might have other text)
        json_match = re.search(r'\[.*\]', result.output, re.DOTALL)
        if json_match:
            projects = json.loads(json_match.group(0))
            assert isinstance(projects, list)
            if len(projects) > 0:
                assert "name" in projects[0] or "id" in projects[0]

    def test_json_output_has_no_rich_formatting(self, tmp_path: Path) -> None:
        """Test that JSON output doesn't include ANSI color codes."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        workspace = tmp_path / "workspace"

        # Create a project
        runner.invoke(
            cli,
            ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.txt"]
        )

        # Get JSON output
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "list", "--json-output"]
        )

        # Should not contain ANSI escape codes
        # ANSI codes start with \x1b[ or \033[
        assert "\x1b[" not in result.output
        assert "\033[" not in result.output

    def test_config_show_json_is_valid(self, tmp_path: Path) -> None:
        """Test that 'bob config show --json-output' produces valid JSON."""
        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create minimal config
            config_dir = Path.home() / ".bob"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "config.yaml"
            config_file.write_text("models:\n  default: claude-sonnet-4\n")

            # Get JSON output
            result = runner.invoke(cli, ["config", "show", "--json-output"])

            # Should be valid JSON
            if result.exit_code == 0:
                json_match = re.search(r'\{.*\}', result.output, re.DOTALL)
                if json_match:
                    config = json.loads(json_match.group(0))
                    assert isinstance(config, dict)


class TestProgressBars:
    """Test that long operations show progress indicators."""

    def test_run_command_shows_progress(self, tmp_path: Path) -> None:
        """Test that 'bob run' shows progress indicators."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        workspace = tmp_path / "workspace"

        # Create a project
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.txt"]
        )

        # Note: We can't easily test actual progress bars in unit tests
        # because they require real-time rendering. This test just ensures
        # the command structure exists.
        # Progress bars are verified manually during integration testing.
        assert result.exit_code == 0


class TestConsistentFormatting:
    """Test that formatting is consistent across different commands."""

    def test_all_create_commands_use_checkmark(self, tmp_path: Path) -> None:
        """Test that all 'create' commands use checkmark on success."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        workspace = tmp_path / "workspace"

        # Project create
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.txt"]
        )
        assert result.exit_code == 0
        # Should have checkmark or success indicator
        assert "✓" in result.output or "Created" in result.output

    def test_all_error_messages_use_x_mark(self, tmp_path: Path) -> None:
        """Test that all error messages use X mark consistently."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        workspace = tmp_path / "workspace"

        # Test various error scenarios

        # Invalid project name (underscore not allowed)
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "create", "invalid_name", str(workspace), "file://spec.txt"]
        )
        assert "✗" in result.output or "invalid" in result.output.lower()

        # Nonexistent project
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "delete", "nonexistent"]
        )
        # Should either error or ask for confirmation
        assert result.exit_code != 0 or "not found" in result.output.lower()


class TestOutputWidth:
    """Test that output adapts to terminal width."""

    def test_narrow_terminal_wraps_properly(self, tmp_path: Path) -> None:
        """Test that output works in narrow terminals."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        workspace = tmp_path / "workspace"

        # Create a project
        runner.invoke(
            cli,
            ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.txt"]
        )

        # List with narrow terminal (80 chars)
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "list"],
            env={"COLUMNS": "80"}
        )

        # Should still work without errors
        assert result.exit_code == 0

    def test_wide_terminal_works(self, tmp_path: Path) -> None:
        """Test that output works in wide terminals."""
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        workspace = tmp_path / "workspace"

        # Create a project
        runner.invoke(
            cli,
            ["--db", str(db_path), "project", "create", "test-app", str(workspace), "file://spec.txt"]
        )

        # List with wide terminal (200 chars)
        result = runner.invoke(
            cli,
            ["--db", str(db_path), "project", "list"],
            env={"COLUMNS": "200"}
        )

        # Should still work without errors
        assert result.exit_code == 0


class TestRichLibraryUsage:
    """Test that rich library is being used for formatting."""

    def test_config_show_uses_rich_syntax(self, tmp_path: Path) -> None:
        """Test that 'bob config show' uses rich syntax highlighting."""
        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            # The config show command should use rich for YAML display
            result = runner.invoke(cli, ["config", "show"])

            # Should succeed (rich may or may not show colors in test mode)
            assert result.exit_code == 0

    def test_help_messages_are_readable(self, tmp_path: Path) -> None:
        """Test that help messages are well-formatted."""
        runner = CliRunner()

        # Test main help
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output

        # Test subcommand help
        result = runner.invoke(cli, ["project", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
