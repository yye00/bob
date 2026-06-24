"""Tests for bob.verifier.scope_pytest_to_feature.

Verifies that the verifier's tests_pass step scopes pytest to ONLY the
current feature's own tests — never the whole tests/ tree or sibling
feature subtrees. This closes the bug where cumulative prior-feature
broken tests caused pytest-xdist --maxfail=20 to abort every subsequent
feature's verification run before its own tests executed.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from bob.verifier import scope_pytest_to_feature
from bob.verification.per_feature_test_scope import SiblingTestCollectionError

FEATURE_ID = "503c2006-a76c-4b43-978d-fb0f3d8b4a0e"
SIBLING_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestScopePytestToFeature:
    """Core behaviour of scope_pytest_to_feature (the primary verifier entry point)."""

    def test_returns_sorted_list(self, tmp_path):
        acs = [
            "pytest: tests/test_z.py",
            "pytest: tests/test_a.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result == sorted(result)

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

    def test_node_id_suffix_stripped_from_pytest_ac(self, tmp_path):
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

    def test_pytest_ac_and_feature_subtree_combined(self, tmp_path):
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        acs = ["pytest: tests/test_extra.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_extra.py" in result
        assert f"tests/{FEATURE_ID}" in result

    def test_pytest_ac_case_insensitive(self, tmp_path):
        acs = ["PYTEST: tests/test_upper.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests/test_upper.py" in result

    def test_never_includes_bare_tests_tree(self, tmp_path):
        acs = ["pytest: tests/test_foo.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert "tests" not in result
        assert "tests/" not in result

    def test_deduplicates_duplicate_pytest_acs(self, tmp_path):
        acs = [
            "pytest: tests/test_same.py",
            "pytest: tests/test_same.py",
        ]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        assert result.count("tests/test_same.py") == 1

    def test_workspace_as_string_accepted(self, tmp_path):
        acs = ["pytest: tests/test_foo.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, str(tmp_path))
        assert "tests/test_foo.py" in result

    def test_workspace_as_path_accepted(self, tmp_path):
        acs = ["pytest: tests/test_foo.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, Path(tmp_path))
        assert "tests/test_foo.py" in result


class TestScopePytestSiblingIsolation:
    """Validates that sibling feature subtrees are never included.

    The root bug: 20+ cumulative failing tests from prior features would trip
    pytest-xdist's --maxfail=20 before the current feature's tests executed.
    scope_pytest_to_feature must exclude every sibling subtree.
    """

    def _make_sibling_workspace(self, tmp_path: Path, n_siblings: int = 20) -> Path:
        """Create a workspace with n_siblings failing subtrees and one green feature."""
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        (feature_dir / "test_green.py").write_text(textwrap.dedent("""\
            def test_passes():
                assert 1 + 1 == 2
        """))

        for i in range(n_siblings):
            sid = f"{i:08x}-1111-1111-1111-111111111111"
            sibling_dir = tmp_path / "tests" / sid
            sibling_dir.mkdir(parents=True)
            (sibling_dir / "test_fail.py").write_text(textwrap.dedent("""\
                import pytest
                def test_always_fails():
                    pytest.fail("stub not implemented")
            """))
        return tmp_path

    def test_scoped_result_excludes_all_sibling_subtrees(self, tmp_path):
        ws = self._make_sibling_workspace(tmp_path, n_siblings=20)
        result = scope_pytest_to_feature(FEATURE_ID, [], ws)

        for token in result:
            parts = Path(token).parts
            if len(parts) >= 2 and parts[0] == "tests":
                candidate = parts[1]
                # Any UUID-like path segment that is NOT our feature_id is a sibling
                import re
                _UUID_RE = re.compile(
                    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    re.IGNORECASE,
                )
                if _UUID_RE.match(candidate):
                    assert candidate == FEATURE_ID, (
                        f"sibling subtree {candidate} leaked into scoped pytest paths: {result}"
                    )

    def test_scoped_result_includes_own_subtree(self, tmp_path):
        ws = self._make_sibling_workspace(tmp_path, n_siblings=5)
        result = scope_pytest_to_feature(FEATURE_ID, [], ws)
        assert f"tests/{FEATURE_ID}" in result

    def test_sibling_ac_path_does_not_appear_in_result(self, tmp_path):
        # Even if someone mistakenly puts a sibling path in a pytest AC,
        # assert_no_sibling_collection should raise SiblingTestCollectionError.
        acs = [f"pytest: tests/{SIBLING_ID}/test_sibling.py"]
        with pytest.raises(SiblingTestCollectionError):
            scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)

    def test_no_bare_tests_tree_leaked(self, tmp_path):
        ws = self._make_sibling_workspace(tmp_path, n_siblings=3)
        result = scope_pytest_to_feature(FEATURE_ID, [], ws)
        # "tests" alone (bare) must never appear
        assert "tests" not in result


class TestScopePytestIntegration:
    """Verifies import from bob.verifier (the declared integration surface)."""

    def test_importable_from_bob_verifier(self):
        from bob.verifier import scope_pytest_to_feature as fn  # noqa: F401
        assert callable(fn)

    def test_is_same_object_as_verification_module(self):
        from bob.verifier import scope_pytest_to_feature as via_verifier
        from bob.verification.per_feature_test_scope import (
            scope_pytest_to_feature as via_verification,
        )
        assert via_verifier is via_verification

    def test_result_is_list(self, tmp_path):
        result = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
        assert isinstance(result, list)

    def test_result_elements_are_strings(self, tmp_path):
        acs = ["pytest: tests/test_foo.py"]
        result = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
        for item in result:
            assert isinstance(item, str)
