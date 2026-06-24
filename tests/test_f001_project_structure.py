"""Tests for F001: Basic project structure."""

import importlib
import pathlib

import pytest

# The workspace root for this bob.1 build
WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


class TestDirectoryStructure:
    """Verify that the src/bob/ directory structure exists."""

    def test_src_directory_exists(self):
        assert (WORKSPACE / "src").is_dir()

    def test_bob_package_directory_exists(self):
        assert (WORKSPACE / "src" / "bob").is_dir()

    def test_bob_init_exists(self):
        assert (WORKSPACE / "src" / "bob" / "__init__.py").is_file()

    def test_orchestrator_directory_exists(self):
        assert (WORKSPACE / "src" / "bob" / "orchestrator").is_dir()

    def test_orchestrator_init_exists(self):
        assert (WORKSPACE / "src" / "bob" / "orchestrator" / "__init__.py").is_file()


class TestBobPackage:
    """Verify that the bob package is importable and has expected attributes."""

    def test_bob_is_importable(self):
        import bob
        assert bob is not None

    def test_version_is_set(self):
        import bob
        assert bob.__version__ == "0.2.0"

    def test_app_name_is_set(self):
        import bob
        assert bob.__app_name__ == "Bob"

    def test_get_package_dir_returns_path(self):
        import bob
        pkg_dir = bob.get_package_dir()
        assert isinstance(pkg_dir, pathlib.Path)
        assert pkg_dir.is_dir()
        assert pkg_dir.name == "bob"

    def test_get_version(self):
        import bob
        assert bob.get_version() == "0.2.0"

    def test_get_schema_path(self):
        import bob
        schema_path = bob.get_schema_path()
        assert isinstance(schema_path, pathlib.Path)
        assert schema_path.name == "schema.sql"

    def test_has_subpackage_orchestrator(self):
        import bob
        assert bob.has_subpackage("orchestrator") is True

    def test_has_subpackage_nonexistent(self):
        import bob
        assert bob.has_subpackage("nonexistent_subpackage_xyz") is False


class TestOrchestratorPackage:
    """Verify that the orchestrator subpackage is importable and functional."""

    def test_orchestrator_is_importable(self):
        from bob import orchestrator
        assert orchestrator is not None

    def test_get_orchestrator_dir(self):
        from bob.orchestrator import get_orchestrator_dir
        orc_dir = get_orchestrator_dir()
        assert isinstance(orc_dir, pathlib.Path)
        assert orc_dir.is_dir()
        assert orc_dir.name == "orchestrator"

    def test_get_orchestrator_modules_returns_list(self):
        from bob.orchestrator import get_orchestrator_modules
        modules = get_orchestrator_modules()
        assert isinstance(modules, list)
