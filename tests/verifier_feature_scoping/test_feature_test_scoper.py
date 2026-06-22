"""Tests for bob3.verifier.feature_test_scoper — verifier pytest scoping.

Verifies that scope_pytest_to_feature scopes pytest invocations to ONLY the
current feature's own test paths, preventing cumulative prior-feature failures
from tripping pytest-xdist's maxfail and blocking subsequent feature verification.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure src/ is on the path for imports
_SRC = Path(__file__).parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bob3.verifier.feature_test_scoper import (
    scope_pytest_to_feature,
    collect_feature_test_paths,
    build_scoped_pytest_argv,
    assert_no_sibling_collection,
    SiblingTestCollectionError,
)


FEATURE_A = "891c92a8-f0da-4db8-b519-fc12546d137d"
FEATURE_B = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# collect_feature_test_paths
# ---------------------------------------------------------------------------


class TestCollectFeatureTestPaths:
    def test_returns_empty_set_when_no_acs_and_no_dir(self, tmp_path):
        """No pytest: ACs and no feature subtree → empty set."""
        result = collect_feature_test_paths(FEATURE_A, [], tmp_path)
        assert result == set()

    def test_includes_pytest_ac_path(self, tmp_path):
        """pytest: AC entries contribute their path to the result."""
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        result = collect_feature_test_paths(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result

    def test_strips_node_id_suffix(self, tmp_path):
        """Node-id suffixes (::Class::method) are stripped from pytest: paths."""
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py::TestClass::test_method"]
        result = collect_feature_test_paths(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result
        assert any("::" not in p for p in result)

    def test_includes_feature_subtree_when_exists(self, tmp_path):
        """tests/<feature_id>/ directory is included when it exists."""
        feature_dir = tmp_path / "tests" / FEATURE_A
        feature_dir.mkdir(parents=True)
        result = collect_feature_test_paths(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" in result

    def test_does_not_include_subtree_when_missing(self, tmp_path):
        """tests/<feature_id>/ is not included when directory doesn't exist."""
        result = collect_feature_test_paths(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" not in result

    def test_ignores_non_pytest_acs(self, tmp_path):
        """Non-pytest: ACs are not counted as test paths."""
        acs = [
            "File exists: src/bob3/foo.py",
            "Function defined: bob3.foo.bar",
            "integration: bob3.foo",
        ]
        result = collect_feature_test_paths(FEATURE_A, acs, tmp_path)
        assert result == set()

    def test_case_insensitive_pytest_prefix(self, tmp_path):
        """pytest: prefix matching is case-insensitive."""
        acs = [f"Pytest: tests/{FEATURE_A}/test_foo.py"]
        result = collect_feature_test_paths(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result

    def test_multiple_pytest_acs(self, tmp_path):
        """Multiple pytest: ACs are all included."""
        acs = [
            f"pytest: tests/{FEATURE_A}/test_foo.py",
            f"pytest: tests/{FEATURE_A}/test_bar.py",
        ]
        result = collect_feature_test_paths(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_foo.py" in result
        assert f"tests/{FEATURE_A}/test_bar.py" in result


# ---------------------------------------------------------------------------
# build_scoped_pytest_argv
# ---------------------------------------------------------------------------


class TestBuildScopedPytestArgv:
    def test_returns_sorted_paths(self, tmp_path):
        """Returned argv is sorted."""
        acs = [
            f"pytest: tests/{FEATURE_A}/test_z.py",
            f"pytest: tests/{FEATURE_A}/test_a.py",
        ]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        paths = [t for t in argv if not t.startswith("-")]
        assert paths == sorted(paths)

    def test_no_bare_tests_dir(self, tmp_path):
        """argv never contains bare 'tests' or 'tests/'."""
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        for token in argv:
            if not token.startswith("-"):
                assert not token.rstrip("/") == "tests", (
                    f"bare 'tests' found in argv: {argv}"
                )

    def test_raises_on_sibling_feature_path(self, tmp_path):
        """Raises SiblingTestCollectionError if a sibling's subtree sneaks in."""
        acs = [f"pytest: tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError):
            build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)

    def test_adds_rootdir_when_feature_subtree_exists(self, tmp_path):
        """--rootdir flag is added when the feature's tests/ subtree exists."""
        feature_dir = tmp_path / "tests" / FEATURE_A
        feature_dir.mkdir(parents=True)
        argv = build_scoped_pytest_argv(FEATURE_A, [], tmp_path)
        assert any(token.startswith("--rootdir=") for token in argv)

    def test_no_rootdir_when_feature_subtree_absent(self, tmp_path):
        """No --rootdir when the feature subtree doesn't exist."""
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_A, acs, tmp_path)
        assert not any(token.startswith("--rootdir=") for token in argv)


# ---------------------------------------------------------------------------
# assert_no_sibling_collection
# ---------------------------------------------------------------------------


class TestAssertNoSiblingCollection:
    def test_passes_for_own_feature_path(self, tmp_path):
        """No error when argv only contains this feature's paths."""
        argv = [f"tests/{FEATURE_A}/test_foo.py"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)  # no exception

    def test_raises_for_sibling_feature_dir(self, tmp_path):
        """Raises when argv references another feature's UUID-like dir."""
        argv = [f"tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError, match=FEATURE_B):
            assert_no_sibling_collection(FEATURE_A, argv, tmp_path)

    def test_raises_for_bare_tests_dir(self, tmp_path):
        """Raises when argv contains bare 'tests'."""
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_A, ["tests"], tmp_path)

    def test_raises_for_bare_tests_slash(self, tmp_path):
        """Raises when argv contains 'tests/'."""
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_A, ["tests/"], tmp_path)

    def test_ignores_option_flags(self, tmp_path):
        """Option flags starting with '-' are ignored."""
        argv = ["--maxfail=20", f"tests/{FEATURE_A}"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)  # no exception

    def test_non_uuid_subdirs_are_allowed(self, tmp_path):
        """Non-UUID-like test directory names are not treated as sibling features."""
        argv = ["tests/verifier_feature_scoping"]
        assert_no_sibling_collection(FEATURE_A, argv, tmp_path)  # no exception


# ---------------------------------------------------------------------------
# scope_pytest_to_feature (primary entry point)
# ---------------------------------------------------------------------------


class TestScopePytestToFeature:
    def test_returns_sorted_list(self, tmp_path):
        """Returns a sorted list of test paths."""
        acs = [
            f"pytest: tests/{FEATURE_A}/test_z.py",
            f"pytest: tests/{FEATURE_A}/test_a.py",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert result == sorted(result)

    def test_returns_empty_list_when_no_paths(self, tmp_path):
        """Returns empty list when no pytest: ACs and no feature subtree."""
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert result == []

    def test_excludes_sibling_feature_paths(self, tmp_path):
        """Never includes paths from sibling feature subtrees."""
        # Only this feature's paths
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        for path in result:
            parts = Path(path).parts
            if len(parts) >= 2 and parts[0] == "tests":
                if len(parts) >= 3:
                    assert parts[1] == FEATURE_A, (
                        f"Sibling feature path found in result: {path}"
                    )

    def test_includes_pytest_ac_paths(self, tmp_path):
        """pytest: AC paths appear in the result."""
        acs = [f"pytest: tests/{FEATURE_A}/test_main.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_main.py" in result

    def test_includes_feature_subtree_when_exists(self, tmp_path):
        """tests/<feature_id>/ is included when it exists."""
        feature_dir = tmp_path / "tests" / FEATURE_A
        feature_dir.mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        assert f"tests/{FEATURE_A}" in result

    def test_does_not_include_whole_tests_dir(self, tmp_path):
        """Result never contains bare 'tests' or 'tests/'."""
        feature_dir = tmp_path / "tests" / FEATURE_A
        feature_dir.mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_A, [], tmp_path)
        for path in result:
            assert path.rstrip("/") != "tests", (
                f"Bare 'tests' found in result: {result}"
            )

    def test_raises_on_sibling_inclusion(self, tmp_path):
        """Raises SiblingTestCollectionError if sibling paths sneak in."""
        # Simulating a broken AC that references the wrong feature
        acs = [f"pytest: tests/{FEATURE_B}/test_other.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_A, acs, tmp_path)

    def test_deduplicates_paths(self, tmp_path):
        """Duplicate paths are not repeated in the result."""
        acs = [
            f"pytest: tests/{FEATURE_A}/test_foo.py",
            f"pytest: tests/{FEATURE_A}/test_foo.py",
        ]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert len(result) == len(set(result))

    def test_combines_ac_paths_and_feature_subtree(self, tmp_path):
        """Both pytest: AC paths and feature subtree are included."""
        feature_dir = tmp_path / "tests" / FEATURE_A
        feature_dir.mkdir(parents=True)
        acs = [f"pytest: tests/{FEATURE_A}/test_special.py"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert f"tests/{FEATURE_A}/test_special.py" in result
        assert f"tests/{FEATURE_A}" in result

    def test_strips_node_id_from_pytest_ac(self, tmp_path):
        """pytest: AC with ::NodeID suffix is stripped to the file path."""
        acs = [f"pytest: tests/{FEATURE_A}/test_foo.py::TestClass::test_method"]
        result = scope_pytest_to_feature(FEATURE_A, acs, tmp_path)
        assert any("::" not in p for p in result)
        assert f"tests/{FEATURE_A}/test_foo.py" in result


# ---------------------------------------------------------------------------
# Integration: bob3.verifier imports scope_pytest_to_feature
# ---------------------------------------------------------------------------


class TestVerifierIntegration:
    def test_importable_from_bob3_verifier(self):
        """scope_pytest_to_feature is importable from bob3.verifier."""
        from bob3.verifier import scope_pytest_to_feature as fn
        assert callable(fn)

    def test_importable_from_feature_test_scoper(self):
        """scope_pytest_to_feature is importable from bob3.verifier.feature_test_scoper."""
        from bob3.verifier.feature_test_scoper import scope_pytest_to_feature as fn
        assert callable(fn)

    def test_both_imports_are_same_function(self):
        """Both import paths resolve to the same underlying function."""
        from bob3.verifier import scope_pytest_to_feature as fn1
        from bob3.verifier.feature_test_scoper import scope_pytest_to_feature as fn2
        assert fn1 is fn2
