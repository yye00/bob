"""Verify that ``tests/`` is an importable package and the skeleton helper
that guarantees this behaves correctly.

WHEN a test does ``from tests.X import Y`` THEN collection succeeds because
``tests/`` is a package (has an ``__init__.py``).
"""

from __future__ import annotations

import importlib
from pathlib import Path

from bob.skeleton_tests_package import ensure_tests_package


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_tests_init_file_exists():
    """tests/__init__.py exists so ``tests`` resolves as a package."""
    assert (_PROJECT_ROOT / "tests" / "__init__.py").exists()


def test_tests_is_importable_as_package():
    """The ``tests`` package can actually be imported."""
    module = importlib.import_module("tests")
    assert module is not None
    assert hasattr(module, "__path__")


def test_ensure_creates_missing_tests_init(tmp_path):
    """ensure_tests_package creates tests/__init__.py when absent."""
    (tmp_path / "tests").mkdir()
    result = ensure_tests_package(tmp_path)
    assert "tests/__init__.py" in result.created
    assert (tmp_path / "tests" / "__init__.py").exists()
    assert result.tests_package_ok is True


def test_ensure_is_idempotent(tmp_path):
    """A second call reports the file as existing, not created."""
    (tmp_path / "tests").mkdir()
    ensure_tests_package(tmp_path)
    result = ensure_tests_package(tmp_path)
    assert "tests/__init__.py" in result.existing
    assert result.created == []
    assert result.tests_package_ok is True


def test_ensure_creates_empty_init(tmp_path):
    """The created tests/__init__.py is empty (a bare package marker)."""
    (tmp_path / "tests").mkdir()
    ensure_tests_package(tmp_path)
    content = (tmp_path / "tests" / "__init__.py").read_text(encoding="utf-8")
    assert content == ""


def test_ensure_src_package_init_created_for_package_style(tmp_path):
    """When src/ holds package dirs, src/__init__.py is created too."""
    (tmp_path / "tests").mkdir()
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    result = ensure_tests_package(tmp_path)
    assert "src/__init__.py" in result.created
    assert (tmp_path / "src" / "__init__.py").exists()


def test_cross_test_import_style_resolves(tmp_path, monkeypatch):
    """A ``from tests.helper import value`` style import resolves once the
    package marker exists (simulated in an isolated project root)."""
    import sys

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "helper.py").write_text("VALUE = 42\n", encoding="utf-8")
    ensure_tests_package(tmp_path)

    monkeypatch.syspath_prepend(str(tmp_path))
    # Drop any real ``tests`` package cached from this repo for the lookup.
    for name in list(sys.modules):
        if name == "tests" or name.startswith("tests."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    mod = importlib.import_module("tests.helper")
    assert mod.VALUE == 42
