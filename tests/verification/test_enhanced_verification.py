"""Tests for bob.verification.enhanced_verification.criterion_checker.

Verifies that 'Class defined:' AC prefix is recognized and routed correctly
through the criterion_checker exposed in the verification sub-package.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from bob.verification.enhanced_verification import criterion_checker


def _empty_workspace() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


def _workspace_with_class(class_name: str, *, decorated: bool = False) -> pathlib.Path:
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    src = tmpdir / "src"
    src.mkdir()
    lines = []
    if decorated:
        lines.append("from dataclasses import dataclass\n")
        lines.append("@dataclass\n")
    lines.append(f"class {class_name}:\n    pass\n")
    (src / "module.py").write_text("".join(lines))
    return tmpdir


class TestCriterionCheckerClassDefined:
    def test_class_defined_recognized(self):
        """'Class defined:' prefix is recognized and returns True when class exists."""
        workspace = _workspace_with_class("MutationReport")
        result = criterion_checker("Class defined: bob.verification.mutation_gate.MutationReport", workspace)
        assert result is True

    def test_class_defined_returns_false_when_absent(self):
        """'Class defined:' returns False when the named class is absent."""
        result = criterion_checker("Class defined: pkg.mod.NonExistentClass", _empty_workspace())
        assert result is False

    def test_class_defined_case_insensitive_prefix(self):
        """'class defined:' (lower-case) is also accepted."""
        workspace = _workspace_with_class("Foo")
        result = criterion_checker("class defined: pkg.Foo", workspace)
        assert isinstance(result, bool)

    def test_class_defined_dataclass_form(self):
        """@dataclass-decorated class is detected via class keyword."""
        workspace = _workspace_with_class("MyDataclass", decorated=True)
        result = criterion_checker("Class defined: pkg.MyDataclass", workspace)
        assert result is True

    def test_file_exists_still_works(self):
        """'File exists:' criterion still resolves correctly (regression guard)."""
        tmpdir = pathlib.Path(tempfile.mkdtemp())
        (tmpdir / "myfile.py").write_text("# ok\n")
        result = criterion_checker("File exists: myfile.py", tmpdir)
        assert result is True

    def test_non_string_raises_value_error(self):
        """Non-string criterion raises ValueError."""
        with pytest.raises(ValueError, match="criterion must be a str"):
            criterion_checker(None, _empty_workspace())  # type: ignore[arg-type]

    def test_empty_criterion_returns_false(self):
        """Empty criterion string returns False without raising."""
        result = criterion_checker("", _empty_workspace())
        assert result is False

    def test_returns_bool_type(self):
        """criterion_checker always returns a bool."""
        workspace = _workspace_with_class("X")
        result = criterion_checker("Class defined: pkg.X", workspace)
        assert isinstance(result, bool)

    def test_class_with_base_class(self):
        """Class with a base class ('class Foo(Base):') is matched."""
        tmpdir = pathlib.Path(tempfile.mkdtemp())
        (tmpdir / "mod.py").write_text("class FooChild(Base):\n    pass\n")
        result = criterion_checker("Class defined: mod.FooChild", tmpdir)
        assert result is True

    def test_partial_class_name_does_not_match(self):
        """'Report' does not match 'MutationReport' (exact name required)."""
        workspace = _workspace_with_class("MutationReport")
        result = criterion_checker("Class defined: pkg.Report", workspace)
        assert result is False
