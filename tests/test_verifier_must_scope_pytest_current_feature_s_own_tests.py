"""Tests for verifier_must_scope_pytest_current_feature_s_own_tests.

Verifies that the canonical function scopes pytest to ONLY the current
feature's own test paths and never to the full tests/ tree or sibling
feature subtrees.
"""

from __future__ import annotations

import pytest

from bob3.verifier_must_scope_pytest_current_feature_s_own_tests import (
    SiblingTestCollectionError,
    verifier_must_scope_pytest_current_feature_s_own_tests,
)

FEATURE_ID = "cf68ad25-7a8f-485e-bcf5-d9344da164de"
OTHER_FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_verifier_must_scope_pytest_current_feature_s_own_tests(tmp_path):
    """Function returns only the feature's own pytest: AC paths."""
    acs = [
        "pytest: tests/test_my_feature.py::test_something",
        "File exists: src/bob3/my_module.py",
    ]
    result = verifier_must_scope_pytest_current_feature_s_own_tests(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_my_feature.py"], result


def test_returns_feature_subtree_when_directory_exists(tmp_path):
    """Function includes tests/<feature_id>/ when that directory exists."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    acs = []
    result = verifier_must_scope_pytest_current_feature_s_own_tests(FEATURE_ID, acs, tmp_path)
    assert result == [f"tests/{FEATURE_ID}"], result


def test_returns_empty_list_when_no_paths(tmp_path):
    """Function returns empty list when no pytest ACs and no feature subtree."""
    acs = ["File exists: src/bob3/foo.py"]
    result = verifier_must_scope_pytest_current_feature_s_own_tests(FEATURE_ID, acs, tmp_path)
    assert result == []


def test_does_not_include_bare_tests_directory(tmp_path):
    """Function must never include bare 'tests/' which collects all features."""
    acs = ["pytest: tests/test_my_feature.py"]
    result = verifier_must_scope_pytest_current_feature_s_own_tests(FEATURE_ID, acs, tmp_path)
    assert "tests" not in result
    assert "tests/" not in result
    for path in result:
        assert path != "tests"
        assert path != "tests/"


def test_raises_on_sibling_feature_subtree_in_result(tmp_path):
    """Function raises SiblingTestCollectionError if it would collect a sibling subtree."""
    sibling_dir = tmp_path / "tests" / OTHER_FEATURE_ID
    sibling_dir.mkdir(parents=True)
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_other.py"]
    with pytest.raises(SiblingTestCollectionError):
        verifier_must_scope_pytest_current_feature_s_own_tests(FEATURE_ID, acs, tmp_path)


def test_combines_pytest_ac_paths_and_feature_subtree(tmp_path):
    """Function merges pytest: AC paths and the feature subtree directory."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    acs = [
        "pytest: tests/test_shared_helper.py::test_helper",
        "Function defined: bob3.my_mod.my_fn",
    ]
    result = verifier_must_scope_pytest_current_feature_s_own_tests(FEATURE_ID, acs, tmp_path)
    assert f"tests/{FEATURE_ID}" in result
    assert "tests/test_shared_helper.py" in result
