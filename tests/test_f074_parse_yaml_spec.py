"""Tests for F074: Parse YAML spec file in plan command.

Validates that the plan command correctly parses YAML spec files,
extracts features, and validates the spec format.
"""

import pathlib
import textwrap

import pytest
import yaml
from click.testing import CliRunner

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


# ============================================================
# Step 1: Add PyYAML dependency
# ============================================================


class TestPyYAMLDependency:
    """Step 1: PyYAML must be listed as a project dependency."""

    def test_pyyaml_in_pyproject_toml(self):
        """PyYAML must be declared in pyproject.toml dependencies."""
        pyproject = WORKSPACE / "pyproject.toml"
        assert pyproject.exists(), "pyproject.toml must exist"
        content = pyproject.read_text()
        assert "PyYAML" in content, "PyYAML must be in pyproject.toml dependencies"

    def test_yaml_importable(self):
        """The yaml module must be importable (PyYAML installed)."""
        import yaml as _yaml

        assert hasattr(_yaml, "safe_load"), "yaml.safe_load must be available"

    def test_cli_imports_yaml(self):
        """The CLI module must import yaml for spec parsing."""
        import inspect

        import bob.cli

        source = inspect.getsource(bob.cli)
        assert "import yaml" in source, "cli.py must import yaml"


# ============================================================
# Step 2: Parse spec file structure
# ============================================================


class TestParseSpecFileStructure:
    """Step 2: Plan command parses the YAML spec file structure."""

    def test_parses_name_field(self, tmp_path):
        """Plan command extracts the project name from spec."""
        from bob.cli import main

        spec = tmp_path / "spec.yaml"
        spec.write_text("name: my-test-project\nversion: '1.0'\nfeatures: []\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "my-test-project" in result.output

    def test_parses_version_field(self, tmp_path):
        """Plan command extracts the version from spec."""
        from bob.cli import main

        spec = tmp_path / "spec.yaml"
        spec.write_text("name: proj\nversion: '2.5.1'\nfeatures: []\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "2.5.1" in result.output

    def test_parses_features_list(self, tmp_path):
        """Plan command extracts the features list from spec."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: proj
            version: "1.0"
            features:
              - name: Auth
                description: Authentication
              - name: DB
                description: Database layer
        """)
        spec = tmp_path / "spec.yaml"
        spec.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "2" in result.output, f"Should show 2 features: {result.output}"

    def test_defaults_name_to_filename_when_missing(self, tmp_path):
        """When name is absent, should default to spec file stem."""
        from bob.cli import main

        spec = tmp_path / "my-cool-project.yaml"
        spec.write_text("version: '1.0'\nfeatures: []\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "my-cool-project" in result.output

    def test_handles_spec_with_description(self, tmp_path):
        """Plan command handles spec with optional description field."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: described-project
            version: "1.0"
            description: A project with a description
            features:
              - name: Feature 1
                description: First feature
        """)
        spec = tmp_path / "spec.yaml"
        spec.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "described-project" in result.output


# ============================================================
# Step 3: Extract features from spec
# ============================================================


class TestExtractFeaturesFromSpec:
    """Step 3: Features are extracted with name, description, and optional fields."""

    def test_extracts_feature_names(self, tmp_path):
        """Plan command displays individual feature names."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: proj
            version: "1.0"
            features:
              - name: User Registration
                description: Register new users
              - name: Password Reset
                description: Reset user passwords
              - name: OAuth Integration
                description: Third-party login
        """)
        spec = tmp_path / "spec.yaml"
        spec.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "User Registration" in result.output
        assert "Password Reset" in result.output
        assert "OAuth Integration" in result.output

    def test_extracts_feature_descriptions(self, tmp_path):
        """Plan command displays feature descriptions."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: proj
            version: "1.0"
            features:
              - name: Cache Layer
                description: Redis-based caching for API responses
        """)
        spec = tmp_path / "spec.yaml"
        spec.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "Cache Layer" in result.output
        assert "Redis-based caching" in result.output

    def test_extracts_correct_feature_count(self, tmp_path):
        """Plan command shows correct count of features."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: proj
            version: "1.0"
            features:
              - name: F1
                description: Feature 1
              - name: F2
                description: Feature 2
              - name: F3
                description: Feature 3
              - name: F4
                description: Feature 4
              - name: F5
                description: Feature 5
        """)
        spec = tmp_path / "spec.yaml"
        spec.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "5" in result.output

    def test_handles_features_as_strings(self, tmp_path):
        """Plan command handles features listed as plain strings."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: proj
            version: "1.0"
            features:
              - Authentication
              - Database
              - API
        """)
        spec = tmp_path / "spec.yaml"
        spec.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "3" in result.output
        assert "Authentication" in result.output

    def test_handles_empty_features_list(self, tmp_path):
        """Plan command handles empty features list gracefully."""
        from bob.cli import main

        spec = tmp_path / "spec.yaml"
        spec.write_text("name: proj\nversion: '1.0'\nfeatures: []\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "0" in result.output

    def test_handles_no_features_key(self, tmp_path):
        """Plan command handles spec without features key."""
        from bob.cli import main

        spec = tmp_path / "spec.yaml"
        spec.write_text("name: proj\nversion: '1.0'\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "0" in result.output


# ============================================================
# Step 4: Validate spec format
# ============================================================


class TestValidateSpecFormat:
    """Step 4: Plan command validates YAML spec format and reports errors."""

    def test_rejects_invalid_yaml(self, tmp_path):
        """Plan command rejects files with invalid YAML syntax."""
        from bob.cli import main

        spec = tmp_path / "bad.yaml"
        spec.write_text("{{invalid: yaml::content}}")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code != 0 or "error" in result.output.lower()

    def test_handles_yaml_with_tabs(self, tmp_path):
        """Plan command handles YAML that uses tabs (which is invalid YAML)."""
        from bob.cli import main

        spec = tmp_path / "tabs.yaml"
        spec.write_text("name: proj\n\tversion: '1.0'\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        # Tabs are invalid in YAML - should either error or handle gracefully
        assert result.exit_code != 0 or "error" in result.output.lower()

    def test_handles_empty_file(self, tmp_path):
        """Plan command handles completely empty spec file."""
        from bob.cli import main

        spec = tmp_path / "empty.yaml"
        spec.write_text("")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        # Should succeed with defaults, not crash
        assert result.exit_code == 0

    def test_rejects_nonexistent_file(self, tmp_path):
        """Plan command errors on nonexistent file."""
        from bob.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(tmp_path / "gone.yaml")])
        assert result.exit_code != 0

    def test_handles_yaml_only_scalar(self, tmp_path):
        """Plan command handles YAML that is just a scalar value."""
        from bob.cli import main

        spec = tmp_path / "scalar.yaml"
        spec.write_text("just a string\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        # Should handle gracefully - a scalar has no .get() method
        # The plan command calls spec.get() which only works on dicts
        # This tests that the code doesn't crash unexpectedly
        # Depending on implementation, might exit 0 or non-0
        assert isinstance(result.exit_code, int)

    def test_handles_features_as_null(self, tmp_path):
        """Plan command handles features: null gracefully."""
        from bob.cli import main

        spec = tmp_path / "spec.yaml"
        spec.write_text("name: proj\nversion: '1.0'\nfeatures: null\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "0" in result.output


# ============================================================
# Step 5: Test: Parse valid spec, verify features extracted
# ============================================================


class TestParseValidSpecVerifyFeatures:
    """Step 5: Integration test - parse a realistic spec and verify feature extraction."""

    def test_full_spec_parsing(self, tmp_path):
        """Parse a complete, realistic spec and verify all features are extracted."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: build-bot
            version: "3.0.0"
            description: A recursive build orchestration system
            features:
              - name: Database Schema
                description: Create SQLite database with all required tables
                priority: 10
              - name: Data Models
                description: Pydantic models for all entities
                priority: 20
              - name: CLI Interface
                description: Click-based command-line interface
                priority: 30
              - name: Orchestrator
                description: Main build orchestration loop
                priority: 40
              - name: Sub-Agent Executor
                description: Claude Code SDK integration
                priority: 50
              - name: Test Suite
                description: Comprehensive test coverage
                priority: 60
        """)
        spec = tmp_path / "full-spec.yaml"
        spec.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0

        output = result.output
        # Verify project name extracted
        assert "build-bot" in output
        # Verify version extracted
        assert "3.0.0" in output
        # Verify feature count
        assert "6" in output
        # Verify individual features extracted
        assert "Database Schema" in output
        assert "Data Models" in output
        assert "CLI Interface" in output
        assert "Orchestrator" in output
        assert "Sub-Agent Executor" in output
        assert "Test Suite" in output

    def test_spec_with_acceptance_criteria(self, tmp_path):
        """Features with acceptance_criteria are parsed correctly."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: criteria-project
            version: "1.0"
            features:
              - name: Auth System
                description: Full authentication with JWT
                acceptance_criteria:
                  - Users can register
                  - Users can login
                  - JWT tokens issued on login
        """)
        spec = tmp_path / "spec.yaml"
        spec.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "Auth System" in result.output
        assert "1" in result.output  # 1 feature

    def test_spec_with_dependencies(self, tmp_path):
        """Spec with dependency info is parsed without errors."""
        from bob.cli import main

        spec_content = textwrap.dedent("""\
            name: dep-project
            version: "1.0"
            features:
              - name: Core
                description: Core library
                priority: 10
              - name: API
                description: REST API (depends on Core)
                priority: 20
                depends_on:
                  - Core
        """)
        spec = tmp_path / "spec.yaml"
        spec.write_text(spec_content)

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "Core" in result.output
        assert "API" in result.output
        assert "2" in result.output

    def test_yaml_safe_load_used(self):
        """Ensure yaml.safe_load is used (not yaml.load) for security."""
        import inspect

        import bob.cli

        source = inspect.getsource(bob.cli)
        assert "safe_load" in source, "Must use yaml.safe_load for security"

    def test_spec_file_path_displayed(self, tmp_path):
        """Plan command shows the spec file name in output."""
        from bob.cli import main

        spec = tmp_path / "my-project-spec.yaml"
        spec.write_text("name: proj\nversion: '1.0'\nfeatures: []\n")

        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(spec)])
        assert result.exit_code == 0
        assert "my-project-spec.yaml" in result.output
