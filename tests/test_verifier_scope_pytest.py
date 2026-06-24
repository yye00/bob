"""Integration tests for bob.verifier — scope_pytest_to_feature.

AC: pytest: tests/test_verifier_scope_pytest.py
    integration: bob.verifier

Verifies that the verifier's tests_pass step scopes pytest to ONLY the
current feature's own test paths. This closes the bug where cumulative
prior-feature broken tests triggered pytest-xdist --maxfail to abort
subsequent features' verification before their own tests ran.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.verifier import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)

FEATURE_ID = "2f644b9a-1d2e-415d-81eb-133dac139874"
SIBLING_ID = "fbd68fee-0000-0000-0000-000000000000"


class TestScopePytestToFeature:
    """Core behaviour of scope_pytest_to_feature."""

    def test_returns_only_pytest_ac_paths(self, tmp_path):
        """Only pytest: AC paths are returned (no full tests/ tree)."""
        acs = [
            "pytest: tests/test_verifier_scope_pytest.py",
            "File exists: src/bob/verifier.py",
            "Function defined: bob.verifier.scope_pytest_to_feature",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == ["tests/test_verifier_scope_pytest.py"]

    def test_bare_tests_tree_never_returned(self, tmp_path):
        """Result never contains the bare tests/ tree path."""
        acs = ["pytest: tests/test_verifier_scope_pytest.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        for p in result:
            assert p not in ("tests", "tests/"), f"Bare tests/ found in result: {result}"

    def test_feature_subtree_included_when_exists(self, tmp_path):
        """tests/<feature_id>/ is included when the directory exists."""
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_sibling_subtree_raises(self, tmp_path):
        """pytest: AC referencing a sibling UUID raises SiblingTestCollectionError."""
        acs = [f"pytest: tests/{SIBLING_ID}/test_sibling.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)

    def test_empty_acs_returns_empty_list(self, tmp_path):
        """Empty AC list with no feature subtree returns []."""
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert result == []

    def test_multiple_pytest_acs_all_included(self, tmp_path):
        """All pytest: ACs are included in the result."""
        acs = [
            "pytest: tests/test_verifier_scope_pytest.py",
            "pytest: tests/test_verifier_must_scope_pytest_to_the_current_feature__boundary.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_verifier_scope_pytest.py" in result
        assert "tests/test_verifier_must_scope_pytest_to_the_current_feature__boundary.py" in result

    def test_result_is_sorted(self, tmp_path):
        """Result is returned in sorted order."""
        acs = [
            "pytest: tests/test_z.py",
            "pytest: tests/test_a.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == sorted(result)


class TestCollectFeatureTestPaths:
    """Lower-level collect_feature_test_paths behaviour."""

    def test_returns_set(self, tmp_path):
        """Always returns a set."""
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert isinstance(result, set)

    def test_collects_pytest_ac_paths(self, tmp_path):
        """pytest: ACs are collected into the set."""
        acs = ["pytest: tests/test_verifier_scope_pytest.py"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/test_verifier_scope_pytest.py" in result

    def test_includes_feature_subtree_when_present(self, tmp_path):
        """Feature subtree is added when the directory exists."""
        (tmp_path / "tests" / FEATURE_ID).mkdir(parents=True)
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_strips_node_id_from_ac(self, tmp_path):
        """pytest: path with ::TestClass::method is stripped to the file path."""
        acs = ["pytest: tests/test_foo.py::TestFoo::test_bar"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/test_foo.py" in result
        assert "tests/test_foo.py::TestFoo::test_bar" not in result


class TestAssertNoSiblingCollection:
    """Guard function for detecting sibling collection."""

    def test_passes_for_feature_own_subtree(self, tmp_path):
        """Passes when argv contains only the current feature's subtree."""
        assert_no_sibling_collection(FEATURE_ID, [f"tests/{FEATURE_ID}"], tmp_path)

    def test_raises_for_bare_tests(self, tmp_path):
        """Raises for bare 'tests' or 'tests/' in argv."""
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, ["tests"], tmp_path)

    def test_raises_for_sibling_uuid_subtree(self, tmp_path):
        """Raises when argv contains a different UUID subtree."""
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, [f"tests/{SIBLING_ID}"], tmp_path)

    def test_ignores_option_flags(self, tmp_path):
        """Option flags (--foo) are ignored and don't trigger the guard."""
        assert_no_sibling_collection(FEATURE_ID, ["--tb=short", f"tests/{FEATURE_ID}"], tmp_path)


class TestBuildScopedPytestArgv:
    """build_scoped_pytest_argv result structure."""

    def test_returns_only_feature_paths(self, tmp_path):
        """Returned argv contains only the feature's own test paths."""
        acs = ["pytest: tests/test_verifier_scope_pytest.py"]
        argv = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
        assert "tests/test_verifier_scope_pytest.py" in argv
        # No bare tests/ tree
        assert "tests" not in argv
        assert "tests/" not in argv

    def test_includes_rootdir_when_subtree_exists(self, tmp_path):
        """Adds --rootdir when the feature subtree exists."""
        (tmp_path / "tests" / FEATURE_ID).mkdir(parents=True)
        argv = build_scoped_pytest_argv(FEATURE_ID, [], tmp_path)
        assert any(arg.startswith("--rootdir=") for arg in argv)
