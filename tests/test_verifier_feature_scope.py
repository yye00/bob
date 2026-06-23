"""Tests for bob3.verifier.scope_pytest_to_feature — feature-scoped pytest invocation.

AC: pytest: tests/test_verifier_feature_scope.py
    integration: bob3.verifier

These tests verify that scope_pytest_to_feature returns ONLY paths belonging
to the current feature (pytest: AC entries and the tests/<feature_id>/ subtree),
never the full tests/ tree or sibling feature subtrees.
"""

from __future__ import annotations

import pytest

from bob3.verifier import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)

FEATURE_ID = "306d8541-6387-48cd-9676-82eeb2fd8f3c"
OTHER_FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


# --- scope_pytest_to_feature ---

def test_scope_returns_pytest_ac_paths(tmp_path):
    """Returns paths extracted from pytest: ACs."""
    acs = [
        "pytest: tests/test_verifier_feature_scope.py",
        "File exists: src/bob3/verifier.py",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert "tests/test_verifier_feature_scope.py" in result


def test_scope_strips_node_id_suffix(tmp_path):
    """pytest: paths with ::ClassName::method are stripped to the file path."""
    acs = ["pytest: tests/test_foo.py::TestClass::test_method"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_foo.py"]


def test_scope_returns_feature_subtree_when_dir_exists(tmp_path):
    """Includes tests/<feature_id>/ when that directory exists on disk."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
    assert f"tests/{FEATURE_ID}" in result


def test_scope_excludes_feature_subtree_when_absent(tmp_path):
    """Does not include tests/<feature_id>/ when the directory does not exist."""
    result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
    assert result == []


def test_scope_never_includes_bare_tests(tmp_path):
    """Returned paths never include bare 'tests' or 'tests/'."""
    acs = ["pytest: tests/test_specific.py"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    for path in result:
        assert path not in ("tests", "tests/")


def test_scope_raises_on_sibling_uuid_path(tmp_path):
    """Raises SiblingTestCollectionError when pytest: AC references another feature's subtree."""
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_other.py"]
    with pytest.raises(SiblingTestCollectionError):
        scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)


def test_scope_deduplicates_paths(tmp_path):
    """Duplicate pytest: AC entries appear only once in the result."""
    acs = [
        "pytest: tests/test_foo.py",
        "pytest: tests/test_foo.py",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result.count("tests/test_foo.py") == 1


def test_scope_result_is_sorted(tmp_path):
    """Returned paths are in sorted order."""
    acs = [
        "pytest: tests/test_z.py",
        "pytest: tests/test_a.py",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == sorted(result)


def test_scope_ignores_non_pytest_acs(tmp_path):
    """ACs without a pytest: prefix do not produce test paths."""
    acs = [
        "Function defined: bob3.verifier.scope_pytest_to_feature",
        "File exists: src/bob3/verifier.py",
        "integration: bob3.verifier",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == []


# --- collect_feature_test_paths ---

def test_collect_extracts_pytest_ac_paths(tmp_path):
    """Returns the set of paths from pytest: ACs."""
    acs = ["pytest: tests/test_mine.py", "pytest: tests/test_other.py"]
    paths = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
    assert "tests/test_mine.py" in paths
    assert "tests/test_other.py" in paths


def test_collect_returns_set_type(tmp_path):
    """Return type is a set."""
    result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
    assert isinstance(result, set)


def test_collect_includes_feature_dir_when_exists(tmp_path):
    """Includes tests/<feature_id>/ path when directory exists."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    paths = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
    assert f"tests/{FEATURE_ID}" in paths


# --- build_scoped_pytest_argv ---

def test_build_argv_returns_list(tmp_path):
    """build_scoped_pytest_argv returns a list."""
    acs = ["pytest: tests/test_foo.py"]
    result = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
    assert isinstance(result, list)


def test_build_argv_includes_test_paths(tmp_path):
    """Argv includes test paths from pytest: ACs."""
    acs = ["pytest: tests/test_build.py"]
    result = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
    assert "tests/test_build.py" in result


def test_build_argv_raises_on_sibling(tmp_path):
    """Raises SiblingTestCollectionError when argv would collect sibling subtree."""
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_sibling.py"]
    with pytest.raises(SiblingTestCollectionError):
        build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)


# --- assert_no_sibling_collection ---

def test_assert_allows_own_feature_uuid(tmp_path):
    """Does not raise when argv contains the current feature's own subtree."""
    assert_no_sibling_collection(FEATURE_ID, [f"tests/{FEATURE_ID}"], tmp_path)


def test_assert_raises_on_other_uuid(tmp_path):
    """Raises when argv contains a different UUID subtree."""
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, [f"tests/{OTHER_FEATURE_ID}"], tmp_path)


def test_assert_raises_on_bare_tests(tmp_path):
    """Raises when argv contains bare 'tests'."""
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, ["tests"], tmp_path)


def test_assert_allows_non_uuid_test_paths(tmp_path):
    """Does not raise for regular test file paths not under a UUID subtree."""
    assert_no_sibling_collection(
        FEATURE_ID,
        ["tests/test_verifier_feature_scope.py"],
        tmp_path,
    )


def test_assert_ignores_option_flags(tmp_path):
    """Option flags like --rootdir are ignored, not treated as paths."""
    assert_no_sibling_collection(
        FEATURE_ID,
        [f"--rootdir=tests/{FEATURE_ID}", "tests/test_foo.py"],
        tmp_path,
    )
