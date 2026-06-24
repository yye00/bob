"""Tests verifying that bob.verifier.scope_pytest_to_feature scopes pytest
to only the current feature's own test paths.

Acceptance criteria: pytest: tests/verifier_scope_pytest/test_verifier_scopes_to_feature_tests.py
"""

from __future__ import annotations

import pytest

from bob.verifier import (
    SiblingTestCollectionError,
    scope_pytest_to_feature,
    collect_feature_test_paths,
    build_scoped_pytest_argv,
    assert_no_sibling_collection,
)

FEATURE_ID = "22ea12cd-52a7-4f0b-8d70-4d63bdae9514"
OTHER_FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_scope_pytest_to_feature_returns_pytest_ac_paths(tmp_path):
    """scope_pytest_to_feature extracts paths from pytest: ACs."""
    acs = [
        "pytest: tests/test_my_feature.py",
        "File exists: src/bob/some_module.py",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_my_feature.py"]


def test_scope_pytest_to_feature_strips_node_id(tmp_path):
    """scope_pytest_to_feature strips ::ClassName::test_name from pytest: AC paths."""
    acs = ["pytest: tests/test_foo.py::TestClass::test_method"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_foo.py"]


def test_scope_pytest_to_feature_includes_feature_subtree(tmp_path):
    """scope_pytest_to_feature includes tests/<feature_id>/ when the directory exists."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    acs = []
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == [f"tests/{FEATURE_ID}"]


def test_scope_pytest_to_feature_combines_sources(tmp_path):
    """scope_pytest_to_feature merges pytest: ACs and the feature subtree."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    acs = [
        "pytest: tests/test_shared.py",
        "Function defined: bob.mod.fn",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert f"tests/{FEATURE_ID}" in result
    assert "tests/test_shared.py" in result


def test_scope_pytest_to_feature_returns_empty_when_no_paths(tmp_path):
    """scope_pytest_to_feature returns [] when no pytest: ACs and no feature dir."""
    acs = ["Function defined: bob.foo.bar"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == []


def test_scope_pytest_to_feature_never_returns_bare_tests_dir(tmp_path):
    """scope_pytest_to_feature must never return bare tests/ or tests."""
    acs = ["pytest: tests/test_something.py"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    for path in result:
        assert path.rstrip("/") != "tests"


def test_scope_pytest_to_feature_raises_on_sibling_subtree(tmp_path):
    """scope_pytest_to_feature raises SiblingTestCollectionError for sibling UUID paths."""
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_other.py"]
    with pytest.raises(SiblingTestCollectionError):
        scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)


def test_collect_feature_test_paths_returns_set(tmp_path):
    """collect_feature_test_paths returns a set of paths."""
    acs = ["pytest: tests/test_a.py", "pytest: tests/test_b.py"]
    result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
    assert isinstance(result, set)
    assert "tests/test_a.py" in result
    assert "tests/test_b.py" in result


def test_build_scoped_pytest_argv_includes_rootdir(tmp_path):
    """build_scoped_pytest_argv includes --rootdir when feature dir exists."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    acs = []
    argv = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
    assert any("--rootdir" in arg for arg in argv)


def test_assert_no_sibling_collection_allows_own_feature(tmp_path):
    """assert_no_sibling_collection does not raise for the current feature's paths."""
    argv = [f"tests/{FEATURE_ID}/test_mine.py"]
    assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)  # must not raise


def test_assert_no_sibling_collection_raises_on_bare_tests(tmp_path):
    """assert_no_sibling_collection raises for bare tests/ path."""
    argv = ["tests"]
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)


def test_assert_no_sibling_collection_raises_on_other_uuid(tmp_path):
    """assert_no_sibling_collection raises when another feature UUID is in argv."""
    argv = [f"tests/{OTHER_FEATURE_ID}"]
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)
