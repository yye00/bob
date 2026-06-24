"""Tests for bob3.verifier.scope_pytest_to_feature — feature-scoped pytest paths.

Verifies that the verifier scopes pytest invocations to ONLY the current
feature's own test paths, preventing cumulative prior-feature failures from
tripping pytest-xdist's maxfail before the current feature's tests run.
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

FEATURE_A = "aaaaaaaa-0000-0000-0000-000000000001"
FEATURE_B = "bbbbbbbb-0000-0000-0000-000000000002"


class TestScopePytestToFeature:
    def test_returns_empty_list_when_no_acs_no_dir(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert result == []

    def test_returns_sorted_list(self, tmp_path):
        acs = [
            f"pytest: tests/{FEATURE_A}/test_z.py",
            f"pytest: tests/{FEATURE_A}/test_a.py",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert result == sorted(result)

    def test_includes_pytest_ac_paths(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_main.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_main.py" in result

    def test_includes_feature_subtree_when_dir_exists(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" in result

    def test_does_not_include_feature_subtree_when_dir_missing(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" not in result

    def test_does_not_include_bare_tests_dir(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        for path in result:
            assert path.rstrip("/") != "tests"

    def test_strips_node_id_suffix(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py::TestClass::test_method"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result
        assert all("::" not in p for p in result)

    def test_deduplicates_paths(self, tmp_path):
        acs = [
            f"pytest: tests/{FEATURE_A}/test_foo.py",
            f"pytest: tests/{FEATURE_A}/test_foo.py",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert len(result) == len(set(result))

    def test_raises_on_sibling_feature_path(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_A, acs, tmp_path)

    def test_combines_ac_paths_and_feature_subtree(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        acs = [f"pytest: tests/{FEATURE_A}/test_special.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_special.py" in result
        assert f"tests/{FEATURE_A}" in result

    def test_ignores_non_pytest_acs(self, tmp_path):
        acs = [
            "File exists: src/bob3/foo.py",
            "Function defined: bob3.foo.bar",
            "integration: bob3.foo",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert result == []


class TestCollectFeatureTestPaths:
    def test_returns_empty_set_when_no_acs_and_no_dir(self, tmp_path):
        assert collect_feature_test_paths(FEATURE_A, [], tmp_path) == set()

    def test_includes_pytest_ac_path(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        result = collect_feature_test_paths(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result

    def test_includes_feature_dir_when_exists(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        result = collect_feature_test_paths(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" in result

    def test_case_insensitive_pytest_prefix(self, tmp_path):
        acs = [f"Pytest: tests/{FEATURE_A}/test_foo.py"]
        result = collect_feature_test_paths(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result


class TestBuildScopedPytestArgv:
    def test_returns_sorted_paths(self, tmp_path):
        acs = [
            f"pytest: tests/{FEATURE_A}/test_z.py",
            f"pytest: tests/{FEATURE_A}/test_a.py",
        ]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        paths = [t for t in argv if not t.startswith("-")]
        assert paths == sorted(paths)

    def test_no_bare_tests_dir(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        for token in argv:
            if not token.startswith("-"):
                assert token.rstrip("/") != "tests"

    def test_raises_on_sibling_feature_path(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError):
            build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)

    def test_adds_rootdir_when_feature_subtree_exists(self, tmp_path):
        (tmp_path / "tests" / FEATURE_A).mkdir(parents=True)
        argv = build_scoped_pytest_argv(FEATURE_A, [], tmp_path)
        assert any(t.startswith("--rootdir=") for t in argv)

    def test_no_rootdir_when_feature_subtree_absent(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        assert not any(t.startswith("--rootdir=") for t in argv)


class TestAssertNoSiblingCollection:
    def test_passes_for_own_feature_path(self, tmp_path):
        argv = [f"tests/{FEATURE_A}/test_foo.py"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)

    def test_raises_for_sibling_feature_dir(self, tmp_path):
        argv = [f"tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError, match=FEATURE_B):
            assert_no_sibling_collection(FEATURE_A, argv, tmp_path)

    def test_raises_for_bare_tests(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_A, ["tests"], tmp_path)

    def test_raises_for_bare_tests_slash(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_A, ["tests/"], tmp_path)

    def test_ignores_option_flags(self, tmp_path):
        argv = ["--maxfail=20", f"tests/{FEATURE_A}"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)

    def test_non_uuid_subdirs_are_allowed(self, tmp_path):
        argv = ["tests/verifier_feature_scoping"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)


class TestVerifierIntegration:
    def test_scope_pytest_to_feature_importable_from_bob3_verifier(self):
        from bob3.verifier import scope_pytest_to_feature as fn
        assert callable(fn)

    def test_collect_feature_test_paths_importable_from_bob3_verifier(self):
        from bob3.verifier import collect_feature_test_paths as fn
        assert callable(fn)

    def test_build_scoped_pytest_argv_importable_from_bob3_verifier(self):
        from bob3.verifier import build_scoped_pytest_argv as fn
        assert callable(fn)

    def test_assert_no_sibling_collection_importable_from_bob3_verifier(self):
        from bob3.verifier import assert_no_sibling_collection as fn
        assert callable(fn)

    def test_sibling_test_collection_error_importable_from_bob3_verifier(self):
        from bob3.verifier import SiblingTestCollectionError
        assert issubclass(SiblingTestCollectionError, RuntimeError)

    def test_bob3_verifier_package_exists(self):
        ws = Path(__file__).parent.parent
        # The verifier module satisfies "File exists: src/bob3/verifier.py" because
        # the package src/bob3/verifier/__init__.py is the canonical implementation.
        verifier_py = ws / "src" / "bob3" / "verifier.py"
        verifier_pkg = ws / "src" / "bob3" / "verifier" / "__init__.py"
        assert verifier_py.exists() or verifier_pkg.exists(), (
            "Neither src/bob3/verifier.py nor src/bob3/verifier/__init__.py exists"
        )
