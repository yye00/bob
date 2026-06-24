"""Tests for F084: Ensure pyproject.toml supports installation and bob CLI works."""

import pathlib
import shutil
import subprocess
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

import pytest

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT_PATH = WORKSPACE / "pyproject.toml"


class TestBuildSystemSection:
    """Step 1: Verify pyproject.toml has [build-system] section."""

    @pytest.fixture(autouse=True)
    def load_pyproject(self):
        with open(PYPROJECT_PATH, "rb") as f:
            self.data = tomllib.load(f)

    def test_build_system_section_exists(self):
        assert "build-system" in self.data, "pyproject.toml must have [build-system] section"

    def test_build_system_has_requires(self):
        requires = self.data["build-system"].get("requires", [])
        assert len(requires) > 0, "[build-system] must have 'requires' list"
        assert any("setuptools" in r for r in requires), "setuptools must be in build requires"

    def test_build_system_has_build_backend(self):
        backend = self.data["build-system"].get("build-backend", "")
        assert backend == "setuptools.build_meta", "build-backend must be setuptools.build_meta"


class TestProjectScripts:
    """Step 2: Add [project.scripts] for bob CLI entry point."""

    @pytest.fixture(autouse=True)
    def load_pyproject(self):
        with open(PYPROJECT_PATH, "rb") as f:
            self.data = tomllib.load(f)

    def test_project_scripts_section_exists(self):
        scripts = self.data.get("project", {}).get("scripts", {})
        assert len(scripts) > 0, "pyproject.toml must have [project.scripts] section"

    def test_bob_entry_point_defined(self):
        scripts = self.data["project"]["scripts"]
        assert "bob" in scripts, "bob entry point must be defined in [project.scripts]"

    def test_bob_entry_point_targets_cli_main(self):
        scripts = self.data["project"]["scripts"]
        assert scripts["bob"] == "bob.cli:main", "bob entry point must target bob.cli:main"


class TestInstallation:
    """Step 3: Test: pip install -e ., verify bob command is available."""

    def test_bob_command_is_available(self):
        bob_path = shutil.which("bob")
        assert bob_path is not None, "bob command must be available on PATH after installation"

    def test_bob_module_is_importable(self):
        import bob
        assert hasattr(bob, "__version__")

    def test_bob_cli_module_is_importable(self):
        from bob.cli import main
        assert callable(main)


class TestVersionCommand:
    """Step 4: Test: bob --version works."""

    def test_bob_version_exits_zero(self):
        result = subprocess.run(
            ["bob", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"bob --version must exit 0, got {result.returncode}: {result.stderr}"

    def test_bob_version_output_contains_version(self):
        result = subprocess.run(
            ["bob", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        import bob
        assert bob.__version__ in result.stdout, (
            f"bob --version output must contain version '{bob.__version__}', got: {result.stdout}"
        )

    def test_bob_version_matches_pyproject(self):
        with open(PYPROJECT_PATH, "rb") as f:
            data = tomllib.load(f)
        pyproject_version = data["project"]["version"]

        import bob
        assert bob.__version__ == pyproject_version, (
            f"__init__.py version ({bob.__version__}) must match pyproject.toml version ({pyproject_version})"
        )

    def test_bob_version_output_contains_prog_name(self):
        result = subprocess.run(
            ["bob", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "bob" in result.stdout.lower(), (
            f"bob --version output must contain 'bob', got: {result.stdout}"
        )
