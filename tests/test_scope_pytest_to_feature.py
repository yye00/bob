"""Tests for bob3.verifier.scope_pytest_to_feature (feature 7dd55444-571d-4d43-b211-b51e1ae1cf70).

Verifies the verifier scopes pytest to ONLY the current feature's own test
paths — never the whole tests/ tree or sibling feature subtrees.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.verifier import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)

FEATURE_ID = "7dd55444-571d-4d43-b211-b51e1ae1cf70"
SIBLING_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestScopePytestToFeature:
    def test_empty_acs_and_no_subtree_returns_empty(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert result == []

    def test_pytest_ac_path_included(self, tmp_path):
        acs = ["pytest: tests/test_foo.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_foo.py" in result

    def test_multiple_pytest_acs_all_included(self, tmp_path):
        acs = [
            "pytest: tests/test_alpha.py",
            "pytest: tests/test_beta.py",
            "File exists: src/bob3/some_module.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_alpha.py" in result
        assert "tests/test_beta.py" in result
        assert len([p for p in result if "some_module" in p]) == 0

    def test_result_is_sorted(self, tmp_path):
        acs = [
            "pytest: tests/test_z.py",
            "pytest: tests/test_a.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == sorted(result)

    def test_feature_subtree_included_when_dir_exists(self, tmp_path):
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_sibling_pytest_ac_raises(self, tmp_path):
        acs = [f"pytest: tests/{SIBLING_ID}/test_x.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)

    def test_bare_tests_path_raises(self, tmp_path):
        acs = ["pytest: tests/"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)

    def test_returns_list_not_set(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert isinstance(result, list)

    def test_node_id_suffix_stripped(self, tmp_path):
        acs = ["pytest: tests/test_foo.py::TestClass::test_method"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_foo.py" in result
        assert "::TestClass::test_method" not in str(result)


class TestCollectFeatureTestPaths:
    def test_empty_input_returns_empty_set(self, tmp_path):
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert result == set()

    def test_pytest_ac_added(self, tmp_path):
        acs = ["pytest: tests/test_bar.py"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert "tests/test_bar.py" in result

    def test_feature_subtree_added_when_exists(self, tmp_path):
        (tmp_path / "tests" / FEATURE_ID).mkdir(parents=True)
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_non_pytest_acs_ignored(self, tmp_path):
        acs = ["File exists: src/bob3/foo.py", "Function defined: bob3.foo.bar"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert result == set()


class TestAssertNoSiblingCollection:
    def test_own_feature_path_passes(self, tmp_path):
        assert_no_sibling_collection(FEATURE_ID, [f"tests/{FEATURE_ID}"], tmp_path)

    def test_sibling_uuid_raises(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError, match=SIBLING_ID):
            assert_no_sibling_collection(FEATURE_ID, [f"tests/{SIBLING_ID}"], tmp_path)

    def test_bare_tests_raises(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, ["tests"], tmp_path)

    def test_bare_tests_slash_raises(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, ["tests/"], tmp_path)

    def test_option_flags_skipped(self, tmp_path):
        assert_no_sibling_collection(
            FEATURE_ID,
            ["-v", "--tb=short", f"tests/{FEATURE_ID}"],
            tmp_path,
        )


class TestBuildScopedPytestArgv:
    def test_empty_returns_empty(self, tmp_path):
        result = build_scoped_pytest_argv(FEATURE_ID, [], tmp_path)
        assert isinstance(result, list)

    def test_pytest_acs_appear_in_argv(self, tmp_path):
        acs = ["pytest: tests/test_foo.py"]
        result = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
        assert "tests/test_foo.py" in result
