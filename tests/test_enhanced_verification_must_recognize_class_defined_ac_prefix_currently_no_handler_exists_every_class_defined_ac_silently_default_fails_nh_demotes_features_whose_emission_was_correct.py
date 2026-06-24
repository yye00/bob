"""Tests for the enhanced_verification 'Class defined:' AC prefix handler.

Feature d012b661: verifies that enhanced_verification correctly recognizes
'Class defined:' acceptance criteria. Previously no handler existed, causing
every Class-defined AC to silently default-fail and NH-demote features whose
emission was correct.

Root cause (observed 2026-05-29): feature 5779ecf7 (Mutation-testing quality
gate / mutmut) was NH-demoted at refinement_attempts=5 despite emitting a
correct MutationReport @dataclass. The _check_criterion function had handlers
for 'File exists:', 'Function defined:', 'pytest:', 'integration:' etc. but
NO handler for 'Class defined:'. The AC criterion fell through every branch
and returned the default-False.
"""

from __future__ import annotations

import pathlib
import tempfile

from bob.enhanced_verification_must_recognize_class_defined_ac_prefix_currently_no_handler_exists_every_class_defined_ac_silently_default_fails_nh_demotes_features_whose_emission_was_correct import (
    enhanced_verification_must_recognize_class_defined_ac_prefix_currently_no_handler_exists_every_class_defined_ac_silently_default_fails_nh_demotes_features_whose_emission_was_correct as check_class_ac,
)


def _make_workspace_with_class(class_name: str, decorator: str = "") -> pathlib.Path:
    """Create a temp workspace with a Python file defining *class_name*."""
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    src_dir = tmpdir / "src"
    src_dir.mkdir()
    code = ""
    if decorator:
        code += f"{decorator}\n"
    code += f"class {class_name}:\n    pass\n"
    (src_dir / "module.py").write_text(code)
    return tmpdir


def test_enhanced_verification_must_recognize_class_defined_ac_prefix_currently_no_handler_exists_every_class_defined_ac_silently_default_fails_nh_demotes_features_whose_emission_was_correct():
    """AC: 'Class defined:' criterion passes when the class exists in the workspace.

    This is the primary guard against the silent-fail regression described in
    the feature description. The function must return True when the named class
    is present and False when absent.
    """
    workspace = _make_workspace_with_class("MutationReport")

    # Must recognize the criterion and find the class
    criterion = "Class defined: bob.verification.mutation_gate.MutationReport"
    result = check_class_ac(criterion, workspace)

    assert result is True, (
        "enhanced_verification must return True for 'Class defined:' AC when "
        "the class exists in the workspace. Previously this silent-failed, "
        "causing NH-demotion of correct feature implementations."
    )

    # Must return False when the class is absent
    empty_dir = pathlib.Path(tempfile.mkdtemp())
    result_absent = check_class_ac(criterion, empty_dir)
    assert result_absent is False, (
        "enhanced_verification must return False when the class is not found."
    )


def test_class_defined_passes_for_dataclass():
    """Decorator-prefixed class forms (@dataclass) are recognized."""
    workspace = _make_workspace_with_class("MutationReport", decorator="@dataclass")
    criterion = "Class defined: bob.verification.mutation_gate.MutationReport"
    assert check_class_ac(criterion, workspace) is True


def test_class_defined_passes_for_inheritance():
    """Class with inheritance 'class Foo(Base):' is recognized."""
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    src = tmpdir / "src"
    src.mkdir()
    (src / "module.py").write_text("class MutationReport(BaseModel):\n    pass\n")
    criterion = "Class defined: bob.verification.mutation_gate.MutationReport"
    assert check_class_ac(criterion, workspace=tmpdir) is True


def test_class_defined_fails_for_missing_class():
    """Returns False when the class is absent from the workspace."""
    empty_dir = pathlib.Path(tempfile.mkdtemp())
    criterion = "Class defined: bob.verification.mutation_gate.MutationReport"
    assert check_class_ac(criterion, empty_dir) is False


def test_class_defined_case_insensitive_prefix():
    """The 'Class defined:' prefix check is case-insensitive."""
    workspace = _make_workspace_with_class("MyClass")
    criterion = "class defined: mymodule.MyClass"
    assert check_class_ac(criterion, workspace) is True


def test_non_class_defined_criterion_returns_false():
    """A criterion that does not start with 'Class defined:' returns False."""
    workspace = _make_workspace_with_class("MyClass")
    criterion = "Function defined: mymodule.some_function"
    assert check_class_ac(criterion, workspace) is False


def test_class_defined_exact_name_match():
    """Exact class name matching: 'Report' must NOT match 'MutationReport'."""
    workspace = _make_workspace_with_class("MutationReport")
    criterion = "Class defined: some.module.Report"
    assert check_class_ac(criterion, workspace) is False


def test_verify_class_defined_public_api():
    """The public verify_class_defined API in enhanced_verification also works."""
    from bob.enhanced_verification import verify_class_defined

    workspace = _make_workspace_with_class("MutationReport")
    criterion = "Class defined: bob.verification.mutation_gate.MutationReport"
    assert verify_class_defined(criterion, workspace) is True
