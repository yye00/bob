"""Error-path tests for hippy.namespace_collision.check_namespace_collisions.

Invalid input raises ValueError and the function does not silently succeed
(error path).
"""
from __future__ import annotations

import pytest

from hippy.namespace_collision import check_namespace_collisions


def test_none_src_dir_raises():
    """A None src_dir is invalid input -> ValueError, not a silent empty list."""
    with pytest.raises(ValueError):
        check_namespace_collisions(None, dependencies={"hip"})


def test_none_dependencies_raises(tmp_path):
    """A None dependencies set is invalid input -> ValueError."""
    src = tmp_path / "src"
    src.mkdir()
    with pytest.raises(ValueError):
        check_namespace_collisions(src, dependencies=None)


def test_non_iterable_dependencies_raises(tmp_path):
    """A non-iterable dependencies value is invalid -> ValueError."""
    src = tmp_path / "src"
    src.mkdir()
    with pytest.raises(ValueError):
        check_namespace_collisions(src, dependencies=123)
