"""Tests for the verifier pytest-scoping entry point.

Verifies that the canonical function scopes pytest to ONLY the current
feature's own test paths and never to the full tests/ tree or sibling
feature subtrees.
"""

from __future__ import annotations

import pytest

from bob.verifier_must_scope_pytest_current_feature_s_own_tests_subtree_cumulative_prior_feature_test_failures_cause_pytest_xdist_stop_after_20_fail_every_subsequent_feature_s_verification import (
    SiblingTestCollectionError,
    verifier_must_scope_pytest_current_feature_s_own_tests_subtree_cumulative_prior_feature_test_failures_cause_pytest_xdist_stop_after_20_fail_every_subsequent_feature_s_verification as scope_fn,
)

FEATURE_ID = "cf68ad25-7a8f-485e-bcf5-d9344da164de"
OTHER_FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_verifier_must_scope_pytest_current_feature_s_own_tests_subtree_cumulative_prior_feature_test_failures_cause_pytest_xdist_stop_after_20_fail_every_subsequent_feature_s_verification(
    tmp_path,
):
    """Function returns only the feature's own pytest: AC paths."""
    acs = [
        f"pytest: tests/test_my_feature.py::test_something",
        "File exists: src/bob/my_module.py",
    ]
    result = scope_fn(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_my_feature.py"], result


def test_returns_feature_subtree_when_directory_exists(tmp_path):
    """Function includes tests/<feature_id>/ when that directory exists."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    acs = []
    result = scope_fn(FEATURE_ID, acs, tmp_path)
    assert result == [f"tests/{FEATURE_ID}"], result


def test_returns_empty_list_when_no_paths(tmp_path):
    """Function returns empty list when no pytest ACs and no feature subtree."""
    acs = ["File exists: src/bob/foo.py"]
    result = scope_fn(FEATURE_ID, acs, tmp_path)
    assert result == []


def test_does_not_include_bare_tests_directory(tmp_path):
    """Function must never include bare 'tests/' which collects all features."""
    acs = ["pytest: tests/test_my_feature.py"]
    result = scope_fn(FEATURE_ID, acs, tmp_path)
    assert "tests" not in result
    assert "tests/" not in result
    for path in result:
        assert path != "tests"
        assert path != "tests/"


def test_raises_on_sibling_feature_subtree_in_result(tmp_path):
    """Function raises SiblingTestCollectionError if it would collect a sibling subtree."""
    sibling_dir = tmp_path / "tests" / OTHER_FEATURE_ID
    sibling_dir.mkdir(parents=True)
    # Force a sibling path into ACs — the guard should catch this.
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_other.py"]
    with pytest.raises(SiblingTestCollectionError):
        scope_fn(FEATURE_ID, acs, tmp_path)


def test_combines_pytest_ac_paths_and_feature_subtree(tmp_path):
    """Function merges pytest: AC paths and the feature subtree directory."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    acs = [
        f"pytest: tests/test_shared_helper.py::test_helper",
        "Function defined: bob.my_mod.my_fn",
    ]
    result = scope_fn(FEATURE_ID, acs, tmp_path)
    assert f"tests/{FEATURE_ID}" in result
    assert "tests/test_shared_helper.py" in result
    assert len(result) == 2


def test_result_is_sorted(tmp_path):
    """Function returns paths in sorted order."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    acs = [
        "pytest: tests/z_last.py",
        "pytest: tests/a_first.py",
    ]
    result = scope_fn(FEATURE_ID, acs, tmp_path)
    assert result == sorted(result)


def test_strips_node_id_from_pytest_ac(tmp_path):
    """Function strips ::ClassName::test_method from pytest: AC paths."""
    acs = ["pytest: tests/test_feature.py::TestClass::test_method"]
    result = scope_fn(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_feature.py"]
    assert "::" not in result[0]
