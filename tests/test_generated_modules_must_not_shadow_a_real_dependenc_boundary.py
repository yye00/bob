"""Boundary tests for hippy.namespace_collision.check_namespace_collisions.

Empty, zero, or minimum input must return a well-defined result rather than
raising (boundary case).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hippy.namespace_collision import check_namespace_collisions


def test_empty_dependencies_returns_empty(tmp_path):
    """No declared dependencies -> nothing can collide -> empty list."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "hip").mkdir()
    (src / "hip" / "__init__.py").write_text("")
    result = check_namespace_collisions(src, dependencies=set())
    assert result == []


def test_empty_src_dir_returns_empty(tmp_path):
    """An empty (but existing) src dir returns an empty list, not an error."""
    src = tmp_path / "src"
    src.mkdir()
    result = check_namespace_collisions(src, dependencies={"hip", "numpy"})
    assert result == []


def test_nonexistent_src_dir_returns_empty(tmp_path):
    """A src dir that does not exist yet returns a well-defined empty list."""
    result = check_namespace_collisions(tmp_path / "absent", dependencies={"hip"})
    assert result == []


def test_result_is_list(tmp_path):
    """The return value is always a list, even in the trivial case."""
    src = tmp_path / "src"
    src.mkdir()
    result = check_namespace_collisions(src, dependencies={"numpy"})
    assert isinstance(result, list)
