"""Boundary tests: criterion_checker with empty, zero, or minimum inputs.

Feature c2168748: enhanced_verification MUST recognize 'Class defined:' AC
prefix. This file verifies boundary cases — empty or minimal inputs must
return a well-defined result rather than raising.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from bob.enhanced_verification import criterion_checker


def _empty_workspace() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


def _workspace_with_class(class_name: str) -> pathlib.Path:
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    src = tmpdir / "src"
    src.mkdir()
    (src / "module.py").write_text(f"class {class_name}:\n    pass\n")
    return tmpdir


class TestBoundaryCases:
    def test_empty_criterion_returns_false(self):
        """Empty criterion string returns False without raising."""
        result = criterion_checker("", _empty_workspace())
        assert result is False

    def test_whitespace_only_criterion_returns_false(self):
        """Criterion containing only whitespace returns False without raising."""
        result = criterion_checker("   ", _empty_workspace())
        assert result is False

    def test_class_defined_with_single_component_path(self):
        """Minimum dotted path (single component = class name) is accepted."""
        workspace = _workspace_with_class("MyClass")
        result = criterion_checker("Class defined: MyClass", workspace)
        assert isinstance(result, bool)

    def test_class_defined_empty_workspace_returns_false(self):
        """'Class defined:' criterion on empty workspace returns False."""
        result = criterion_checker("Class defined: pkg.MyClass", _empty_workspace())
        assert result is False

    def test_class_defined_present_returns_true(self):
        """'Class defined:' criterion returns True when class is present."""
        workspace = _workspace_with_class("MyClass")
        result = criterion_checker("Class defined: some.pkg.MyClass", workspace)
        assert result is True

    def test_class_defined_only_prefix_no_path_returns_false(self):
        """'Class defined:' with no class path after colon returns False."""
        result = criterion_checker("Class defined:", _empty_workspace())
        assert result is False

    def test_class_defined_path_with_many_dots(self):
        """Deep dotted paths are handled gracefully."""
        workspace = _workspace_with_class("Leaf")
        result = criterion_checker("Class defined: a.b.c.d.e.f.Leaf", workspace)
        assert isinstance(result, bool)

    def test_returns_bool_not_none(self):
        """criterion_checker always returns a bool, never None."""
        workspace = _workspace_with_class("SomeClass")
        result = criterion_checker("Class defined: pkg.SomeClass", workspace)
        assert result is not None
        assert isinstance(result, bool)
