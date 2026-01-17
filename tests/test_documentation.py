"""Tests for documentation (F071).

This module verifies that all required documentation files exist
and contain the expected sections.
"""

from pathlib import Path

import pytest


class TestDocumentationFiles:
    """Test that all required documentation files exist."""

    @pytest.fixture
    def docs_dir(self) -> Path:
        """Get the docs directory path."""
        return Path(__file__).parent.parent / "docs"

    def test_docs_directory_exists(self, docs_dir: Path) -> None:
        """Test that docs/ directory exists."""
        assert docs_dir.exists()
        assert docs_dir.is_dir()

    def test_getting_started_exists(self, docs_dir: Path) -> None:
        """Test that getting-started.md exists."""
        getting_started = docs_dir / "getting-started.md"
        assert getting_started.exists()
        assert getting_started.is_file()

    def test_configuration_exists(self, docs_dir: Path) -> None:
        """Test that configuration.md exists."""
        configuration = docs_dir / "configuration.md"
        assert configuration.exists()
        assert configuration.is_file()

    def test_spec_formats_exists(self, docs_dir: Path) -> None:
        """Test that spec-formats.md exists."""
        spec_formats = docs_dir / "spec-formats.md"
        assert spec_formats.exists()
        assert spec_formats.is_file()

    def test_escalation_exists(self, docs_dir: Path) -> None:
        """Test that escalation.md exists."""
        escalation = docs_dir / "escalation.md"
        assert escalation.exists()
        assert escalation.is_file()

    def test_research_first_exists(self, docs_dir: Path) -> None:
        """Test that research-first.md exists."""
        research_first = docs_dir / "research-first.md"
        assert research_first.exists()
        assert research_first.is_file()

    def test_plugins_exists(self, docs_dir: Path) -> None:
        """Test that plugins.md exists."""
        plugins = docs_dir / "plugins.md"
        assert plugins.exists()
        assert plugins.is_file()

    def test_architecture_exists(self, docs_dir: Path) -> None:
        """Test that architecture.md exists."""
        architecture = docs_dir / "architecture.md"
        assert architecture.exists()
        assert architecture.is_file()

    def test_cli_reference_exists(self, docs_dir: Path) -> None:
        """Test that cli-reference.md exists."""
        cli_reference = docs_dir / "cli-reference.md"
        assert cli_reference.exists()
        assert cli_reference.is_file()


class TestDocumentationContent:
    """Test that documentation files contain expected content."""

    @pytest.fixture
    def docs_dir(self) -> Path:
        """Get the docs directory path."""
        return Path(__file__).parent.parent / "docs"

    def test_getting_started_has_installation(self, docs_dir: Path) -> None:
        """Test that getting-started.md has installation section."""
        content = (docs_dir / "getting-started.md").read_text()
        assert "Installation" in content or "installation" in content.lower()
        assert "Prerequisites" in content or "requirements" in content.lower()

    def test_configuration_has_models_section(self, docs_dir: Path) -> None:
        """Test that configuration.md has models section."""
        content = (docs_dir / "configuration.md").read_text()
        assert "models" in content.lower()
        assert "database" in content.lower()
        assert "limits" in content.lower()

    def test_spec_formats_has_yaml(self, docs_dir: Path) -> None:
        """Test that spec-formats.md covers YAML format."""
        content = (docs_dir / "spec-formats.md").read_text()
        assert "YAML" in content or "yaml" in content
        assert "tasks:" in content or "task" in content

    def test_escalation_has_strategies(self, docs_dir: Path) -> None:
        """Test that escalation.md covers strategies."""
        content = (docs_dir / "escalation.md").read_text()
        assert "smart" in content.lower()
        assert "aggressive" in content.lower() or "conservative" in content.lower()
        assert "escalation" in content.lower()

    def test_research_first_has_workflow(self, docs_dir: Path) -> None:
        """Test that research-first.md covers workflow."""
        content = (docs_dir / "research-first.md").read_text()
        assert "research" in content.lower()
        assert "perplexity" in content.lower() or "search" in content.lower()

    def test_plugins_has_types(self, docs_dir: Path) -> None:
        """Test that plugins.md covers plugin types."""
        content = (docs_dir / "plugins.md").read_text()
        assert "plugin" in content.lower()
        assert "spec" in content.lower() or "agent" in content.lower()

    def test_architecture_has_overview(self, docs_dir: Path) -> None:
        """Test that architecture.md has architecture overview."""
        content = (docs_dir / "architecture.md").read_text()
        assert "architecture" in content.lower() or "overview" in content.lower()
        assert "component" in content.lower() or "layer" in content.lower()

    def test_cli_reference_has_commands(self, docs_dir: Path) -> None:
        """Test that cli-reference.md has command reference."""
        content = (docs_dir / "cli-reference.md").read_text()
        assert "project" in content.lower()
        assert "task" in content.lower()
        assert "run" in content.lower()


class TestDocumentationMarkdown:
    """Test that documentation uses valid markdown."""

    @pytest.fixture
    def docs_dir(self) -> Path:
        """Get the docs directory path."""
        return Path(__file__).parent.parent / "docs"

    def test_getting_started_is_markdown(self, docs_dir: Path) -> None:
        """Test that getting-started.md is valid markdown."""
        content = (docs_dir / "getting-started.md").read_text()
        # Should have markdown headers
        assert content.startswith("#") or "\n#" in content
        # Should not be empty
        assert len(content) > 100

    def test_all_docs_have_headers(self, docs_dir: Path) -> None:
        """Test that all documentation files have headers."""
        doc_files = [
            "getting-started.md",
            "configuration.md",
            "spec-formats.md",
            "escalation.md",
            "research-first.md",
            "plugins.md",
            "architecture.md",
            "cli-reference.md",
        ]

        for doc_file in doc_files:
            content = (docs_dir / doc_file).read_text()
            # Should have at least one header
            assert "#" in content, f"{doc_file} should have headers"
            # Should not be empty
            assert len(content) > 100, f"{doc_file} should have content"

    def test_code_blocks_formatted_correctly(self, docs_dir: Path) -> None:
        """Test that code blocks use proper markdown syntax."""
        # Check a few key files that should have code blocks
        content = (docs_dir / "getting-started.md").read_text()

        # Should have code blocks (triple backticks)
        assert "```" in content or "`" in content

    def test_links_use_markdown_format(self, docs_dir: Path) -> None:
        """Test that internal links use markdown format."""
        # Links to other docs should use [text](file.md) format
        content = (docs_dir / "getting-started.md").read_text()

        # Check that references to other docs exist
        # (May be in "See also" or "For more information" sections)
        has_doc_references = (
            "configuration.md" in content.lower()
            or "spec-formats.md" in content.lower()
            or "cli-reference.md" in content.lower()
        )

        assert has_doc_references, "Should reference other documentation"
