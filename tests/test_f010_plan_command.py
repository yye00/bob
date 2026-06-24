"""Tests for F010: Implement 'bob plan <spec.yaml>' command stub."""

import pathlib
import textwrap

import pytest
import yaml
from click.testing import CliRunner

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


# ============================================================
# Step 1: Implement plan command in cli.py
# ============================================================


class TestPlanCommandExists:
    """Step 1: Plan command is registered and accepts a spec file argument."""

    def test_plan_command_registered(self):
        from bob.cli import main

        assert "plan" in main.commands, "plan command must be registered"

    def test_plan_help_works(self):
        from bob.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["plan", "--help"])
        assert result.exit_code == 0
        assert "spec" in result.output.lower() or "yaml" in result.output.lower()


# ============================================================
# Step 2: Add spec file path parameter
# ============================================================


class TestPlanSpecFileParameter:
    """Step 2: Plan command accepts a spec file path as a positional argument."""

    def test_plan_accepts_spec_file_argument(self, tmp_path):
        """Plan command should accept a positional SPEC_FILE argument."""
        from bob.cli import main

        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: test\nversion: '1.0'\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code == 0, f"plan command failed: {result.output}"

    def test_plan_without_spec_file_shows_error(self):
        """Plan command with no arguments should show an error or usage."""
        from bob.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["plan"])
        # Click will show "Missing argument" error for a required argument
        assert result.exit_code != 0 or "missing" in result.output.lower() or "usage" in result.output.lower()

    def test_plan_nonexistent_file_shows_error(self, tmp_path):
        """Plan command with a nonexistent file should show an error."""
        from bob.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(tmp_path / "nonexistent.yaml")])
        assert result.exit_code != 0 or "not found" in result.output.lower() or "error" in result.output.lower()


# ============================================================
# Step 3: Parse spec file (basic YAML parsing)
# ============================================================


class TestPlanYamlParsing:
    """Step 3: Plan command parses the YAML spec file."""

    def test_plan_parses_valid_yaml(self, tmp_path):
        """Plan command should successfully parse a valid YAML spec."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: my-project
            version: "1.0"
            features:
              - name: Feature A
                description: First feature
              - name: Feature B
                description: Second feature
        """)
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code == 0, f"plan failed: {result.output}"

    def test_plan_handles_invalid_yaml(self, tmp_path):
        """Plan command should handle invalid YAML gracefully."""
        from bob.cli import main

        spec_file = tmp_path / "bad.yaml"
        spec_file.write_text("{{{{invalid yaml content::::}}}")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code != 0 or "error" in result.output.lower() or "invalid" in result.output.lower()

    def test_plan_handles_empty_yaml(self, tmp_path):
        """Plan command should handle an empty YAML file gracefully."""
        from bob.cli import main

        spec_file = tmp_path / "empty.yaml"
        spec_file.write_text("")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code == 0 or "empty" in result.output.lower()


# ============================================================
# Step 4: Display spec summary
# ============================================================


class TestPlanDisplaysSummary:
    """Step 4: Plan command displays a summary of the parsed spec."""

    def test_plan_shows_project_name(self, tmp_path):
        """Plan command should display the project name from the spec."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: awesome-project
            version: "2.0"
            features:
              - name: Auth
                description: Authentication system
        """)
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code == 0, f"plan failed: {result.output}"
        assert "awesome-project" in result.output, (
            f"Project name not in output: {result.output}"
        )

    def test_plan_shows_feature_count(self, tmp_path):
        """Plan command should display the number of features found."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: test-project
            version: "1.0"
            features:
              - name: Feature A
                description: First
              - name: Feature B
                description: Second
              - name: Feature C
                description: Third
        """)
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code == 0, f"plan failed: {result.output}"
        assert "3" in result.output, f"Feature count '3' not in output: {result.output}"

    def test_plan_shows_feature_names(self, tmp_path):
        """Plan command should display individual feature names."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: test-project
            version: "1.0"
            features:
              - name: Database Layer
                description: DB setup
              - name: API Endpoints
                description: REST API
        """)
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code == 0, f"plan failed: {result.output}"
        assert "Database Layer" in result.output, f"Feature name missing: {result.output}"
        assert "API Endpoints" in result.output, f"Feature name missing: {result.output}"

    def test_plan_shows_version_if_present(self, tmp_path):
        """Plan command should display the version from the spec."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: versioned-project
            version: "3.5.0"
            features: []
        """)
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code == 0, f"plan failed: {result.output}"
        assert "3.5.0" in result.output, f"Version not in output: {result.output}"

    def test_plan_shows_spec_file_path(self, tmp_path):
        """Plan command should display which spec file was loaded."""
        from bob.cli import main

        spec_file = tmp_path / "my-spec.yaml"
        spec_file.write_text("name: test\nversion: '1.0'\nfeatures: []\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code == 0, f"plan failed: {result.output}"
        assert "my-spec.yaml" in result.output, f"Spec file path not in output: {result.output}"


# ============================================================
# Step 5: Test: Run 'bob plan dummy.yaml' and verify it reads file
# ============================================================


class TestPlanEndToEnd:
    """Step 5: End-to-end test of plan command with a realistic spec file."""

    def test_plan_full_workflow(self, tmp_path):
        """Full workflow: create spec, run plan, verify output."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: e2e-project
            version: "1.0.0"
            description: End-to-end test project
            features:
              - name: Project Setup
                description: Initialize project structure
                priority: 10
              - name: Database Schema
                description: Create database tables
                priority: 20
              - name: REST API
                description: Implement API endpoints
                priority: 30
              - name: Frontend
                description: Build user interface
                priority: 40
              - name: Testing
                description: Write comprehensive tests
                priority: 50
        """)
        spec_file = tmp_path / "dummy.yaml"
        spec_file.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code == 0, f"plan failed: {result.output}"

        output = result.output
        # Should show project name
        assert "e2e-project" in output, f"Project name missing: {output}"
        # Should show feature count
        assert "5" in output, f"Feature count '5' missing: {output}"
        # Should show at least some feature names
        assert "Project Setup" in output, f"Feature name missing: {output}"
        assert "Database Schema" in output, f"Feature name missing: {output}"

    def test_plan_spec_without_features_key(self, tmp_path):
        """Spec without features key should be handled gracefully."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: minimal-project
            version: "0.1"
        """)
        spec_file = tmp_path / "minimal.yaml"
        spec_file.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec_file)])
        assert result.exit_code == 0, f"plan failed: {result.output}"
        assert "minimal-project" in result.output
        # Should indicate 0 features
        assert "0" in result.output, f"Expected '0' features: {result.output}"

    def test_plan_uses_yaml_import(self):
        """The cli module should import yaml for parsing."""
        import bob.cli
        import inspect

        source = inspect.getsource(bob.cli)
        assert "yaml" in source, "cli.py must import yaml for spec parsing"
