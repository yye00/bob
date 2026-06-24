"""Tests for bob.verifier.scope_pytest_to_feature.

Verifies the verifier's tests_pass step scopes pytest to ONLY the current
feature's own test paths — never the whole tests/ tree or sibling feature
subtrees. Closes the bug where cumulative prior-feature failures tripped
pytest-xdist --maxfail before the current feature's own tests ran.
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

FEATURE_ID = "62c02ec5-1373-4a7c-abe6-f9f5b3797038"
SIBLING_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


# ---------------------------------------------------------------------------
# scope_pytest_to_feature — primary entry point
# ---------------------------------------------------------------------------


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
            "File exists: src/bob/some_module.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_alpha.py" in result
        assert "tests/test_beta.py" in result

    def test_non_pytest_acs_do_not_add_paths(self, tmp_path):
        acs = [
            "File exists: src/bob/foo.py",
            "Function defined: bob.foo.bar",
            "integration: bob.foo",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == []

    def test_result_is_sorted(self, tmp_path):
        acs = [
            "pytest: tests/test_z.py",
            "pytest: tests/test_a.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == sorted(result)

    def test_node_id_suffix_stripped(self, tmp_path):
        acs = ["pytest: tests/test_foo.py::TestClass::test_bar"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_foo.py" in result
        assert not any("::" in p for p in result)

    def test_feature_subtree_included_when_dir_exists(self, tmp_path):
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_feature_subtree_not_included_when_dir_missing(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" not in result

    def test_returns_list_not_set(self, tmp_path):
        acs = ["pytest: tests/test_foo.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert isinstance(result, list)

    def test_sibling_subtree_in_acs_raises(self, tmp_path):
        acs = [f"pytest: tests/{SIBLING_ID}/test_bar.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)

    def test_bare_tests_dir_in_acs_raises(self, tmp_path):
        acs = ["pytest: tests/"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)


# ---------------------------------------------------------------------------
# collect_feature_test_paths — lower-level collector
# ---------------------------------------------------------------------------


class TestCollectFeatureTestPaths:
    def test_empty_when_no_acs_and_no_dir(self, tmp_path):
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert result == set()

    def test_pytest_ac_path_included(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_ID}/test_foo.py"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert f"tests/{FEATURE_ID}/test_foo.py" in result

    def test_feature_subtree_included_when_exists(self, tmp_path):
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert f"tests/{FEATURE_ID}" in result

    def test_non_pytest_acs_ignored(self, tmp_path):
        acs = ["File exists: src/bob/foo.py", "Function defined: bob.foo.bar"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert result == set()

    def test_returns_set(self, tmp_path):
        result = collect_feature_test_paths(FEATURE_ID, [], tmp_path)
        assert isinstance(result, set)

    def test_strips_node_id_from_path(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_ID}/test_foo.py::TestClass::test_method"]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert f"tests/{FEATURE_ID}/test_foo.py" in result
        assert not any("::" in p for p in result)

    def test_multiple_pytest_acs_all_collected(self, tmp_path):
        acs = [
            f"pytest: tests/{FEATURE_ID}/test_foo.py",
            f"pytest: tests/{FEATURE_ID}/test_bar.py",
        ]
        result = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
        assert f"tests/{FEATURE_ID}/test_foo.py" in result
        assert f"tests/{FEATURE_ID}/test_bar.py" in result


# ---------------------------------------------------------------------------
# build_scoped_pytest_argv
# ---------------------------------------------------------------------------


class TestBuildScopedPytestArgv:
    def test_returns_list(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_ID}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
        assert isinstance(argv, list)

    def test_includes_pytest_ac_paths(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_ID}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
        assert f"tests/{FEATURE_ID}/test_foo.py" in argv

    def test_does_not_include_bare_tests_dir(self, tmp_path):
        acs = [f"pytest: tests/{FEATURE_ID}/test_foo.py"]
        argv = build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)
        assert "tests/" not in argv
        assert "tests" not in argv

    def test_includes_rootdir_when_feature_subtree_exists(self, tmp_path):
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        argv = build_scoped_pytest_argv(FEATURE_ID, [], tmp_path)
        assert any("rootdir" in arg for arg in argv)

    def test_empty_acs_and_no_subtree_returns_empty(self, tmp_path):
        argv = build_scoped_pytest_argv(FEATURE_ID, [], tmp_path)
        test_paths = [a for a in argv if not a.startswith("-")]
        assert test_paths == []

    def test_sibling_path_in_acs_raises(self, tmp_path):
        acs = [f"pytest: tests/{SIBLING_ID}/test_bar.py"]
        with pytest.raises(SiblingTestCollectionError):
            build_scoped_pytest_argv(FEATURE_ID, acs, tmp_path)


# ---------------------------------------------------------------------------
# assert_no_sibling_collection — defensive guard
# ---------------------------------------------------------------------------


class TestAssertNoSiblingCollection:
    def test_own_feature_subtree_ok(self, tmp_path):
        argv = [f"tests/{FEATURE_ID}"]
        assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)  # no exception

    def test_bare_tests_raises(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError, match="bare 'tests/'"):
            assert_no_sibling_collection(FEATURE_ID, ["tests/"], tmp_path)

    def test_bare_tests_no_slash_raises(self, tmp_path):
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(FEATURE_ID, ["tests"], tmp_path)

    def test_sibling_uuid_path_raises(self, tmp_path):
        argv = [f"tests/{SIBLING_ID}/test_foo.py"]
        with pytest.raises(SiblingTestCollectionError, match="sibling feature subtree"):
            assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)

    def test_non_test_path_is_fine(self, tmp_path):
        argv = ["src/bob/verifier.py"]
        assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)  # no exception

    def test_option_flags_ignored(self, tmp_path):
        argv = ["-v", "--tb=short", f"tests/{FEATURE_ID}"]
        assert_no_sibling_collection(FEATURE_ID, argv, tmp_path)  # no exception

    def test_empty_argv_is_fine(self, tmp_path):
        assert_no_sibling_collection(FEATURE_ID, [], tmp_path)  # no exception


# ---------------------------------------------------------------------------
# Integration: bob.verifier module exports
# ---------------------------------------------------------------------------


class TestVerifierModuleIntegration:
    def test_scope_pytest_to_feature_importable(self):
        from bob.verifier import scope_pytest_to_feature as fn
        assert callable(fn)

    def test_collect_feature_test_paths_importable(self):
        from bob.verifier import collect_feature_test_paths as fn
        assert callable(fn)

    def test_build_scoped_pytest_argv_importable(self):
        from bob.verifier import build_scoped_pytest_argv as fn
        assert callable(fn)

    def test_assert_no_sibling_collection_importable(self):
        from bob.verifier import assert_no_sibling_collection as fn
        assert callable(fn)

    def test_sibling_test_collection_error_importable(self):
        from bob.verifier import SiblingTestCollectionError as exc
        assert issubclass(exc, Exception)

    def test_scope_pytest_does_not_include_whole_suite(self, tmp_path):
        """Key invariant: output never contains bare tests/ or tests."""
        acs = [f"pytest: tests/{FEATURE_ID}/test_smoke.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests" not in result
        assert "tests/" not in result

    def test_scope_pytest_never_includes_sibling_subtree(self, tmp_path):
        """Key invariant: result never contains another feature's UUID path."""
        acs = [f"pytest: tests/{FEATURE_ID}/test_smoke.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        for path in result:
            parts = Path(path).parts
            if len(parts) >= 2 and parts[0] == "tests":
                candidate = parts[1]
                # Any UUID-like second component that isn't our feature_id is a bug
                import re
                uuid_re = re.compile(
                    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    re.IGNORECASE,
                )
                if uuid_re.match(candidate):
                    assert candidate == FEATURE_ID, (
                        f"Result includes sibling feature subtree tests/{candidate}"
                    )

    def test_end_to_end_with_feature_subtree(self, tmp_path):
        """Full round-trip: feature dir exists + pytest: AC → scoped result."""
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        acs = [
            f"pytest: tests/{FEATURE_ID}/test_main.py",
            "File exists: src/bob/verifier.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert f"tests/{FEATURE_ID}/test_main.py" in result
        assert f"tests/{FEATURE_ID}" in result
        # No bare tests/ in result
        assert "tests" not in result
        assert "tests/" not in result
