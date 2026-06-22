"""Tests for enhanced_verification_must_recognize_class_defined_ac_prefix module.

Verifies that the 'Class defined:' AC prefix handler correctly detects class
definitions in a workspace, fixing the silent-fail regression documented in
feature 34f15fb6 (and root-cause feature 5779ecf7 / d012b661).
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from bob3.enhanced_verification_must_recognize_class_defined_ac_prefix import (
    enhanced_verification_must_recognize_class_defined_ac_prefix,
)


def _workspace_with_class(class_name: str, extra_content: str = "") -> pathlib.Path:
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    src = tmpdir / "src"
    src.mkdir()
    code = extra_content + f"class {class_name}:\n    pass\n"
    (src / "module.py").write_text(code)
    return tmpdir


def test_enhanced_verification_must_recognize_class_defined_ac_prefix():
    """Primary AC guard: 'Class defined:' returns True when the class exists."""
    workspace = _workspace_with_class("MutationReport")
    criterion = "Class defined: bob3.verification.mutation_gate.MutationReport"

    assert enhanced_verification_must_recognize_class_defined_ac_prefix(criterion, workspace) is True

    empty_dir = pathlib.Path(tempfile.mkdtemp())
    assert enhanced_verification_must_recognize_class_defined_ac_prefix(criterion, empty_dir) is False


def test_returns_false_for_non_class_defined_criterion():
    """Non-matching prefix returns False without searching."""
    workspace = _workspace_with_class("Foo")
    assert enhanced_verification_must_recognize_class_defined_ac_prefix("File exists: foo.py", workspace) is False


def test_recognizes_dataclass_decorated_class():
    """@dataclass decorator above 'class Foo:' does not block recognition."""
    workspace = _workspace_with_class("DataModel", extra_content="@dataclass\n")
    criterion = "Class defined: some.module.DataModel"
    assert enhanced_verification_must_recognize_class_defined_ac_prefix(criterion, workspace) is True


def test_recognizes_class_with_inheritance():
    """'class Foo(Base):' form is recognized."""
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    src = tmpdir / "src"
    src.mkdir()
    (src / "m.py").write_text("class Report(BaseModel):\n    pass\n")
    criterion = "Class defined: pkg.Report"
    assert enhanced_verification_must_recognize_class_defined_ac_prefix(criterion, tmpdir) is True


def test_case_insensitive_prefix():
    """Prefix matching is case-insensitive per spec."""
    workspace = _workspace_with_class("MyClass")
    assert enhanced_verification_must_recognize_class_defined_ac_prefix("class defined: some.MyClass", workspace) is True
    assert enhanced_verification_must_recognize_class_defined_ac_prefix("CLASS DEFINED: some.MyClass", workspace) is True


def test_exact_name_match_only():
    """'Report' must NOT match 'MutationReport' — substring matches are rejected."""
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    src = tmpdir / "src"
    src.mkdir()
    (src / "m.py").write_text("class MutationReport:\n    pass\n")
    criterion = "Class defined: pkg.Report"
    assert enhanced_verification_must_recognize_class_defined_ac_prefix(criterion, tmpdir) is False
