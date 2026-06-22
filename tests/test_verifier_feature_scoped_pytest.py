"""Tests for bob3.verifier.scope_pytest_to_feature — scoped pytest invocation.

AC: pytest: tests/test_verifier_feature_scoped_pytest.py
    integration: bob3.verifier

Verifies that scope_pytest_to_feature returns ONLY paths belonging to the
current feature, never the full tests/ tree or sibling feature subtrees.
This prevents pytest-xdist --maxfail from tripping on accumulated prior-feature
failures before the current feature's own tests execute.
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

FEATURE_ID = "bd8d65ba-9ade-4375-ad5e-8d0ad9c33f1e"
OTHER_FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_scope_pytest_to_feature_extracts_pytest_ac_paths(tmp_path):
    """scope_pytest_to_feature returns paths from pytest: ACs."""
    acs = [
        "pytest: tests/test_verifier_feature_scoped_pytest.py",
        "Function defined: bob3.verifier.scope_pytest_to_feature",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert "tests/test_verifier_feature_scoped_pytest.py" in result


def test_scope_includes_feature_subtree_when_directory_exists(tmp_path):
    """scope_pytest_to_feature includes tests/<feature_id>/ when it exists."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
    assert f"tests/{FEATURE_ID}" in result


def test_scope_excludes_feature_subtree_when_absent(tmp_path):
    """scope_pytest_to_feature returns [] when no ACs and no subtree exist."""
    result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
    assert result == []


def test_scope_strips_nodeid_from_pytest_ac(tmp_path):
    """pytest: paths with ::Class::method are reduced to the file path only."""
    acs = ["pytest: tests/test_foo.py::TestSuite::test_case"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == ["tests/test_foo.py"]


def test_scope_ignores_non_pytest_acs(tmp_path):
    """Non-pytest: ACs are not included in the result."""
    acs = [
        "Function defined: bob3.verifier.scope_pytest_to_feature",
        "File exists: src/bob3/verifier/__init__.py",
        "integration: bob3.verifier",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == []


def test_scope_returns_sorted_paths(tmp_path):
    """scope_pytest_to_feature returns paths in sorted order."""
    acs = [
        "pytest: tests/test_z_last.py",
        "pytest: tests/test_a_first.py",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result == sorted(result)


def test_scope_deduplicates_paths(tmp_path):
    """scope_pytest_to_feature deduplicates identical pytest: paths."""
    acs = [
        "pytest: tests/test_dup.py",
        "pytest: tests/test_dup.py",
    ]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert result.count("tests/test_dup.py") == 1


def test_collect_feature_test_paths_returns_set(tmp_path):
    """collect_feature_test_paths returns a set of strings."""
    acs = ["pytest: tests/test_feature.py"]
    result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
    assert isinstance(result, set)
    assert "tests/test_feature.py" in result


def test_build_scoped_argv_excludes_bare_tests(tmp_path):
    """build_scoped_pytest_argv never returns argv containing bare 'tests/'."""
    acs = ["pytest: tests/test_single.py"]
    argv = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
    assert "tests" not in argv
    assert "tests/" not in argv


def test_build_scoped_argv_contains_ac_paths(tmp_path):
    """build_scoped_pytest_argv includes all pytest: AC paths."""
    acs = [
        "pytest: tests/test_alpha.py",
        "pytest: tests/test_beta.py",
    ]
    argv = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
    assert "tests/test_alpha.py" in argv
    assert "tests/test_beta.py" in argv


def test_assert_no_sibling_collection_passes_for_own_feature(tmp_path):
    """assert_no_sibling_collection does not raise for own feature's paths."""
    argv = [f"tests/{FEATURE_ID}/test_mine.py"]
    assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)


def test_assert_no_sibling_collection_raises_for_bare_tests(tmp_path):
    """assert_no_sibling_collection raises SiblingTestCollectionError for bare tests/."""
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, ["tests/"], tmp_path)


def test_assert_no_sibling_collection_raises_for_sibling_uuid(tmp_path):
    """assert_no_sibling_collection raises for another feature's UUID subtree."""
    with pytest.raises(SiblingTestCollectionError):
        assert_no_sibling_collection(FEATURE_ID, [f"tests/{OTHER_FEATURE_ID}"], tmp_path)


def test_scope_raises_on_sibling_uuid_in_pytest_ac(tmp_path):
    """scope_pytest_to_feature raises SiblingTestCollectionError for sibling UUID in AC."""
    acs = [f"pytest: tests/{OTHER_FEATURE_ID}/test_sibling.py"]
    with pytest.raises(SiblingTestCollectionError):
        scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)


def test_scope_combines_ac_paths_and_subtree(tmp_path):
    """scope_pytest_to_feature returns both pytest: paths and the feature subtree."""
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    acs = ["pytest: tests/test_explicit.py"]
    result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert "tests/test_explicit.py" in result
    assert f"tests/{FEATURE_ID}" in result


def test_scope_pytest_to_feature_is_importable_from_verifier():
    """scope_pytest_to_feature is importable from bob3.verifier (integration AC)."""
    from bob3.verifier import scope_pytest_to_feature as spf
    assert callable(spf)
