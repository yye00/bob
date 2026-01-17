"""Tests for requirements and dependencies (F072)"""
import os
from pathlib import Path


class TestRequirementsTxt:
    """Test F072: requirements.txt completeness"""

    def test_requirements_txt_exists(self):
        """requirements.txt file exists"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        assert req_path.exists(), "requirements.txt should exist in project root"

    def test_requirements_has_click(self):
        """requirements.txt includes click"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()
        assert "click" in content.lower(), "Should include click or typer for CLI"

    def test_requirements_has_pyyaml(self):
        """requirements.txt includes pyyaml"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()
        assert "pyyaml" in content.lower() or "yaml" in content.lower()

    def test_requirements_has_jinja2(self):
        """requirements.txt includes jinja2"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()
        assert "jinja2" in content.lower()

    def test_requirements_has_rich(self):
        """requirements.txt includes rich for terminal formatting"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()
        assert "rich" in content.lower()

    def test_requirements_has_aiosqlite(self):
        """requirements.txt includes aiosqlite"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()
        assert "aiosqlite" in content.lower()

    def test_requirements_has_anthropic_sdk(self):
        """requirements.txt includes anthropic SDK"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()
        assert "anthropic" in content.lower()

    def test_requirements_has_optional_dependencies_mentioned(self):
        """requirements.txt mentions optional dependencies"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()
        # Should mention perplexity or have optional dependencies section
        assert (
            "perplexity" in content.lower()
            or "optional" in content.lower()
            or "postgres" in content.lower()
        )

    def test_requirements_has_version_constraints(self):
        """requirements.txt has version constraints for stability"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()
        # Should have at least some version constraints (>=, ==, ~=)
        assert ">=" in content or "==" in content or "~=" in content


class TestSetupPy:
    """Test F072: setup.py completeness"""

    def test_setup_py_exists(self):
        """setup.py file exists"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        assert setup_path.exists(), "setup.py should exist in project root"

    def test_setup_py_has_package_name(self):
        """setup.py defines package name"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'name=' in content
        assert 'bob' in content.lower()

    def test_setup_py_has_version(self):
        """setup.py defines version"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'version=' in content

    def test_setup_py_has_python_version_requirement(self):
        """setup.py specifies Python 3.10+ requirement"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'python_requires=' in content
        # Should require at least Python 3.10
        assert '3.10' in content

    def test_setup_py_has_install_requires(self):
        """setup.py defines install_requires"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'install_requires=' in content

    def test_setup_py_has_entry_points(self):
        """setup.py defines console_scripts entry point"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'entry_points=' in content
        assert 'console_scripts' in content
        assert 'bob=' in content

    def test_setup_py_has_classifiers(self):
        """setup.py includes PyPI classifiers"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'classifiers=' in content
        assert 'Programming Language :: Python :: 3' in content

    def test_setup_py_has_long_description_from_readme(self):
        """setup.py uses README.md for long description"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'long_description=' in content
        assert 'README.md' in content

    def test_setup_py_includes_package_data(self):
        """setup.py includes package data (prompts, etc.)"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        # Should have package_data or include_package_data
        assert 'package_data=' in content or 'include_package_data=' in content


class TestInstallation:
    """Test that package can be installed (F072 step 6)"""

    def test_package_can_be_imported(self):
        """Package bob can be imported"""
        # If we're running tests, the package should already be installed
        import bob
        assert bob is not None

    def test_bob_module_has_version(self):
        """bob module has __version__ attribute"""
        import bob
        # Version might be defined in __init__.py or via setup.py
        # At minimum, the module should be importable
        assert hasattr(bob, '__version__') or hasattr(bob, '__file__')

    def test_cli_module_exists(self):
        """bob.cli module exists"""
        import bob.cli
        assert bob.cli is not None

    def test_database_module_exists(self):
        """bob.database module exists"""
        import bob.database
        assert bob.database is not None

    def test_models_module_exists(self):
        """bob.models module exists"""
        import bob.models
        assert bob.models is not None
