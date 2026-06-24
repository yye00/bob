"""Tests for bob.verifier.scope_pytest_to_feature_subtree and related API.

AC-0: pytest: tests/verifier_scope_pytest_to_feature.py
AC-1: Function defined: bob.verifier.scope_pytest_to_feature_subtree
AC-2: integration: bob.verifier
AC-3: behavior — empty/zero input returns well-defined result, not a crash
AC-4: behavior — invalid input raises ValueError or rejection, no silent success
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.verifier import (
    SiblingTestCollectionError,
    scope_pytest_to_feature,
    scope_pytest_to_feature_subtree,
)


FEATURE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SIBLING_ID = "11111111-2222-3333-4444-555555555555"


class TestFunctionDefined:
    """AC-1: Function defined: bob.verifier.scope_pytest_to_feature_subtree"""

    def test_function_is_callable(self):
        assert callable(scope_pytest_to_feature_subtree)

    def test_function_is_importable_from_bob_verifier(self):
        import bob.verifier as m
        assert hasattr(m, "scope_pytest_to_feature_subtree")
        assert callable(m.scope_pytest_to_feature_subtree)

    def test_alias_is_same_as_scope_pytest_to_feature(self):
        assert scope_pytest_to_feature_subtree is scope_pytest_to_feature


class TestIntegrationBobVerifier:
    """AC-2: integration: bob.verifier"""

    def test_bob_verifier_exposes_scope_pytest_to_feature_subtree(self):
        import bob.verifier
        assert "scope_pytest_to_feature_subtree" in dir(bob.verifier)

    def test_scope_pytest_to_feature_subtree_returns_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scope_pytest_to_feature_subtree(FEATURE_ID, [], tmp)
        assert isinstance(result, list)

    def test_scope_pytest_to_feature_subtree_with_pytest_ac(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = [f"pytest: tests/{FEATURE_ID}/test_foo.py"]
            result = scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)
        assert f"tests/{FEATURE_ID}/test_foo.py" in result

    def test_scope_pytest_to_feature_subtree_with_feature_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            feature_dir = Path(tmp) / "tests" / FEATURE_ID
            feature_dir.mkdir(parents=True)
            result = scope_pytest_to_feature_subtree(FEATURE_ID, [], tmp)
        assert f"tests/{FEATURE_ID}" in result

    def test_scope_pytest_to_feature_subtree_result_is_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = [
                f"pytest: tests/{FEATURE_ID}/test_z.py",
                f"pytest: tests/{FEATURE_ID}/test_a.py",
            ]
            result = scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)
        assert result == sorted(result)

    def test_does_not_include_bare_tests_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scope_pytest_to_feature_subtree(FEATURE_ID, [], tmp)
        assert "tests" not in result
        assert "tests/" not in result

    def test_does_not_include_sibling_feature_subtree(self):
        with tempfile.TemporaryDirectory() as tmp:
            # sibling AC must not appear in current feature's paths
            acs = [f"pytest: tests/{SIBLING_ID}/test_bar.py"]
            with pytest.raises(SiblingTestCollectionError):
                scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)


class TestBehaviorEmptyInput:
    """AC-3: boundary case — empty or zero input returns well-defined result, not a crash."""

    def test_empty_acs_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scope_pytest_to_feature_subtree(FEATURE_ID, [], tmp)
        assert result == []

    def test_none_like_empty_string_ac_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = ["", "   ", "some non-pytest ac"]
            result = scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)
        assert result == []

    def test_zero_pytest_acs_no_feature_dir_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scope_pytest_to_feature_subtree(FEATURE_ID, ["File exists: foo.py"], tmp)
        assert result == []

    def test_does_not_crash_on_empty_feature_id_when_no_acs(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Empty feature_id: no feature dir will match, empty acs → empty result
            result = scope_pytest_to_feature_subtree("", [], tmp)
        assert isinstance(result, list)

    def test_returns_list_not_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scope_pytest_to_feature_subtree(FEATURE_ID, [], tmp)
        assert result is not None


class TestBehaviorInvalidInput:
    """AC-4: invalid input raises ValueError or rejection; no silent success."""

    def test_sibling_pytest_ac_raises_sibling_collection_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = [f"pytest: tests/{SIBLING_ID}/test_x.py"]
            with pytest.raises(SiblingTestCollectionError):
                scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)

    def test_bare_tests_path_in_ac_raises_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = ["pytest: tests/"]
            with pytest.raises(SiblingTestCollectionError):
                scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)

    def test_bare_tests_without_slash_raises_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = ["pytest: tests"]
            with pytest.raises(SiblingTestCollectionError):
                scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)

    def test_sibling_collection_error_message_contains_feature_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            acs = [f"pytest: tests/{SIBLING_ID}/test_x.py"]
            with pytest.raises(SiblingTestCollectionError, match=SIBLING_ID):
                scope_pytest_to_feature_subtree(FEATURE_ID, acs, tmp)
