"""Tests for the 'Class defined:' acceptance-criterion handler.

Feature fad860a5: enhanced_verification MUST recognize the 'Class defined:'
AC prefix. Before this handler existed, any 'Class defined:' criterion fell
through every pattern branch and returned the default-False from the bottom
of the criterion-checker — silently NH-demoting features whose class
emission was actually correct (e.g. 5779ecf7's MutationReport @dataclass).

These tests assert the handler is symmetric to the 'Function defined:'
handler: it extracts the class name (last dotted component) and confirms a
matching 'class Name:' / 'class Name(Base):' definition exists in the
workspace source tree — including decorator-prefixed forms.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from bob.enhanced_verification import _search_for_function, criterion_checker
from bob.verification.class_defined_ac_check import (
    check_class_defined_ac,
    extract_class_name_from_criterion,
)


def _empty_workspace() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


def _workspace_with_source(rel_path: str, body: str) -> pathlib.Path:
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    target = tmpdir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body)
    return tmpdir


class TestExtractClassName:
    def test_extracts_last_dotted_component(self):
        assert (
            extract_class_name_from_criterion(
                "Class defined: bob.verification.mutation_gate.MutationReport"
            )
            == "MutationReport"
        )

    def test_single_component_path(self):
        assert extract_class_name_from_criterion("Class defined: MyClass") == "MyClass"

    def test_case_insensitive_prefix(self):
        assert extract_class_name_from_criterion("class defined: pkg.Foo") == "Foo"

    def test_non_class_criterion_returns_none(self):
        assert extract_class_name_from_criterion("File exists: src/foo.py") is None

    def test_function_defined_criterion_returns_none(self):
        assert (
            extract_class_name_from_criterion("Function defined: bob.mod.func") is None
        )


class TestCheckClassDefinedAc:
    def test_plain_class_matches(self):
        ws = _workspace_with_source("src/m.py", "class Foo:\n    pass\n")
        assert check_class_defined_ac("Foo", ws) is True

    def test_class_with_base_matches(self):
        ws = _workspace_with_source("src/m.py", "class Foo(Base):\n    pass\n")
        assert check_class_defined_ac("Foo", ws) is True

    def test_decorated_dataclass_matches(self):
        ws = _workspace_with_source(
            "src/m.py",
            "from dataclasses import dataclass\n\n@dataclass\nclass MutationReport:\n    score: float\n",
        )
        assert check_class_defined_ac("MutationReport", ws) is True

    def test_absent_class_returns_false(self):
        ws = _workspace_with_source("src/m.py", "class Other:\n    pass\n")
        assert check_class_defined_ac("Missing", ws) is False

    def test_exact_match_only_no_substring(self):
        """'Report' must NOT match 'MutationReport' — substrings are not matches."""
        ws = _workspace_with_source("src/m.py", "class MutationReport:\n    pass\n")
        assert check_class_defined_ac("Report", ws) is False

    def test_empty_workspace_returns_false(self):
        assert check_class_defined_ac("Anything", _empty_workspace()) is False


class TestCriterionCheckerClassDefinedBranch:
    def test_class_defined_ac_present_returns_true(self):
        ws = _workspace_with_source(
            "src/bob/verification/mutation_gate.py",
            "from dataclasses import dataclass\n\n@dataclass\nclass MutationReport:\n    score: float\n",
        )
        result = criterion_checker(
            "Class defined: bob.verification.mutation_gate.MutationReport", ws
        )
        assert result is True

    def test_class_defined_ac_absent_returns_false(self):
        ws = _empty_workspace()
        result = criterion_checker(
            "Class defined: bob.verification.mutation_gate.MutationReport", ws
        )
        assert result is False

    def test_class_defined_does_not_default_fail_when_correct(self):
        """Regression for the NH-demotion bug: a correct class emission must
        NOT fall through to the default-False at the bottom of the checker."""
        ws = _workspace_with_source("src/pkg/mod.py", "class Widget:\n    pass\n")
        assert criterion_checker("Class defined: pkg.mod.Widget", ws) is True

    def test_class_defined_branch_independent_from_function_defined(self):
        """A 'Class defined:' AC is satisfied by a class, not a function of
        the same name — and vice versa is not required here, but the class
        path must route through the class check."""
        ws = _workspace_with_source("src/mod.py", "class Alpha:\n    pass\n")
        assert criterion_checker("Class defined: mod.Alpha", ws) is True


class TestSearchForFunctionMatchesClasses:
    """The description notes _search_for_function already matches
    'class Name:' definitions; confirm that underlying capability."""

    def test_search_for_function_finds_class_definition(self):
        ws = _workspace_with_source("src/m.py", "class Beta:\n    pass\n")
        assert _search_for_function(ws, "Beta", True, False) is True
