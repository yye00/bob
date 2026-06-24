"""Tests for bob3.verifier.scope_pytest_to_feature — feature-scoped pytest invocation.

AC: pytest: tests/test_verifier_scope.py
    integration: bob3.orchestrator

Ensures the verifier's tests_pass step scopes pytest to ONLY the current
feature's own test paths, preventing pytest-xdist --maxfail from tripping on
accumulated failures from prior features.
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

FEATURE_ID = "0b5de6b0-f093-4eb0-8d74-8ee8e151ff61"
SIBLING_ID = "fbd68fee-1234-5678-90ab-cdefabcdef12"


class TestScopePytestToFeature:
    """Core behaviour of scope_pytest_to_feature."""

    def test_returns_only_pytest_ac_paths(self, tmp_path):
        """scope_pytest_to_feature returns only paths from pytest: ACs."""
        acs = [
            "pytest: tests/test_verifier_scope.py",
            "File exists: src/bob3/verifier.py",
            "Function defined: bob3.verifier.scope_pytest_to_feature",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == ["tests/test_verifier_scope.py"]

    def test_bare_tests_tree_never_returned(self, tmp_path):
        """Result never contains the bare tests/ tree path."""
        acs = ["pytest: tests/test_verifier_scope.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        for p in result:
            assert p not in ("tests", "tests/"), f"Bare tests/ found in result: {result}"

    def test_feature_subtree_included_when_exists(self, tmp_path):
        """tests/<feature_id>/ is included when the directory exists."""
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_sibling_uuid_in_pytest_ac_raises(self, tmp_path):
        """pytest: AC referencing another feature's UUID raises SiblingTestCollectionError."""
        acs = [f"pytest: tests/{SIBLING_ID}/test_sibling.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)

    def test_multiple_pytest_acs_all_returned(self, tmp_path):
        """All pytest: ACs are included in the result."""
        acs = [
            "pytest: tests/test_a.py",
            "pytest: tests/test_b.py",
            "File exists: src/bob3/verifier.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_a.py" in result
        assert "tests/test_b.py" in result

    def test_result_is_sorted(self, tmp_path):
        """Result is returned in sorted order."""
        acs = [
            "pytest: tests/test_zzz.py",
            "pytest: tests/test_aaa.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == sorted(result)

    def test_empty_acs_no_subtree_returns_empty(self, tmp_path):
        """Empty ACs with no feature subtree returns empty list."""
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert result == []

    def test_pytest_ac_with_node_id_stripped(self, tmp_path):
        """Node-id (::) suffixes in pytest: AC paths are stripped."""
        acs = ["pytest: tests/test_module.py::TestClass::test_method"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_module.py" in result
        for p in result:
            assert "::" not in p


class TestCollectFeatureTestPaths:
    """Tests for collect_feature_test_paths."""

    def test_returns_set(self, tmp_path):
        """Return type is a set."""
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert isinstance(result, set)

    def test_includes_pytest_ac_paths(self, tmp_path):
        """pytest: ACs yield paths in the result."""
        acs = ["pytest: tests/test_scope.py"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/test_scope.py" in result

    def test_includes_feature_subtree_if_exists(self, tmp_path):
        """tests/<feature_id>/ is included when directory exists."""
        (tmp_path / "tests" / FEATURE_ID).mkdir(parents=True)
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_excludes_sibling_subtree(self, tmp_path):
        """Sibling feature subtrees are NOT auto-included."""
        (tmp_path / "tests" / SIBLING_ID).mkdir(parents=True)
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert f"tests/{SIBLING_ID}" not in result


class TestAssertNoSiblingCollection:
    """Tests for assert_no_sibling_collection."""

    def test_own_feature_path_ok(self, tmp_path):
        """Own feature subtree path does not raise."""
        assert_no_sibling_collection(FEATURE_ID, [f"tests/{FEATURE_ID}"], tmp_path)

    def test_bare_tests_raises(self, tmp_path):
        """Bare 'tests' in argv raises SiblingTestCollectionError."""
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, ["tests"], tmp_path)

    def test_bare_tests_slash_raises(self, tmp_path):
        """Bare 'tests/' raises SiblingTestCollectionError."""
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, ["tests/"], tmp_path)

    def test_sibling_uuid_path_raises(self, tmp_path):
        """Sibling UUID path raises SiblingTestCollectionError."""
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, [f"tests/{SIBLING_ID}"], tmp_path)

    def test_option_flags_are_skipped(self, tmp_path):
        """Option flags like --rootdir are not checked for siblings."""
        assert_no_sibling_collection(
            FEATURE_ID,
            [f"--rootdir=tests/{FEATURE_ID}", f"tests/{FEATURE_ID}"],
            tmp_path,
        )

    def test_regular_test_file_ok(self, tmp_path):
        """A regular test file path (not a UUID subtree) does not raise."""
        assert_no_sibling_collection(
            FEATURE_ID,
            ["tests/test_verifier_scope.py"],
            tmp_path,
        )


class TestBuildScopedPytestArgv:
    """Tests for build_scoped_pytest_argv."""

    def test_returns_list_of_paths(self, tmp_path):
        """build_scoped_pytest_argv returns a list."""
        acs = ["pytest: tests/test_verifier_scope.py"]
        result = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
        assert isinstance(result, list)
        assert "tests/test_verifier_scope.py" in result

    def test_no_bare_tests_in_argv(self, tmp_path):
        """The resulting argv never contains bare 'tests' or 'tests/'."""
        acs = ["pytest: tests/test_scope.py"]
        result = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
        assert "tests" not in result
        assert "tests/" not in result

    def test_empty_acs_no_subtree_returns_empty_argv(self, tmp_path):
        """No ACs and no feature subtree yields empty argv."""
        result = build_scoped_pytest_argv(FEATURE_ID, [], tmp_path)
        # Should be empty (no paths, possibly just rootdir flag if subtree exists)
        paths = [t for t in result if not t.startswith("-")]
        assert paths == []


class TestOrchestratorIntegration:
    """Integration: orchestrator imports scope_pytest_to_feature from bob3.verifier."""

    def test_orchestrator_imports_scope_pytest_to_feature(self):
        """bob3.orchestrator exposes scope_pytest_to_feature."""
        import bob3.orchestrator as orch
        assert hasattr(orch, "scope_pytest_to_feature")

    def test_orchestrator_imports_sibling_error(self):
        """bob3.orchestrator exposes SiblingTestCollectionError."""
        import bob3.orchestrator as orch
        assert hasattr(orch, "SiblingTestCollectionError")

    def test_scope_pytest_to_feature_callable_from_orchestrator(self, tmp_path):
        """scope_pytest_to_feature can be called through orchestrator import."""
        import bob3.orchestrator as orch
        acs = ["pytest: tests/test_verifier_scope.py"]
        result = orch.scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == ["tests/test_verifier_scope.py"]
