"""Tests for F001: Basic project structure."""

import importlib
import pathlib

import pytest

# The workspace root for this bob3.1 build
WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


class TestDirectoryStructure:
    """Verify that the src/bob3/ directory structure exists."""

    def test_src_directory_exists(self):
        assert (WORKSPACE / "src").is_dir()

    def test_bob3_package_directory_exists(self):
        assert (WORKSPACE / "src" / "bob3").is_dir()

    def test_bob3_init_exists(self):
        assert (WORKSPACE / "src" / "bob3" / "__init__.py").is_file()

    def test_orchestrator_directory_exists(self):
        assert (WORKSPACE / "src" / "bob3" / "orchestrator").is_dir()

    def test_orchestrator_init_exists(self):
        assert (WORKSPACE / "src" / "bob3" / "orchestrator" / "__init__.py").is_file()


class TestBob3Package:
    """Verify that the bob3 package is importable and has expected attributes."""

    def test_bob3_is_importable(self):
        import bob3
        assert bob3 is not None

    def test_version_is_set(self):
        import bob3
        assert bob3.__version__ == "0.2.0"

    def test_app_name_is_set(self):
        import bob3
        assert bob3.__app_name__ == "Bob3"

    def test_get_package_dir_returns_path(self):
        import bob3
        pkg_dir = bob3.get_package_dir()
        assert isinstance(pkg_dir, pathlib.Path)
        assert pkg_dir.is_dir()
        assert pkg_dir.name == "bob3"

    def test_get_version(self):
        import bob3
        assert bob3.get_version() == "0.2.0"

    def test_get_schema_path(self):
        import bob3
        schema_path = bob3.get_schema_path()
        assert isinstance(schema_path, pathlib.Path)
        assert schema_path.name == "schema.sql"

    def test_has_subpackage_orchestrator(self):
        import bob3
        assert bob3.has_subpackage("orchestrator") is True

    def test_has_subpackage_nonexistent(self):
        import bob3
        assert bob3.has_subpackage("nonexistent_subpackage_xyz") is False


class TestOrchestratorPackage:
    """Verify that the orchestrator subpackage is importable and functional."""

    def test_orchestrator_is_importable(self):
        from bob3 import orchestrator
        assert orchestrator is not None

    def test_get_orchestrator_dir(self):
        from bob3.orchestrator import get_orchestrator_dir
        orc_dir = get_orchestrator_dir()
        assert isinstance(orc_dir, pathlib.Path)
        assert orc_dir.is_dir()
        assert orc_dir.name == "orchestrator"

    def test_get_orchestrator_modules_returns_list(self):
        from bob3.orchestrator import get_orchestrator_modules
        modules = get_orchestrator_modules()
        assert isinstance(modules, list)
