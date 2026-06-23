"""Boundary tests for bob3.verifier.scope_pytest_to_feature.

AC: pytest: tests/test_verifier_must_scope_pytest_to_the_current_feature__boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

from bob3.verifier import scope_pytest_to_feature, collect_feature_test_paths

FEATURE_ID = "22ea12cd-52a7-4f0b-8d70-4d63bdae9514"


def test_empty_acs_returns_empty_list(tmp_path):
    """Empty AC list returns [] without raising."""
    result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
    assert result == []


def test_empty_acs_empty_string_feature_id_returns_empty(tmp_path):
    """Empty string feature_id with empty ACs returns [] without raising."""
    result = scope_pytest_to_feature("", [], tmp_path)
    assert result == []


def test_no_pytest_acs_returns_empty_list(tmp_path):
    """ACs without any pytest: prefix returns [] without raising."""
    acs = [
        "Function defined: bob3.foo.bar",
        "File exists: src/bob3/module.py",
        "integration: bob3.verifier",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == []


def test_single_pytest_ac_minimum_input(tmp_path):
    """Single pytest: AC returns exactly one path."""
    acs = ["pytest: tests/test_one.py"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_one.py"]


def test_nonexistent_workspace_still_returns_ac_paths():
    """Workspace that doesn't exist as a real dir still returns pytest: AC paths."""
    import tempfile, os
    # Use a path that doesn't exist on disk
    workspace = "/tmp/nonexistent_bob3_workspace_for_boundary_test_xyzzy"
    acs = ["pytest: tests/test_boundary.py"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, workspace)
    assert result == ["tests/test_boundary.py"]


def test_collect_feature_test_paths_empty_inputs(tmp_path):
    """collect_feature_test_paths returns empty set for empty inputs."""
    result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
    assert isinstance(result, set)
    assert len(result) == 0


def test_pytest_ac_with_only_whitespace_path_ignored(tmp_path):
    """pytest: AC with empty path after stripping is silently skipped."""
    acs = ["pytest:   "]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == []


def test_feature_id_with_no_tests_subtree_returns_ac_paths(tmp_path):
    """When feature subtree doesn't exist, only AC paths are returned."""
    acs = ["pytest: tests/test_my_feature.py"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_my_feature.py"]
    # Feature subtree should not appear since directory doesn't exist
    assert f"tests/{FEATURE_ID}" not in result
