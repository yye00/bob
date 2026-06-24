"""Tests for is_local_module function in bob3.security.slopsquatting_scan."""
from __future__ import annotations

import pytest
from pathlib import Path
from bob3.security.slopsquatting_scan import is_local_module


@pytest.fixture
def fixture_tree(tmp_path: Path) -> Path:
    """Create a fixture src/bob3 tree with example_local.py and example_pkg/__init__.py."""
    src_bob3 = tmp_path / "src" / "bob3"
    src_bob3.mkdir(parents=True)
    # A single .py file module
    (src_bob3 / "example_local.py").write_text("# local module\n")
    # A package
    pkg_dir = src_bob3 / "example_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("# example package\n")
    return tmp_path


def test_is_local_module_returns_true_for_py_file(fixture_tree: Path) -> None:
    """is_local_module returns True for a .py file at src/bob3/example_local.py."""
    py_file = fixture_tree / "src" / "bob3" / "example_local.py"
    assert is_local_module(py_file) is True


def test_is_local_module_returns_true_for_package_init(fixture_tree: Path) -> None:
    """is_local_module returns True for a package's __init__.py."""
    init_file = fixture_tree / "src" / "bob3" / "example_pkg" / "__init__.py"
    assert is_local_module(init_file) is True


def test_is_local_module_returns_false_for_nonexistent_file(tmp_path: Path) -> None:
    """is_local_module returns False for a file that does not exist."""
    nonexistent = tmp_path / "src" / "bob3" / "does_not_exist.py"
    assert is_local_module(nonexistent) is False


def test_is_local_module_returns_false_for_dir_without_init(tmp_path: Path) -> None:
    """is_local_module returns False for a directory without __init__.py."""
    src_bob3 = tmp_path / "src" / "bob3"
    src_bob3.mkdir(parents=True)
    bare_dir = src_bob3 / "bare_dir"
    bare_dir.mkdir()
    assert is_local_module(bare_dir) is False


def test_is_local_module_returns_false_for_non_python_file(tmp_path: Path) -> None:
    """is_local_module returns False for a non-.py file."""
    src_bob3 = tmp_path / "src" / "bob3"
    src_bob3.mkdir(parents=True)
    txt_file = src_bob3 / "some_file.txt"
    txt_file.write_text("not python")
    assert is_local_module(txt_file) is False
