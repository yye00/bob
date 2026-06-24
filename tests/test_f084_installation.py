"""Tests for F084: Ensure pyproject.toml supports installation and bob3 CLI works."""

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
    """Step 2: Add [project.scripts] for bob3 CLI entry point."""

    @pytest.fixture(autouse=True)
    def load_pyproject(self):
        with open(PYPROJECT_PATH, "rb") as f:
            self.data = tomllib.load(f)

    def test_project_scripts_section_exists(self):
        scripts = self.data.get("project", {}).get("scripts", {})
        assert len(scripts) > 0, "pyproject.toml must have [project.scripts] section"

    def test_bob3_entry_point_defined(self):
        scripts = self.data["project"]["scripts"]
        assert "bob3" in scripts, "bob3 entry point must be defined in [project.scripts]"

    def test_bob3_entry_point_targets_cli_main(self):
        scripts = self.data["project"]["scripts"]
        assert scripts["bob3"] == "bob3.cli:main", "bob3 entry point must target bob3.cli:main"


class TestInstallation:
    """Step 3: Test: pip install -e ., verify bob3 command is available."""

    def test_bob3_command_is_available(self):
        bob3_path = shutil.which("bob3")
        assert bob3_path is not None, "bob3 command must be available on PATH after installation"

    def test_bob3_module_is_importable(self):
        import bob3
        assert hasattr(bob3, "__version__")

    def test_bob3_cli_module_is_importable(self):
        from bob3.cli import main
        assert callable(main)


class TestVersionCommand:
    """Step 4: Test: bob3 --version works."""

    def test_bob3_version_exits_zero(self):
        result = subprocess.run(
            ["bob3", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"bob3 --version must exit 0, got {result.returncode}: {result.stderr}"

    def test_bob3_version_output_contains_version(self):
        result = subprocess.run(
            ["bob3", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        import bob3
        assert bob3.__version__ in result.stdout, (
            f"bob3 --version output must contain version '{bob3.__version__}', got: {result.stdout}"
        )

    def test_bob3_version_matches_pyproject(self):
        with open(PYPROJECT_PATH, "rb") as f:
            data = tomllib.load(f)
        pyproject_version = data["project"]["version"]

        import bob3
        assert bob3.__version__ == pyproject_version, (
            f"__init__.py version ({bob3.__version__}) must match pyproject.toml version ({pyproject_version})"
        )

    def test_bob3_version_output_contains_prog_name(self):
        result = subprocess.run(
            ["bob3", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "bob3" in result.stdout.lower(), (
            f"bob3 --version output must contain 'bob3', got: {result.stdout}"
        )
