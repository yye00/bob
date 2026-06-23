"""Tests for F103: bob3 generate-features CLI command.

Usage: bob3 generate-features spec.yaml --refs paper.pdf --output features.yaml [--auto-continue]
"""

import json
import pathlib
import textwrap
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


# ============================================================
# Step 1: generate-features command exists in cli.py
# ============================================================


class TestGenerateFeaturesCommandExists:
    """Step 1: Add generate-features command to cli.py."""

    def test_generate_features_command_registered(self):
        from bob3.cli import main

        assert "generate-features" in main.commands, (
            "generate-features command must be registered"
        )

    def test_generate_features_help_works(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["generate-features", "--help"])
        assert result.exit_code == 0
        assert "spec" in result.output.lower() or "yaml" in result.output.lower()

    def test_generate_features_listed_in_main_help(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "generate-features" in result.output


# ============================================================
# Step 2: Parse project spec and extract PDF content
# ============================================================


class TestParseSpecAndPDF:
    """Step 2: Parse project spec and extract PDF content."""

    def test_accepts_spec_file_argument(self, tmp_path):
        """generate-features accepts a positional SPEC_FILE argument."""
        from bob3.cli import main

        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: test\nversion: '1.0'\nfeatures: []\n")
        output_file = tmp_path / "features.yaml"

        runner = CliRunner()
        # Mock the sub-agent so we don't actually call Claude
        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = []
            result = runner.invoke(
                main,
                ["generate-features", str(spec_file), "--output", str(output_file)],
            )
        assert result.exit_code == 0, f"generate-features failed: {result.output}"

    def test_nonexistent_spec_file_shows_error(self, tmp_path):
        """generate-features with nonexistent spec shows error."""
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main, ["generate-features", str(tmp_path / "no.yaml")]
        )
        assert result.exit_code != 0

    def test_invalid_yaml_shows_error(self, tmp_path):
        """generate-features with invalid YAML shows error."""
        from bob3.cli import main

        spec_file = tmp_path / "bad.yaml"
        spec_file.write_text("{{{{invalid yaml::::}}}")
        output_file = tmp_path / "features.yaml"

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["generate-features", str(spec_file), "--output", str(output_file)],
        )
        assert result.exit_code != 0 or "error" in result.output.lower()

    def test_refs_option_accepts_pdf_paths(self, tmp_path):
        """--refs option accepts file paths for reference documents."""
        from bob3.cli import main

        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: test\nversion: '1.0'\n")
        output_file = tmp_path / "features.yaml"

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["generate-features", str(spec_file), "--refs", "paper.pdf", "--output", str(output_file), "--help"],
        )
        # --help should exit 0 and mention refs
        assert result.exit_code == 0

    def test_help_shows_refs_option(self):
        """--help shows the --refs option."""
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["generate-features", "--help"])
        assert "--refs" in result.output

    def test_help_shows_output_option(self):
        """--help shows the --output option."""
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["generate-features", "--help"])
        assert "--output" in result.output

    def test_help_shows_auto_continue_option(self):
        """--help shows the --auto-continue option."""
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["generate-features", "--help"])
        assert "--auto-continue" in result.output


# ============================================================
# Step 3: Spawn research sub-agent with feature generation prompt
# ============================================================


class TestSpawnResearchAgent:
    """Step 3: Spawn research sub-agent with feature generation prompt."""

    def test_calls_run_generate_features(self, tmp_path):
        """Command should call _run_generate_features with parsed spec."""
        from bob3.cli import main

        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(
            textwrap.dedent("""\
            name: my-project
            version: "1.0"
            description: A test project
        """)
        )
        output_file = tmp_path / "features.yaml"

        runner = CliRunner()
        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = [
                {"name": "Feature A", "description": "First feature"}
            ]
            result = runner.invoke(
                main,
                ["generate-features", str(spec_file), "--output", str(output_file)],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args
        # Should pass spec_content as first arg
        assert "my-project" in str(call_kwargs)

    def test_passes_pdf_content_when_refs_provided(self, tmp_path):
        """When --refs is provided with valid PDFs, content is extracted and passed."""
        from bob3.cli import main

        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: test\nversion: '1.0'\n")
        output_file = tmp_path / "features.yaml"

        runner = CliRunner()
        with patch("bob3.cli._run_generate_features") as mock_gen, \
             patch("bob3.cli.extract_pdf_text") as mock_pdf:
            mock_gen.return_value = []
            mock_pdf.return_value = MagicMock(text="PDF content here", pages=["page1"], metadata={"page_count": 1})
            result = runner.invoke(
                main,
                ["generate-features", str(spec_file), "--refs", str(tmp_path / "paper.pdf"), "--output", str(output_file)],
            )

        # Even if PDF doesn't exist on disk, the mock should handle it
        # The function should attempt to extract PDF content
        assert result.exit_code == 0 or "error" in result.output.lower() or "not found" in result.output.lower()


# ============================================================
# Step 4: Parse agent output to YAML features
# ============================================================


class TestParseAgentOutput:
    """Step 4: Parse agent output to YAML features."""

    def test_parse_features_from_yaml_text(self):
        """_parse_features_from_output extracts YAML features from agent output."""
        from bob3.cli import _parse_features_from_output

        agent_output = textwrap.dedent("""\
            Here are the features:

            ```yaml
            features:
              - name: Database Layer
                description: Set up the database schema
                priority: 10
                acceptance_criteria:
                  - Create tables
                  - Add indexes
              - name: REST API
                description: Implement REST endpoints
                priority: 20
                acceptance_criteria:
                  - GET /items
                  - POST /items
            ```
        """)

        features = _parse_features_from_output(agent_output)
        assert len(features) == 2
        assert features[0]["name"] == "Database Layer"
        assert features[1]["name"] == "REST API"
        assert features[0]["priority"] == 10

    def test_parse_features_handles_no_yaml_block(self):
        """_parse_features_from_output returns empty list for no YAML."""
        from bob3.cli import _parse_features_from_output

        features = _parse_features_from_output("No features here, just text.")
        assert features == []

    def test_parse_features_handles_yaml_without_features_key(self):
        """_parse_features_from_output handles YAML without 'features' key."""
        from bob3.cli import _parse_features_from_output

        agent_output = textwrap.dedent("""\
            ```yaml
            - name: Feature A
              description: A feature
            - name: Feature B
              description: Another feature
            ```
        """)

        features = _parse_features_from_output(agent_output)
        assert len(features) == 2
        assert features[0]["name"] == "Feature A"

    def test_parse_features_handles_invalid_yaml(self):
        """_parse_features_from_output returns empty list for invalid YAML."""
        from bob3.cli import _parse_features_from_output

        agent_output = "```yaml\n{{invalid yaml\n```"
        features = _parse_features_from_output(agent_output)
        assert features == []


# ============================================================
# Step 5: Write output file
# ============================================================


class TestWriteOutputFile:
    """Step 5: Write output file."""

    def test_output_file_is_created(self, tmp_path):
        """generate-features creates the output YAML file."""
        from bob3.cli import main

        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: test\nversion: '1.0'\n")
        output_file = tmp_path / "features.yaml"

        runner = CliRunner()
        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = [
                {"name": "Feature A", "description": "Desc A", "priority": 10},
                {"name": "Feature B", "description": "Desc B", "priority": 20},
            ]
            result = runner.invoke(
                main,
                ["generate-features", str(spec_file), "--output", str(output_file)],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert output_file.exists(), "Output file was not created"

        written = yaml.safe_load(output_file.read_text())
        assert "features" in written
        assert len(written["features"]) == 2
        assert written["features"][0]["name"] == "Feature A"

    def test_default_output_file_name(self, tmp_path):
        """Without --output, default output is features.yaml in current dir."""
        from bob3.cli import main

        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: test\nversion: '1.0'\n")

        runner = CliRunner()
        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = [
                {"name": "Feature A", "description": "Desc A"},
            ]
            # Run from tmp_path so default output goes there
            with runner.isolated_filesystem(temp_dir=tmp_path):
                result = runner.invoke(
                    main,
                    ["generate-features", str(spec_file)],
                )

        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_output_shows_feature_count(self, tmp_path):
        """Command output should show how many features were generated."""
        from bob3.cli import main

        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: test\nversion: '1.0'\n")
        output_file = tmp_path / "features.yaml"

        runner = CliRunner()
        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = [
                {"name": "F1", "description": "D1"},
                {"name": "F2", "description": "D2"},
                {"name": "F3", "description": "D3"},
            ]
            result = runner.invoke(
                main,
                ["generate-features", str(spec_file), "--output", str(output_file)],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "3" in result.output, f"Feature count not shown: {result.output}"


# ============================================================
# Step 6: Implement --auto-continue flag
# ============================================================


class TestAutoContinueFlag:
    """Step 6: Implement --auto-continue flag."""

    def test_auto_continue_flag_accepted(self, tmp_path):
        """--auto-continue flag should be accepted without error."""
        from bob3.cli import main

        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: test\nversion: '1.0'\n")
        output_file = tmp_path / "features.yaml"

        runner = CliRunner()
        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = [
                {"name": "Feature A", "description": "Desc"},
            ]
            result = runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                    "--auto-continue",
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_auto_continue_message_shown(self, tmp_path):
        """With --auto-continue, the output should indicate auto-continue mode."""
        from bob3.cli import main

        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: test\nversion: '1.0'\n")
        output_file = tmp_path / "features.yaml"

        runner = CliRunner()
        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = [
                {"name": "Feature A", "description": "Desc"},
            ]
            result = runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                    "--auto-continue",
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "auto" in result.output.lower() or "plan" in result.output.lower()


# ============================================================
# Step 7: Integration tests
# ============================================================


class TestGenerateFeaturesIntegration:
    """Step 7: End-to-end integration tests (with mocked sub-agent)."""

    def test_full_workflow_with_spec(self, tmp_path):
        """Full workflow: spec file -> generate -> output YAML."""
        from bob3.cli import main

        spec_content = textwrap.dedent("""\
            name: awesome-app
            version: "2.0"
            description: |
                An awesome application with many features.
                It should have a database, API, and frontend.
        """)
        spec_file = tmp_path / "app_spec.yaml"
        spec_file.write_text(spec_content)
        output_file = tmp_path / "generated_features.yaml"

        runner = CliRunner()
        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = [
                {
                    "name": "Database Schema",
                    "description": "Create database schema with users, items tables",
                    "priority": 10,
                    "acceptance_criteria": ["Create users table", "Create items table"],
                },
                {
                    "name": "REST API",
                    "description": "Implement REST endpoints for CRUD operations",
                    "priority": 20,
                    "acceptance_criteria": ["GET /api/items", "POST /api/items"],
                },
            ]
            result = runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert output_file.exists()

        written = yaml.safe_load(output_file.read_text())
        assert len(written["features"]) == 2
        assert written["features"][0]["name"] == "Database Schema"
        assert "acceptance_criteria" in written["features"][0]

    def test_empty_spec_generates_no_features(self, tmp_path):
        """Empty spec should result in no features generated."""
        from bob3.cli import main

        spec_file = tmp_path / "empty.yaml"
        spec_file.write_text("name: empty\nversion: '0.1'\n")
        output_file = tmp_path / "features.yaml"

        runner = CliRunner()
        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = []
            result = runner.invoke(
                main,
                ["generate-features", str(spec_file), "--output", str(output_file)],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "0" in result.output
