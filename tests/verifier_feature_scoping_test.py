"""Tests: verifier MUST scope pytest to the current feature's own test paths.

This file is the AC-specified test module for feature 332b597d-d30d-4d54-b9b7-1598adda73d0.

Root cause addressed: bob3 v.14 round 11 — feature fbd68fee verification
failed because pytest ran the full tests/ tree and tripped --maxfail=20 on
prior-feature stubs before the current feature's own tests ran.

Fix: the verifier scopes every tests_pass invocation to ONLY:
  1. paths declared in ``pytest:`` ACs for the feature, and
  2. the feature's own ``tests/<feature_id>/`` subtree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bob3.verifier import (
    SiblingTestCollectionError,
    assert_no_sibling_collection,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)

FEATURE_A = "aaaaaaaa-1111-0000-0000-000000000001"
FEATURE_B = "bbbbbbbb-2222-0000-0000-000000000002"


# ---------------------------------------------------------------------------
# scope_pytest_to_feature — primary entry point
# ---------------------------------------------------------------------------


class TestScopePytestToFeatureAC:
    """AC: the verifier scopes pytest to only the current feature's own tests."""

    def test_empty_acs_no_dir_returns_empty(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert result == []

    def test_pytest_ac_path_included(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_main.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_main.py" in result

    def test_feature_subtree_included_when_dir_exists(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" in result

    def test_feature_subtree_absent_when_dir_missing(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" not in result

    def test_bare_tests_dir_never_included(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        for path in result:
            assert path.rstrip("/") != "tests", (
                "scope_pytest_to_feature must never return bare 'tests/'"
            )

    def test_sibling_feature_path_in_ac_raises(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_A, acs, tmp_path)

    def test_node_id_suffix_stripped(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py::TestClass::test_method"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result
        assert all("::" not in p for p in result)

    def test_result_is_sorted(self, tmp_path):
        acs = [
            f"pytest: tests/{FEATURE_A}/test_z.py",
            f"pytest: tests/{FEATURE_A}/test_a.py",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert result == sorted(result)

    def test_duplicate_paths_collapsed(self, tmp_path):
        acs = [
            f"pytest: tests/{FEATURE_A}/test_foo.py",
            f"pytest: tests/{FEATURE_A}/test_foo.py",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert len(result) == len(set(result))

    def test_non_pytest_acs_ignored(self, tmp_path):
        acs = [
            "File exists: src/bob3/foo.py",
            "Function defined: bob3.foo.bar",
            "integration: bob3.foo",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert result == []

    def test_ac_paths_and_subtree_combined(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        acs = [f"pytest: tests/{FEATURE_A}/test_extra.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_extra.py" in result
        assert f"tests/{FEATURE_A}" in result


# ---------------------------------------------------------------------------
# collect_feature_test_paths — lower-level path collector
# ---------------------------------------------------------------------------


class TestCollectFeatureTestPathsAC:
    def test_empty_acs_no_dir_returns_empty_set(self, tmp_path):
        assert collect_feature_test_paths(FEATURE_A, [], tmp_path) == set()

    def test_pytest_ac_path_in_result(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        result = collect_feature_test_paths(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result

    def test_feature_dir_included_when_present(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        result = collect_feature_test_paths(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" in result

    def test_case_insensitive_pytest_prefix(self, tmp_path):
        acs = [f"Pytest: tests/{FEATURE_A}/test_foo.py"]
        result = collect_feature_test_paths(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result


# ---------------------------------------------------------------------------
# build_scoped_pytest_argv — argv builder
# ---------------------------------------------------------------------------


class TestBuildScopedPytestArgvAC:
    def test_paths_are_sorted(self, tmp_path):
        acs = [
            f"pytest: tests/{FEATURE_A}/test_z.py",
            f"pytest: tests/{FEATURE_A}/test_a.py",
        ]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        paths = [t for t in argv if not t.startswith("-")]
        assert paths == sorted(paths)

    def test_no_bare_tests_token_in_argv(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        for token in argv:
            if not token.startswith("-"):
                assert token.rstrip("/") != "tests"

    def test_sibling_path_raises(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError):
            build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)

    def test_rootdir_added_when_subtree_exists(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        argv = build_scoped_pytest_argv(FEATURE_A, [], tmp_path)
        assert any(t.startswith("--rootdir=") for t in argv)

    def test_no_rootdir_when_subtree_absent(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        assert not any(t.startswith("--rootdir=") for t in argv)


# ---------------------------------------------------------------------------
# assert_no_sibling_collection — defensive guard
# ---------------------------------------------------------------------------


class TestAssertNoSiblingCollectionAC:
    def test_own_feature_path_allowed(self, tmp_path):
        argv = [f"tests/{FEATURE_A}/test_foo.py"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)

    def test_sibling_feature_dir_raises(self, tmp_path):
        argv = [f"tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError, match=FEATURE_B):
            assert_no_sibling_collection(FEATURE_A, argv, tmp_path)

    def test_bare_tests_raises(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_A, ["tests"], tmp_path)

    def test_bare_tests_slash_raises(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_A, ["tests/"], tmp_path)

    def test_option_flags_ignored(self, tmp_path):
        argv = ["--maxfail=20", f"tests/{FEATURE_A}"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)

    def test_non_uuid_subdirs_allowed(self, tmp_path):
        argv = ["tests/verifier_feature_scoping"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)


# ---------------------------------------------------------------------------
# Integration: verify all symbols importable from bob3.verifier
# ---------------------------------------------------------------------------


class TestOrchestratorIntegrationAC:
    """AC: integration: bob3.orchestrator — verifier scoping wired into the stack."""

    def test_scope_pytest_to_feature_in_bob3_verifier(self):
        from bob3.verifier import scope_pytest_to_feature as fn
        assert callable(fn)

    def test_collect_feature_test_paths_in_bob3_verifier(self):
        from bob3.verifier import collect_feature_test_paths as fn
        assert callable(fn)

    def test_build_scoped_pytest_argv_in_bob3_verifier(self):
        from bob3.verifier import build_scoped_pytest_argv as fn
        assert callable(fn)

    def test_assert_no_sibling_collection_in_bob3_verifier(self):
        from bob3.verifier import assert_no_sibling_collection as fn
        assert callable(fn)

    def test_sibling_test_collection_error_is_runtime_error(self):
        from bob3.verifier import SiblingTestCollectionError
        assert issubclass(SiblingTestCollectionError, RuntimeError)

    def test_verifier_py_or_package_exists(self):
        ws = Path(__file__).parent.parent
        verifier_py = ws / "src" / "bob3" / "verifier.py"
        verifier_pkg = ws / "src" / "bob3" / "verifier" / "__init__.py"
        assert verifier_py.exists() or verifier_pkg.exists()

    def test_superpowers_check_tests_pass_accepts_feature_id(self):
        """_check_tests_pass must accept feature_id/feature_acs so orchestrator
        can pass scoping context to the verifier layer."""
        import inspect
        from bob3.superpowers import _check_tests_pass
        sig = inspect.signature(_check_tests_pass)
        assert "feature_id" in sig.parameters
        assert "feature_acs" in sig.parameters

    def test_scope_pytest_to_feature_returns_list(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert isinstance(result, list)

    def test_orchestrator_run_loop_importable(self):
        """The orchestrator run_loop must be importable (integration smoke test)."""
        from bob3.orchestrator import run_loop  # noqa: F401
        assert True
