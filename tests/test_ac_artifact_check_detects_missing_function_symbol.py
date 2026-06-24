"""AC artifact-existence verifier — detects missing function symbol."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from bob.verification.ac_artifact_check import (
    check_function_defined_ac,
    verify_ac_artifacts,
    ArtifactMiss,
)


def test_missing_module_returns_false(tmp_path):
    """check_function_defined_ac returns False when the module does not exist."""
    result = check_function_defined_ac(
        "bob.nonexistent_module_xyz.some_function", workspace=tmp_path
    )
    assert result is False


def test_missing_symbol_in_existing_module_returns_false(tmp_path):
    """check_function_defined_ac returns False when the symbol is not in the module."""
    # os module exists but has no 'nonexistent_symbol_abc'
    result = check_function_defined_ac("os.nonexistent_symbol_abc", workspace=tmp_path)
    assert result is False


def test_existing_symbol_returns_true(tmp_path):
    """check_function_defined_ac returns True when module and symbol both exist."""
    result = check_function_defined_ac("os.path.join", workspace=tmp_path)
    assert result is True


def test_verify_ac_artifacts_flags_missing_function(tmp_path):
    """verify_ac_artifacts returns ArtifactMiss with kind=function_defined for missing symbols."""
    acs = ["Function defined: bob.nonexistent_xyz.some_func (returns str)"]
    misses = verify_ac_artifacts(acs, workspace=tmp_path)
    assert len(misses) == 1
    assert misses[0].kind == "function_defined"
    assert "ARTIFACT_MISSING" in misses[0].reason


def test_no_dot_in_module_symbol_returns_false(tmp_path):
    """check_function_defined_ac returns False when module_symbol has no dot separator."""
    result = check_function_defined_ac("noseparator", workspace=tmp_path)
    assert result is False
