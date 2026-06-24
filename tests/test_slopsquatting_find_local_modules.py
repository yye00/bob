"""Tests for find_local_modules function in bob.security.slopsquatting_scan."""
from __future__ import annotations

import pytest
from pathlib import Path
from bob.security.slopsquatting_scan import find_local_modules


@pytest.fixture
def fixture_tree(tmp_path: Path) -> Path:
    """Create a fixture src/bob tree with various modules."""
    src_bob = tmp_path / "src" / "bob"
    src_bob.mkdir(parents=True)
    # Single-file modules
    (src_bob / "module_a.py").write_text("# module a\n")
    (src_bob / "module_b.py").write_text("# module b\n")
    # Package
    pkg = src_bob / "my_package"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("# package\n")
    # __init__.py at the bob level itself (should NOT be included as a separate name)
    (src_bob / "__init__.py").write_text("")
    return tmp_path


def test_find_local_modules_includes_py_files(fixture_tree: Path) -> None:
    """find_local_modules returns module names for each <name>.py file."""
    modules = find_local_modules(fixture_tree)
    assert "module_a" in modules
    assert "module_b" in modules


def test_find_local_modules_includes_packages(fixture_tree: Path) -> None:
    """find_local_modules returns module names for packages with __init__.py."""
    modules = find_local_modules(fixture_tree)
    assert "my_package" in modules


def test_find_local_modules_returns_set(fixture_tree: Path) -> None:
    """find_local_modules returns a set."""
    result = find_local_modules(fixture_tree)
    assert isinstance(result, set)


def test_find_local_modules_excludes_init_itself(fixture_tree: Path) -> None:
    """find_local_modules does not include __init__ as a module name."""
    modules = find_local_modules(fixture_tree)
    assert "__init__" not in modules


def test_find_local_modules_only_top_level_names(fixture_tree: Path) -> None:
    """find_local_modules only returns top-level module names from src/bob/."""
    modules = find_local_modules(fixture_tree)
    # Should not include sub-sub items
    for name in modules:
        assert "." not in name


def test_find_local_modules_with_additional_py_file(tmp_path: Path) -> None:
    """find_local_modules finds each additional .py module in src/bob/."""
    src_bob = tmp_path / "src" / "bob"
    src_bob.mkdir(parents=True)
    (src_bob / "spec_quality_score.py").write_text("# spec quality\n")
    modules = find_local_modules(tmp_path)
    assert "spec_quality_score" in modules
