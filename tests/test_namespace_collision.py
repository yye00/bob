"""Tests for hippy.namespace_collision.check_namespace_collisions (46744620).

A generated ``src/<dep>`` package/module that matches an imported third-party
distribution SHADOWS the real package so ``from <dep> import ...`` breaks
workspace-wide. This module detects that collision so verification (and the
root conftest) can fail loudly instead of silently poisoning the build.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hippy.namespace_collision import check_namespace_collisions


def _make_src(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    return src


def test_detects_shadowing_package(tmp_path):
    """A src/hip package that shadows an imported 'hip' dependency is a collision."""
    src = _make_src(tmp_path)
    (src / "hip").mkdir()
    (src / "hip" / "__init__.py").write_text("# shadow")
    result = check_namespace_collisions(src, dependencies={"hip", "hiprtc"})
    assert "hip" in result


def test_detects_shadowing_module_file(tmp_path):
    """A src/numpy.py module that shadows the numpy dependency is a collision."""
    src = _make_src(tmp_path)
    (src / "numpy.py").write_text("# shadow")
    result = check_namespace_collisions(src, dependencies={"numpy"})
    assert "numpy" in result


def test_no_collision_for_project_namespace(tmp_path):
    """The project's own namespace package (not a dependency) is allowed."""
    src = _make_src(tmp_path)
    (src / "hippy").mkdir()
    (src / "hippy" / "__init__.py").write_text("# own")
    result = check_namespace_collisions(src, dependencies={"hip", "numpy", "scipy"})
    assert result == []


def test_multiple_collisions_all_reported(tmp_path):
    """Every shadowing name is reported, sorted."""
    src = _make_src(tmp_path)
    (src / "hip").mkdir()
    (src / "hip" / "__init__.py").write_text("")
    (src / "scipy.py").write_text("")
    (src / "hippy").mkdir()
    (src / "hippy" / "__init__.py").write_text("")
    result = check_namespace_collisions(
        src, dependencies={"hip", "scipy", "numpy"}
    )
    assert result == ["hip", "scipy"]


def test_non_py_file_is_not_a_collision(tmp_path):
    """A non-package data file matching a dep name is not an import collision."""
    src = _make_src(tmp_path)
    (src / "numpy.txt").write_text("data")
    result = check_namespace_collisions(src, dependencies={"numpy"})
    assert result == []


def test_directory_without_init_still_flagged(tmp_path):
    """A namespace-style dir matching a dep name still shadows on import."""
    src = _make_src(tmp_path)
    (src / "hip").mkdir()  # no __init__.py -> namespace package still shadows
    result = check_namespace_collisions(src, dependencies={"hip"})
    assert "hip" in result


def test_accepts_string_path(tmp_path):
    """src_dir may be passed as a string, not only a Path."""
    src = _make_src(tmp_path)
    (src / "hip").mkdir()
    (src / "hip" / "__init__.py").write_text("")
    result = check_namespace_collisions(str(src), dependencies={"hip"})
    assert "hip" in result


def test_missing_src_dir_returns_empty(tmp_path):
    """A src dir that does not exist yields no collisions (well-defined)."""
    result = check_namespace_collisions(
        tmp_path / "nope", dependencies={"hip"}
    )
    assert result == []
