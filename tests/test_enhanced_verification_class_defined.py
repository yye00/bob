"""Tests for verify_class_defined — the public entry point in enhanced_verification.

AC: Function defined: bob3.enhanced_verification.verify_class_defined

This module tests that verify_class_defined:
- Delegates to the Class defined: branch in _check_criterion
- Returns True when the class exists in the workspace
- Returns False when the class is missing
- Handles dotted-path criteria (uses last component as class name)
- Handles @dataclass / decorated class forms
- Handles class Foo(Base): inheritance forms
- Integration: _check_criterion routes 'Class defined:' to check_class_defined_ac
"""

from __future__ import annotations

import pathlib
import pytest

from bob3.enhanced_verification import verify_class_defined


@pytest.fixture
def workspace_with_class(tmp_path):
    src = tmp_path / "src" / "bob3"
    src.mkdir(parents=True)
    (src / "mymod.py").write_text(
        "class MyReport:\n"
        "    pass\n"
    )
    return tmp_path


@pytest.fixture
def workspace_with_dataclass(tmp_path):
    src = tmp_path / "src" / "bob3" / "verification"
    src.mkdir(parents=True)
    (src / "mutation_gate.py").write_text(
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class MutationReport:\n"
        "    passed: int\n"
        "    total: int\n"
    )
    return tmp_path


@pytest.fixture
def empty_workspace(tmp_path):
    (tmp_path / "src").mkdir()
    return tmp_path


# ── Existence checks ─────────────────────────────────────────────────────────

def test_returns_true_when_class_exists(workspace_with_class):
    result = verify_class_defined("Class defined: bob3.mymod.MyReport", workspace_with_class)
    assert result is True


def test_returns_false_when_class_missing(empty_workspace):
    result = verify_class_defined("Class defined: bob3.mymod.Missing", empty_workspace)
    assert result is False


def test_returns_false_when_workspace_has_no_src(tmp_path):
    result = verify_class_defined("Class defined: pkg.Cls", tmp_path)
    assert result is False


# ── Dotted-path extraction ────────────────────────────────────────────────────

def test_uses_last_component_of_dotted_path(workspace_with_class):
    # 'bob3.deep.nested.path.MyReport' → class name is 'MyReport'
    result = verify_class_defined("Class defined: bob3.deep.nested.path.MyReport", workspace_with_class)
    assert result is True


def test_single_component_criterion(workspace_with_class):
    # 'Class defined: MyReport' (no dotted path)
    result = verify_class_defined("Class defined: MyReport", workspace_with_class)
    assert result is True


# ── Decorator / inheritance forms ─────────────────────────────────────────────

def test_dataclass_decorated_class(workspace_with_dataclass):
    """@dataclass above class must not block detection."""
    result = verify_class_defined(
        "Class defined: bob3.verification.mutation_gate.MutationReport",
        workspace_with_dataclass,
    )
    assert result is True


def test_class_with_base(tmp_path):
    """class Foo(Base): form should pass."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "model.py").write_text("class FooBase(object):\n    pass\n")
    result = verify_class_defined("Class defined: FooBase", tmp_path)
    assert result is True


# ── Return type is bool ───────────────────────────────────────────────────────

def test_return_type_true_is_bool(workspace_with_class):
    result = verify_class_defined("Class defined: MyReport", workspace_with_class)
    assert isinstance(result, bool)


def test_return_type_false_is_bool(empty_workspace):
    result = verify_class_defined("Class defined: Missing", empty_workspace)
    assert isinstance(result, bool)


# ── Non-class-defined criterion returns False ─────────────────────────────────

def test_non_class_defined_prefix_returns_false(workspace_with_class):
    """verify_class_defined is only for Class defined: criteria."""
    result = verify_class_defined("Function defined: bob3.mymod.MyReport", workspace_with_class)
    assert result is False


def test_empty_criterion_returns_false(workspace_with_class):
    result = verify_class_defined("", workspace_with_class)
    assert result is False


# ── Exact-name matching ───────────────────────────────────────────────────────

def test_does_not_match_substring_of_class_name(workspace_with_class):
    """'Report' must NOT match 'MyReport'."""
    result = verify_class_defined("Class defined: bob3.mymod.Report", workspace_with_class)
    assert result is False


# ── Real workspace regression guard ──────────────────────────────────────────

def test_mutation_report_exists_in_real_workspace():
    """MutationReport must be detectable in the actual bob62 workspace."""
    workspace = pathlib.Path(__file__).parent.parent
    result = verify_class_defined(
        "Class defined: bob3.verification.mutation_gate.MutationReport",
        workspace,
    )
    assert result is True
