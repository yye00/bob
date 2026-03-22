"""Tests for F085: README.md with installation and usage instructions.

Verifies that the README.md file exists in the project root and contains
all required sections: project description, installation instructions,
usage examples for all CLI commands, and an architecture overview.
"""

import pathlib
import re

import pytest


PROJECT_ROOT = pathlib.Path(__file__).parent.parent


@pytest.fixture
def readme_path():
    """Return the path to the README.md file."""
    return PROJECT_ROOT / "README.md"


@pytest.fixture
def readme_text(readme_path):
    """Return the contents of the README.md file."""
    assert readme_path.exists(), f"README.md not found at {readme_path}"
    return readme_path.read_text()


class TestReadmeExists:
    """Step 1: Create README.md in project root."""

    def test_readme_exists(self, readme_path):
        """README.md file must exist in the project root."""
        assert readme_path.exists(), f"README.md not found at {readme_path}"

    def test_readme_is_not_empty(self, readme_text):
        """README.md must not be empty."""
        assert len(readme_text.strip()) > 100, "README.md is too short"


class TestProjectDescription:
    """Step 2: Add project description."""

    def test_has_title(self, readme_text):
        """README must contain a top-level heading with the project name."""
        assert re.search(r"^#\s+.*Bob3", readme_text, re.MULTILINE), (
            "README must have a top-level heading mentioning Bob3"
        )

    def test_has_project_description(self, readme_text):
        """README must describe what Bob3 does."""
        lower = readme_text.lower()
        assert "build orchestration" in lower, (
            "README must mention 'build orchestration'"
        )
        assert "claude" in lower, (
            "README must mention Claude"
        )
        assert "sub-agent" in lower or "subagent" in lower, (
            "README must mention sub-agents"
        )

    def test_has_key_features_list(self, readme_text):
        """README must list key features of Bob3."""
        lower = readme_text.lower()
        assert "mcp" in lower, "README must mention MCP integration"
        assert "titans" in lower or "memory" in lower, (
            "README must mention memory/TITANS"
        )


class TestInstallationInstructions:
    """Step 3: Add installation instructions (pip install)."""

    def test_has_installation_section(self, readme_text):
        """README must have an installation section."""
        assert re.search(r"#+\s+.*[Ii]nstall", readme_text), (
            "README must have an installation section heading"
        )

    def test_has_pip_install(self, readme_text):
        """README must include pip install command."""
        assert "pip install" in readme_text, (
            "README must show pip install command"
        )

    def test_mentions_python_version(self, readme_text):
        """README must mention required Python version."""
        assert "3.11" in readme_text or "python" in readme_text.lower(), (
            "README must mention Python version requirement"
        )

    def test_mentions_environment_variables(self, readme_text):
        """README must mention required environment variables."""
        assert "OPENAI_API_KEY" in readme_text, (
            "README must mention OPENAI_API_KEY"
        )


class TestUsageExamples:
    """Step 4: Add usage examples for all CLI commands."""

    def test_has_usage_section(self, readme_text):
        """README must have a usage section."""
        assert re.search(r"#+\s+.*[Uu]sage", readme_text), (
            "README must have a usage section heading"
        )

    def test_documents_init_command(self, readme_text):
        """README must document the init command."""
        assert "bob3 init" in readme_text, (
            "README must document 'bob3 init' command"
        )

    def test_documents_plan_command(self, readme_text):
        """README must document the plan command."""
        assert "bob3 plan" in readme_text, (
            "README must document 'bob3 plan' command"
        )

    def test_documents_run_command(self, readme_text):
        """README must document the run command."""
        assert "bob3 run" in readme_text, (
            "README must document 'bob3 run' command"
        )

    def test_documents_status_command(self, readme_text):
        """README must document the status command."""
        assert "bob3 status" in readme_text, (
            "README must document 'bob3 status' command"
        )

    def test_documents_generate_features_command(self, readme_text):
        """README must document the generate-features command."""
        assert "bob3 generate-features" in readme_text or "generate-features" in readme_text, (
            "README must document 'bob3 generate-features' command"
        )

    def test_has_code_blocks(self, readme_text):
        """README must contain code blocks for usage examples."""
        code_blocks = re.findall(r"```", readme_text)
        assert len(code_blocks) >= 4, (
            "README must contain at least 2 code blocks (opening + closing pairs)"
        )


class TestArchitectureOverview:
    """Step 5: Add architecture overview."""

    def test_has_architecture_section(self, readme_text):
        """README must have an architecture section."""
        assert re.search(r"#+\s+.*[Aa]rchitecture", readme_text), (
            "README must have an architecture section heading"
        )

    def test_mentions_orchestration_loop(self, readme_text):
        """README must describe the orchestration loop."""
        lower = readme_text.lower()
        assert "orchestrat" in lower, (
            "README must describe the orchestration system"
        )

    def test_mentions_database(self, readme_text):
        """README must mention the SQLite database."""
        lower = readme_text.lower()
        assert "sqlite" in lower or "database" in lower, (
            "README must mention the database"
        )

    def test_mentions_claude_code_sdk(self, readme_text):
        """README must mention the Claude Code SDK."""
        assert "claude-code-sdk" in readme_text or "Claude Code SDK" in readme_text, (
            "README must mention the Claude Code SDK"
        )
