"""Tests for bob3.verifier — verifies that pytest is scoped to the current feature's own
tests/ subtree, preventing cumulative prior-feature failures from tripping --maxfail.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bob3.verifier import scope_pytest_to_feature
from bob3.verification.per_feature_test_scope import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
)

FEATURE_ID = "aabbccdd-1234-5678-abcd-ef0123456789"
OTHER_ID = "11111111-2222-3333-4444-555555555555"


class TestCollectFeatureTestPaths:
    def test_empty_acs_no_subtree_returns_empty(self, tmp_path):
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert result == set()

    def test_pytest_ac_extracted(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_ID}/test_foo.py"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert f"tests/{FEATURE_ID}/test_foo.py" in result

    def test_pytest_ac_with_node_id_strips_suffix(self, tmp_path):
        acs = [f"pytest: tests/mytest.py::MyClass::test_method"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/mytest.py" in result

    def test_feature_subtree_added_when_dir_exists(self, tmp_path):
        subtree = tmp_path / "tests" / FEATURE_ID
        subtree.mkdir(parents=True)
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_feature_subtree_not_added_when_missing(self, tmp_path):
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" not in result

    def test_non_pytest_acs_ignored(self, tmp_path):
        acs = ["integration: bob3.verifier", "File exists: src/bob3/verifier.py"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert result == set()

    def test_multiple_pytest_acs_all_included(self, tmp_path):
        acs = ["pytest: tests/a.py", "pytest: tests/b.py"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/a.py" in result
        assert "tests/b.py" in result


class TestScopePytestToFeature:
    def test_returns_list(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert isinstance(result, list)

    def test_returns_sorted_paths(self, tmp_path):
        acs = ["pytest: tests/z.py", "pytest: tests/a.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == sorted(result)

    def test_empty_input_returns_empty_list(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert result == []

    def test_does_not_include_bare_tests_dir(self, tmp_path):
        (tmp_path / "tests").mkdir()
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert "tests" not in result
        assert "tests/" not in result

    def test_includes_feature_subtree_when_exists(self, tmp_path):
        subtree = tmp_path / "tests" / FEATURE_ID
        subtree.mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_sibling_subtree_raises(self, tmp_path):
        bad_ac = [f"pytest: tests/{OTHER_ID}/test_foo.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_ID, bad_ac, tmp_path)

    def test_feature_own_pytest_ac_included(self, tmp_path):
        acs = ["pytest: tests/verifier_scoped_feature_tests.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/verifier_scoped_feature_tests.py" in result


class TestAssertNoSiblingCollection:
    def test_feature_own_subtree_allowed(self, tmp_path):
        argv = [f"tests/{FEATURE_ID}"]
        assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_sibling_subtree_raises(self, tmp_path):
        argv = [f"tests/{OTHER_ID}/test_foo.py"]
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_bare_tests_raises(self, tmp_path):
        argv = ["tests"]
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_bare_tests_slash_raises(self, tmp_path):
        argv = ["tests/"]
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_option_flags_skipped(self, tmp_path):
        argv = ["-v", "--tb=short", f"tests/{FEATURE_ID}"]
        assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_empty_argv_passes(self, tmp_path):
        assert_no_sibling_collection(FEATURE_ID, [], tmp_path)


class TestBuildScopedPytestArgv:
    def test_returns_list(self, tmp_path):
        result = build_scoped_pytest_argv(FEATURE_ID, [], tmp_path)
        assert isinstance(result, list)

    def test_does_not_contain_bare_tests(self, tmp_path):
        result = build_scoped_pytest_argv(FEATURE_ID, [], tmp_path)
        for token in result:
            if not token.startswith("-"):
                assert token not in ("tests", "tests/")

    def test_includes_rootdir_when_subtree_exists(self, tmp_path):
        subtree = tmp_path / "tests" / FEATURE_ID
        subtree.mkdir(parents=True)
        result = build_scoped_pytest_argv(FEATURE_ID, [], tmp_path)
        assert any("--rootdir" in tok for tok in result)

    def test_sibling_ac_raises(self, tmp_path):
        bad_ac = [f"pytest: tests/{OTHER_ID}/test_foo.py"]
        with pytest.raises(SiblingTestCollectionError):
            build_scoped_pytest_argv(FEATURE_ID, bad_ac, tmp_path)


class TestBoundaryAndError:
    def test_feature_id_empty_string_returns_empty(self, tmp_path):
        result = scope_pytest_to_feature("", [], tmp_path)
        assert result == []

    def test_none_like_feature_id_does_not_crash(self, tmp_path):
        result = scope_pytest_to_feature("not-a-uuid-but-valid-string", [], tmp_path)
        assert isinstance(result, list)

    def test_whitespace_only_ac_ignored(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_ID, ["   ", "\t"], tmp_path)
        assert result == []

    def test_pytest_ac_with_empty_path_ignored(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_ID, ["pytest:"], tmp_path)
        assert result == []
