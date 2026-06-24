"""Tests for F002: pyproject.toml with all required dependencies."""

import pathlib
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


class TestPyprojectExists:
    """Step 1: pyproject.toml must exist in project root."""

    def test_pyproject_toml_exists(self):
        assert PYPROJECT_PATH.is_file(), "pyproject.toml must exist in project root"

    def test_pyproject_toml_is_valid_toml(self):
        with open(PYPROJECT_PATH, "rb") as f:
            data = tomllib.load(f)
        assert isinstance(data, dict)


class TestProjectMetadata:
    """Step 2: Project metadata (name, version)."""

    @pytest.fixture(autouse=True)
    def load_pyproject(self):
        with open(PYPROJECT_PATH, "rb") as f:
            self.data = tomllib.load(f)

    def test_project_section_exists(self):
        assert "project" in self.data

    def test_project_name_is_bob3(self):
        assert self.data["project"]["name"] == "bob3"

    def test_project_version(self):
        assert self.data["project"]["version"] == "0.2.0"

    def test_project_has_description(self):
        assert "description" in self.data["project"]
        assert len(self.data["project"]["description"]) > 0

    def test_project_requires_python(self):
        assert "requires-python" in self.data["project"]


class TestDependencies:
    """Step 3: All required dependencies are listed."""

    REQUIRED_DEPS = {
        "claude-code-sdk": ">=0.0.25",
        "click": ">=8.0",
        "rich": ">=13.0",
        "pydantic": ">=2.0",
        "PyMuPDF": ">=1.23.0",
    }

    @pytest.fixture(autouse=True)
    def load_pyproject(self):
        with open(PYPROJECT_PATH, "rb") as f:
            self.data = tomllib.load(f)
        self.deps = self.data["project"].get("dependencies", [])

    def test_dependencies_section_exists(self):
        assert "dependencies" in self.data["project"]
        assert len(self.deps) > 0

    def _find_dep(self, name: str) -> str | None:
        """Find a dependency string by package name (case-insensitive)."""
        for dep in self.deps:
            dep_name = dep.split(">")[0].split("<")[0].split("=")[0].split("~")[0].split("!")[0].strip()
            if dep_name.lower() == name.lower():
                return dep
        return None

    def test_claude_code_sdk_dependency(self):
        dep = self._find_dep("claude-code-sdk")
        assert dep is not None, "claude-code-sdk must be in dependencies"
        assert ">=0.0.25" in dep

    def test_click_dependency(self):
        dep = self._find_dep("click")
        assert dep is not None, "click must be in dependencies"
        assert ">=8.0" in dep

    def test_rich_dependency(self):
        dep = self._find_dep("rich")
        assert dep is not None, "rich must be in dependencies"
        assert ">=13.0" in dep

    def test_pydantic_dependency(self):
        dep = self._find_dep("pydantic")
        assert dep is not None, "pydantic must be in dependencies"
        assert ">=2.0" in dep

    def test_pymupdf_dependency(self):
        dep = self._find_dep("PyMuPDF")
        assert dep is not None, "PyMuPDF must be in dependencies"
        assert ">=1.23.0" in dep

    def test_all_required_deps_present(self):
        """Verify every required dependency is present."""
        for name in self.REQUIRED_DEPS:
            dep = self._find_dep(name)
            assert dep is not None, f"Missing required dependency: {name}"


class TestBuildSystem:
    """Step 4: Build system configuration."""

    @pytest.fixture(autouse=True)
    def load_pyproject(self):
        with open(PYPROJECT_PATH, "rb") as f:
            self.data = tomllib.load(f)

    def test_build_system_section_exists(self):
        assert "build-system" in self.data

    def test_build_system_has_requires(self):
        assert "requires" in self.data["build-system"]
        requires = self.data["build-system"]["requires"]
        assert any("setuptools" in r for r in requires)

    def test_build_system_has_build_backend(self):
        assert "build-backend" in self.data["build-system"]
        assert self.data["build-system"]["build-backend"] == "setuptools.build_meta"


class TestClaudeCodeSdkPresence:
    """Step 5: Verify pyproject.toml is valid and contains claude-code-sdk."""

    def test_pyproject_contains_claude_code_sdk_text(self):
        content = PYPROJECT_PATH.read_text()
        assert "claude-code-sdk" in content

    def test_claude_code_sdk_has_minimum_version(self):
        content = PYPROJECT_PATH.read_text()
        assert "claude-code-sdk>=0.0.25" in content.replace(" ", "").replace('"', "").replace("'", "")
