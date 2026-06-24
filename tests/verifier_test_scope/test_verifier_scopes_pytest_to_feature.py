"""Tests verifying that bob.verifier.scope_pytest_to_feature scopes pytest
to only the current feature's own test paths.

Root problem (2026-05-29): the verifier ran `pytest tests/` which collected
ALL feature subtrees. pytest-xdist's --maxfail=20 tripped on accumulated
failures from prior features before the current feature's tests ran, causing
every feature after the 20th broken test to fail regardless of its own quality.

Fix: scope_pytest_to_feature() returns ONLY the current feature's paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bob.verifier import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)

FEATURE_A = "aaaaaaaa-0000-0000-0000-000000000001"
FEATURE_B = "bbbbbbbb-0000-0000-0000-000000000002"


class TestScopePytestToFeature:
    """scope_pytest_to_feature is the primary entry point for AC tests_pass."""

    def test_empty_when_no_acs_and_no_dir(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert result == []

    def test_returns_list_not_set(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert isinstance(result, list)

    def test_includes_pytest_ac_path(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_main.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_main.py" in result

    def test_includes_feature_subtree_when_dir_exists(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" in result

    def test_excludes_feature_subtree_when_dir_absent(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" not in result

    def test_never_includes_bare_tests_dir(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert "tests" not in result
        assert "tests/" not in result

    def test_result_is_sorted(self, tmp_path):
        acs = [
            f"pytest: tests/{FEATURE_A}/test_z.py",
            f"pytest: tests/{FEATURE_A}/test_a.py",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert result == sorted(result)

    def test_strips_node_id_from_ac_path(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py::TestClass::test_method"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result
        assert all("::" not in p for p in result)

    def test_deduplicates_repeated_paths(self, tmp_path):
        acs = [
            f"pytest: tests/{FEATURE_A}/test_foo.py",
            f"pytest: tests/{FEATURE_A}/test_foo.py",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert result.count(f"tests/{FEATURE_A}/test_foo.py") == 1

    def test_raises_for_sibling_feature_ac(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_A, acs, tmp_path)

    def test_combines_ac_paths_and_subtree(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        acs = [f"pytest: tests/{FEATURE_A}/test_special.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_special.py" in result
        assert f"tests/{FEATURE_A}" in result

    def test_ignores_non_pytest_acs(self, tmp_path):
        acs = [
            "File exists: src/bob/foo.py",
            "Function defined: bob.foo.bar",
            "integration: bob.foo",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert result == []

    def test_case_insensitive_pytest_prefix(self, tmp_path):
        acs = [f"PYTEST: tests/{FEATURE_A}/test_foo.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result


class TestSiblingIsolation:
    """Sibling feature subtrees must never appear in the scoped paths."""

    def test_own_feature_path_allowed(self, tmp_path):
        argv = [f"tests/{FEATURE_A}/test_foo.py"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)

    def test_bare_tests_raises(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_A, ["tests"], tmp_path)

    def test_bare_tests_slash_raises(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_A, ["tests/"], tmp_path)

    def test_sibling_uuid_path_raises(self, tmp_path):
        argv = [f"tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError, match=FEATURE_B):
            assert_no_sibling_collection(FEATURE_A, argv, tmp_path)

    def test_option_flags_skipped(self, tmp_path):
        argv = ["--maxfail=20", f"tests/{FEATURE_A}"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)

    def test_non_uuid_subdir_allowed(self, tmp_path):
        argv = ["tests/verifier_test_scope"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)


class TestBuildScopedPytestArgv:
    def test_no_bare_tests_dir(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        tokens = [t for t in argv if not t.startswith("-")]
        assert all(t.rstrip("/") != "tests" for t in tokens)

    def test_raises_for_sibling_in_acs(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError):
            build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)

    def test_adds_rootdir_when_subtree_exists(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        argv = build_scoped_pytest_argv(FEATURE_A, [], tmp_path)
        assert any(t.startswith("--rootdir=") for t in argv)

    def test_no_rootdir_when_subtree_absent(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        assert not any(t.startswith("--rootdir=") for t in argv)


class TestVerifierIntegration:
    """Verify scope_pytest_to_feature is importable from bob.verifier."""

    def test_scope_pytest_to_feature_callable(self):
        assert callable(scope_pytest_to_feature)

    def test_collect_feature_test_paths_callable(self):
        assert callable(collect_feature_test_paths)

    def test_build_scoped_pytest_argv_callable(self):
        assert callable(build_scoped_pytest_argv)

    def test_assert_no_sibling_collection_callable(self):
        assert callable(assert_no_sibling_collection)

    def test_sibling_test_collection_error_is_runtime_error(self):
        assert issubclass(SiblingTestCollectionError, RuntimeError)

    def test_scope_returns_empty_not_full_suite(self, tmp_path):
        # Core invariant: empty ACs + no subtree → empty list (NOT tests/ fallback).
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert result == []
        assert "tests" not in result
