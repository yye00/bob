"""
Tests for F073: Package distribution - PyPI publication readiness

These tests verify that the package is properly configured for distribution:
- setup.py with complete metadata
- MANIFEST.in for package files
- .gitignore for Python project
- Package can be built (sdist and wheel)
- Package can be installed from wheel
- 'bob' command is available after install
"""

import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import pytest


class TestSetupPy:
    """Test setup.py configuration"""

    def test_setup_py_exists(self):
        """setup.py file should exist"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        assert setup_path.exists(), "setup.py should exist"

    def test_setup_py_has_name(self):
        """setup.py should define package name"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'name="bob-framework"' in content, "Package name should be defined"

    def test_setup_py_has_version(self):
        """setup.py should define version"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'version=' in content, "Version should be defined"

    def test_setup_py_has_author(self):
        """setup.py should define author"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'author=' in content, "Author should be defined"
        assert 'author_email=' in content, "Author email should be defined"

    def test_setup_py_has_description(self):
        """setup.py should define description"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'description=' in content, "Description should be defined"
        assert 'long_description=' in content, "Long description should be defined"

    def test_setup_py_has_classifiers(self):
        """setup.py should define classifiers"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'classifiers=' in content, "Classifiers should be defined"
        assert 'Development Status' in content, "Development status classifier should exist"
        assert 'Intended Audience' in content, "Intended audience classifier should exist"
        assert 'License ::' in content, "License classifier should exist"
        assert 'Programming Language :: Python' in content, "Python version classifiers should exist"

    def test_setup_py_has_keywords(self):
        """setup.py should define keywords"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'keywords=' in content, "Keywords should be defined"

    def test_setup_py_has_project_urls(self):
        """setup.py should define project URLs"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'project_urls=' in content or 'url=' in content, "Project URLs should be defined"

    def test_setup_py_has_entry_points(self):
        """setup.py should define console entry points"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'entry_points=' in content, "Entry points should be defined"
        assert 'console_scripts' in content, "Console scripts should be defined"
        assert 'bob=' in content, "bob command should be defined"

    def test_setup_py_has_install_requires(self):
        """setup.py should define install_requires"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        assert 'install_requires=' in content, "install_requires should be defined"

    def test_setup_py_has_package_data(self):
        """setup.py should include package data (prompts, schema)"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        content = setup_path.read_text()
        # Should have either package_data or include_package_data
        has_package_data = 'package_data=' in content or 'include_package_data=' in content
        assert has_package_data, "Package data configuration should exist"


class TestManifestIn:
    """Test MANIFEST.in configuration"""

    def test_manifest_in_exists(self):
        """MANIFEST.in file should exist"""
        manifest_path = Path(__file__).parent.parent / "MANIFEST.in"
        assert manifest_path.exists(), "MANIFEST.in should exist"

    def test_manifest_includes_readme(self):
        """MANIFEST.in should include README.md"""
        manifest_path = Path(__file__).parent.parent / "MANIFEST.in"
        content = manifest_path.read_text()
        assert 'README.md' in content, "MANIFEST.in should include README.md"

    def test_manifest_includes_license(self):
        """MANIFEST.in should include LICENSE"""
        manifest_path = Path(__file__).parent.parent / "MANIFEST.in"
        content = manifest_path.read_text()
        assert 'LICENSE' in content, "MANIFEST.in should include LICENSE"

    def test_manifest_includes_prompts(self):
        """MANIFEST.in should include prompt templates"""
        manifest_path = Path(__file__).parent.parent / "MANIFEST.in"
        content = manifest_path.read_text()
        # Should recursively include prompts directory or specific .md files
        has_prompts = 'prompts' in content or '*.md' in content
        assert has_prompts, "MANIFEST.in should include prompt templates"

    def test_manifest_includes_schema(self):
        """MANIFEST.in should include database schema"""
        manifest_path = Path(__file__).parent.parent / "MANIFEST.in"
        content = manifest_path.read_text()
        # Should include database schema
        has_schema = 'schema.sql' in content or 'database' in content
        assert has_schema, "MANIFEST.in should include database schema"

    def test_manifest_excludes_build_artifacts(self):
        """MANIFEST.in should exclude build artifacts"""
        manifest_path = Path(__file__).parent.parent / "MANIFEST.in"
        content = manifest_path.read_text()
        # Should have global-exclude or prune for common artifacts
        excludes_artifacts = (
            '__pycache__' in content or
            '*.pyc' in content or
            'global-exclude' in content
        )
        assert excludes_artifacts, "MANIFEST.in should exclude build artifacts"


class TestGitignore:
    """Test .gitignore configuration"""

    def test_gitignore_exists(self):
        """.gitignore file should exist"""
        gitignore_path = Path(__file__).parent.parent / ".gitignore"
        assert gitignore_path.exists(), ".gitignore should exist"

    def test_gitignore_has_python_patterns(self):
        """.gitignore should ignore Python artifacts"""
        gitignore_path = Path(__file__).parent.parent / ".gitignore"
        content = gitignore_path.read_text()
        assert '__pycache__' in content, ".gitignore should include __pycache__"
        assert '*.pyc' in content or '*.py[cod]' in content, ".gitignore should include .pyc files"

    def test_gitignore_has_build_patterns(self):
        """.gitignore should ignore build directories"""
        gitignore_path = Path(__file__).parent.parent / ".gitignore"
        content = gitignore_path.read_text()
        assert 'build/' in content, ".gitignore should include build/"
        assert 'dist/' in content, ".gitignore should include dist/"
        assert '*.egg-info' in content, ".gitignore should include *.egg-info"

    def test_gitignore_has_venv_patterns(self):
        """.gitignore should ignore virtual environments"""
        gitignore_path = Path(__file__).parent.parent / ".gitignore"
        content = gitignore_path.read_text()
        has_venv = 'venv/' in content or '.venv' in content or 'env/' in content
        assert has_venv, ".gitignore should ignore virtual environments"

    def test_gitignore_has_test_patterns(self):
        """.gitignore should ignore test artifacts"""
        gitignore_path = Path(__file__).parent.parent / ".gitignore"
        content = gitignore_path.read_text()
        has_test_artifacts = '.pytest_cache' in content or '.coverage' in content
        assert has_test_artifacts, ".gitignore should ignore test artifacts"


class TestRequirementsTxt:
    """Test requirements.txt file"""

    def test_requirements_txt_exists(self):
        """requirements.txt file should exist"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        assert req_path.exists(), "requirements.txt should exist"

    def test_requirements_has_core_deps(self):
        """requirements.txt should list core dependencies"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()

        # Core dependencies for BOB
        core_deps = ['click', 'anthropic', 'rich', 'jinja2', 'pyyaml']

        for dep in core_deps:
            assert dep in content.lower(), f"requirements.txt should include {dep}"


class TestPackageBuild:
    """Test package building"""

    def test_package_can_be_built(self):
        """Package should be buildable with setup.py"""
        project_root = Path(__file__).parent.parent

        # Clean previous builds
        dist_dir = project_root / "dist"
        build_dir = project_root / "build"

        # Run build command
        result = subprocess.run(
            [sys.executable, "setup.py", "sdist", "bdist_wheel"],
            cwd=project_root,
            capture_output=True,
            text=True
        )

        # Should succeed (exit code 0)
        if result.returncode != 0:
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")

        assert result.returncode == 0, f"Package build should succeed: {result.stderr}"

    def test_sdist_created(self):
        """Source distribution should be created"""
        project_root = Path(__file__).parent.parent
        dist_dir = project_root / "dist"

        # Find .tar.gz file
        sdist_files = list(dist_dir.glob("bob_framework-*.tar.gz"))
        assert len(sdist_files) > 0, "Source distribution (.tar.gz) should be created"

    def test_wheel_created(self):
        """Wheel distribution should be created"""
        project_root = Path(__file__).parent.parent
        dist_dir = project_root / "dist"

        # Find .whl file
        wheel_files = list(dist_dir.glob("bob_framework-*.whl"))
        assert len(wheel_files) > 0, "Wheel distribution (.whl) should be created"

    def test_sdist_contains_required_files(self):
        """Source distribution should contain required files"""
        project_root = Path(__file__).parent.parent
        dist_dir = project_root / "dist"

        sdist_files = list(dist_dir.glob("bob_framework-*.tar.gz"))
        if not sdist_files:
            pytest.skip("No sdist found")

        sdist_path = sdist_files[0]

        # Check contents
        with tarfile.open(sdist_path, "r:gz") as tar:
            names = tar.getnames()

            # Should contain essential files
            has_readme = any('README.md' in name for name in names)
            has_license = any('LICENSE' in name for name in names)
            has_setup = any('setup.py' in name for name in names)

            assert has_readme, "sdist should contain README.md"
            assert has_license, "sdist should contain LICENSE"
            assert has_setup, "sdist should contain setup.py"

    def test_wheel_contains_package(self):
        """Wheel should contain the bob package"""
        project_root = Path(__file__).parent.parent
        dist_dir = project_root / "dist"

        wheel_files = list(dist_dir.glob("bob_framework-*.whl"))
        if not wheel_files:
            pytest.skip("No wheel found")

        wheel_path = wheel_files[0]

        # Check contents
        with zipfile.ZipFile(wheel_path, 'r') as zip_file:
            names = zip_file.namelist()

            # Should contain bob package
            has_bob_package = any(name.startswith('bob/') for name in names)
            has_cli_module = any('bob/cli/' in name for name in names)
            has_entry_points = any('entry_points.txt' in name for name in names)

            assert has_bob_package, "Wheel should contain bob/ package"
            assert has_cli_module, "Wheel should contain bob/cli/ module"
            assert has_entry_points, "Wheel should contain entry_points.txt"

    def test_wheel_contains_prompts(self):
        """Wheel should contain prompt template files"""
        project_root = Path(__file__).parent.parent
        dist_dir = project_root / "dist"

        wheel_files = list(dist_dir.glob("bob_framework-*.whl"))
        if not wheel_files:
            pytest.skip("No wheel found")

        wheel_path = wheel_files[0]

        with zipfile.ZipFile(wheel_path, 'r') as zip_file:
            names = zip_file.namelist()

            # Should contain prompt templates
            has_prompts = any('.md' in name and 'bob/prompts/' in name for name in names)
            assert has_prompts, "Wheel should contain prompt template files"

    def test_wheel_contains_schema(self):
        """Wheel should contain database schema"""
        project_root = Path(__file__).parent.parent
        dist_dir = project_root / "dist"

        wheel_files = list(dist_dir.glob("bob_framework-*.whl"))
        if not wheel_files:
            pytest.skip("No wheel found")

        wheel_path = wheel_files[0]

        with zipfile.ZipFile(wheel_path, 'r') as zip_file:
            names = zip_file.namelist()

            # Should contain schema.sql
            has_schema = any('schema.sql' in name for name in names)
            assert has_schema, "Wheel should contain schema.sql"


class TestPackageInstallation:
    """Test package installation from wheel"""

    def test_package_can_be_installed(self):
        """Package should be installable from wheel"""
        project_root = Path(__file__).parent.parent
        dist_dir = project_root / "dist"

        wheel_files = list(dist_dir.glob("bob_framework-*.whl"))
        if not wheel_files:
            pytest.skip("No wheel found - run build test first")

        wheel_path = wheel_files[0]

        # Create temporary venv and install
        with tempfile.TemporaryDirectory() as tmpdir:
            venv_dir = Path(tmpdir) / "test_venv"

            # Create venv
            result = subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                capture_output=True
            )
            assert result.returncode == 0, "venv creation should succeed"

            # Install wheel
            pip_path = venv_dir / "bin" / "pip"
            if not pip_path.exists():
                pip_path = venv_dir / "Scripts" / "pip.exe"  # Windows

            result = subprocess.run(
                [str(pip_path), "install", str(wheel_path)],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")

            assert result.returncode == 0, f"Package installation should succeed: {result.stderr}"

    def test_bob_command_available_after_install(self):
        """'bob' command should be available after installation"""
        project_root = Path(__file__).parent.parent
        dist_dir = project_root / "dist"

        wheel_files = list(dist_dir.glob("bob_framework-*.whl"))
        if not wheel_files:
            pytest.skip("No wheel found - run build test first")

        wheel_path = wheel_files[0]

        # Create temporary venv and install
        with tempfile.TemporaryDirectory() as tmpdir:
            venv_dir = Path(tmpdir) / "test_venv"

            # Create venv
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                capture_output=True
            )

            # Install wheel
            pip_path = venv_dir / "bin" / "pip"
            if not pip_path.exists():
                pip_path = venv_dir / "Scripts" / "pip.exe"  # Windows

            subprocess.run(
                [str(pip_path), "install", str(wheel_path)],
                capture_output=True
            )

            # Check if bob command exists
            bob_path = venv_dir / "bin" / "bob"
            if not bob_path.exists():
                bob_path = venv_dir / "Scripts" / "bob.exe"  # Windows

            assert bob_path.exists(), "'bob' command should be installed"

    def test_bob_command_executes(self):
        """'bob' command should execute successfully"""
        project_root = Path(__file__).parent.parent
        dist_dir = project_root / "dist"

        wheel_files = list(dist_dir.glob("bob_framework-*.whl"))
        if not wheel_files:
            pytest.skip("No wheel found - run build test first")

        wheel_path = wheel_files[0]

        # Create temporary venv and install
        with tempfile.TemporaryDirectory() as tmpdir:
            venv_dir = Path(tmpdir) / "test_venv"

            # Create venv
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                capture_output=True
            )

            # Install wheel
            pip_path = venv_dir / "bin" / "pip"
            python_path = venv_dir / "bin" / "python"
            if not pip_path.exists():
                pip_path = venv_dir / "Scripts" / "pip.exe"  # Windows
                python_path = venv_dir / "Scripts" / "python.exe"

            subprocess.run(
                [str(pip_path), "install", str(wheel_path)],
                capture_output=True
            )

            # Run bob command via python module
            result = subprocess.run(
                [str(python_path), "-m", "bob.cli.main", "--version"],
                capture_output=True,
                text=True
            )

            assert result.returncode == 0, "bob command should execute successfully"
            assert "bob" in result.stdout.lower() or "0.1.0" in result.stdout, \
                "bob command should output version information"

    def test_package_imports_successfully(self):
        """bob package should be importable after installation"""
        project_root = Path(__file__).parent.parent
        dist_dir = project_root / "dist"

        wheel_files = list(dist_dir.glob("bob_framework-*.whl"))
        if not wheel_files:
            pytest.skip("No wheel found - run build test first")

        wheel_path = wheel_files[0]

        # Create temporary venv and install
        with tempfile.TemporaryDirectory() as tmpdir:
            venv_dir = Path(tmpdir) / "test_venv"

            # Create venv
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                capture_output=True
            )

            # Install wheel
            pip_path = venv_dir / "bin" / "pip"
            python_path = venv_dir / "bin" / "python"
            if not pip_path.exists():
                pip_path = venv_dir / "Scripts" / "pip.exe"  # Windows
                python_path = venv_dir / "Scripts" / "python.exe"

            subprocess.run(
                [str(pip_path), "install", str(wheel_path)],
                capture_output=True
            )

            # Try importing bob
            result = subprocess.run(
                [str(python_path), "-c", "import bob; import bob.cli.main; print('Success')"],
                capture_output=True,
                text=True
            )

            assert result.returncode == 0, "bob package should be importable"
            assert "Success" in result.stdout, "Import should succeed"
