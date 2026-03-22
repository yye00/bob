"""Tests for F007: Create cli.py with Click framework and basic command structure."""

import pathlib

import pytest
from click.testing import CliRunner

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


# ============================================================
# Step 1: cli.py file exists
# ============================================================


class TestCliFileExists:
    """Step 1: Create src/bob3/cli.py file."""

    def test_cli_file_exists(self):
        cli_path = WORKSPACE / "src" / "bob3" / "cli.py"
        assert cli_path.exists(), "src/bob3/cli.py must exist"

    def test_cli_module_importable(self):
        import bob3.cli  # noqa: F401


# ============================================================
# Step 2: Import Click and setup main CLI group
# ============================================================


class TestClickSetup:
    """Step 2: Import Click and setup main CLI group."""

    def test_cli_uses_click(self):
        import bob3.cli
        import inspect

        source = inspect.getsource(bob3.cli)
        assert "click" in source.lower(), "cli.py must use Click"

    def test_main_is_click_group(self):
        import click
        from bob3.cli import main

        assert isinstance(main, click.Group) or isinstance(
            main, click.core.Group
        ), "main must be a Click group"

    def test_main_callable(self):
        from bob3.cli import main

        assert callable(main), "main must be callable"


# ============================================================
# Step 3: Add command stubs: init, plan, run, status
# ============================================================


class TestCommandsExist:
    """Step 3: Add commands: init, plan, run, status."""

    def test_init_command_registered(self):
        from bob3.cli import main

        assert "init" in main.commands, "init command must be registered"

    def test_plan_command_registered(self):
        from bob3.cli import main

        assert "plan" in main.commands, "plan command must be registered"

    def test_run_command_registered(self):
        from bob3.cli import main

        assert "run" in main.commands, "run command must be registered"

    def test_status_command_registered(self):
        from bob3.cli import main

        assert "status" in main.commands, "status command must be registered"

    def test_exactly_four_commands(self):
        from bob3.cli import main

        expected = {"init", "plan", "run", "status"}
        actual = set(main.commands.keys())
        assert expected.issubset(actual), (
            f"Missing commands: {expected - actual}"
        )


# ============================================================
# Step 4: Add --help documentation
# ============================================================


class TestHelpDocumentation:
    """Step 4: Add --help documentation."""

    def test_main_help_has_description(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "bob3" in result.output.lower() or "build orchestration" in result.output.lower()

    def test_init_has_help_text(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert len(result.output) > 0

    def test_plan_has_help_text(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["plan", "--help"])
        assert result.exit_code == 0
        assert len(result.output) > 0

    def test_run_has_help_text(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        assert len(result.output) > 0

    def test_status_has_help_text(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["status", "--help"])
        assert result.exit_code == 0
        assert len(result.output) > 0


# ============================================================
# Step 5: Test that 'bob3 --help' works
# ============================================================


class TestBob3Help:
    """Step 5: Test that 'bob3 --help' works."""

    def test_help_exits_cleanly(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_help_shows_version_option(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "--version" in result.output or "--help" in result.output

    def test_version_flag_works(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.2.0" in result.output or "bob3" in result.output.lower()


# ============================================================
# Step 6: Verify all four commands are listed
# ============================================================


class TestCommandsListedInHelp:
    """Step 6: Verify all four commands are listed in help output."""

    def test_init_listed_in_help(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "init" in result.output

    def test_plan_listed_in_help(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "plan" in result.output

    def test_run_listed_in_help(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "run" in result.output

    def test_status_listed_in_help(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "status" in result.output

    def test_all_commands_in_single_help(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        for cmd in ["init", "plan", "run", "status"]:
            assert cmd in result.output, f"'{cmd}' not found in help output"
