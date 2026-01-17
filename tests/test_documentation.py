"""Tests for documentation completeness (F070, F071, etc.)"""
import os
from pathlib import Path


class TestReadmeDocumentation:
    """Test F070: README.md completeness"""

    def test_readme_exists(self):
        """README.md file exists"""
        readme_path = Path(__file__).parent.parent / "README.md"
        assert readme_path.exists(), "README.md should exist in project root"

    def test_readme_has_project_overview(self):
        """README has project overview section"""
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text()
        assert "# BOB: Build Orchestration Bot" in content
        assert "generalized, production-ready autonomous coding framework" in content

    def test_readme_has_why_bob_section(self):
        """README has 'Why BOB?' section explaining vision"""
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text()
        assert "## Why BOB?" in content
        assert "autonomous-coding" in content.lower()

    def test_readme_has_installation_instructions(self):
        """README has installation instructions"""
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text()
        assert "## Quick Start" in content or "### Installation" in content
        assert "git clone" in content
        assert "init.sh" in content or "pip install" in content

    def test_readme_has_quick_start_guide(self):
        """README has quick start guide"""
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text()
        assert "## Quick Start" in content
        assert "bob project create" in content

    def test_readme_has_cli_commands_with_examples(self):
        """README documents CLI commands with examples"""
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text()
        assert "## CLI Reference" in content or "CLI" in content
        # Should have command examples
        assert "bob project" in content
        assert "bob task" in content
        assert "bob run" in content

    def test_readme_has_architecture_diagram(self):
        """README includes architecture diagram"""
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text()
        assert "## Architecture" in content
        # ASCII diagram markers
        assert "┌─" in content or "BOB CLI" in content

    def test_readme_has_comparison_with_autonomous_coding(self):
        """README includes comparison with autonomous-coding"""
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text()
        # Should have a comparison table or section
        assert "autonomous-coding" in content.lower() or "Autonomous-Coding" in content
        # Check for table comparison
        assert "| Feature |" in content or "Autonomous Coding" in content

    def test_readme_has_contributing_guidelines(self):
        """README references contributing guidelines"""
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text()
        assert "## Contributing" in content or "CONTRIBUTING.md" in content

    def test_readme_has_license_information(self):
        """README includes license information"""
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text()
        assert "## License" in content or "LICENSE" in content
        assert "MIT" in content


class TestContributingDocumentation:
    """Test that CONTRIBUTING.md exists and is comprehensive"""

    def test_contributing_exists(self):
        """CONTRIBUTING.md file exists"""
        contributing_path = Path(__file__).parent.parent / "CONTRIBUTING.md"
        assert contributing_path.exists(), "CONTRIBUTING.md should exist"

    def test_contributing_has_development_setup(self):
        """CONTRIBUTING.md has development setup instructions"""
        contributing_path = Path(__file__).parent.parent / "CONTRIBUTING.md"
        content = contributing_path.read_text()
        assert "Development Setup" in content or "Setup" in content
        assert "init.sh" in content or "pip install" in content

    def test_contributing_has_code_style(self):
        """CONTRIBUTING.md has code style guidelines"""
        contributing_path = Path(__file__).parent.parent / "CONTRIBUTING.md"
        content = contributing_path.read_text()
        assert "Code Style" in content or "style" in content.lower()

    def test_contributing_has_testing_guidelines(self):
        """CONTRIBUTING.md has testing guidelines"""
        contributing_path = Path(__file__).parent.parent / "CONTRIBUTING.md"
        content = contributing_path.read_text()
        assert "Testing" in content or "test" in content.lower()
        assert "pytest" in content

    def test_contributing_has_pr_process(self):
        """CONTRIBUTING.md has pull request process"""
        contributing_path = Path(__file__).parent.parent / "CONTRIBUTING.md"
        content = contributing_path.read_text()
        assert "Pull Request" in content or "PR" in content


class TestLicenseDocumentation:
    """Test that LICENSE file exists"""

    def test_license_exists(self):
        """LICENSE file exists"""
        license_path = Path(__file__).parent.parent / "LICENSE"
        assert license_path.exists(), "LICENSE file should exist"

    def test_license_is_mit(self):
        """LICENSE is MIT license"""
        license_path = Path(__file__).parent.parent / "LICENSE"
        content = license_path.read_text()
        assert "MIT License" in content
        assert "Permission is hereby granted" in content
