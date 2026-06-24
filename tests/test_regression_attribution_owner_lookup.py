"""Tests for owning_feature_for_test — directory-based and AC-based ownership.

AC-10: asserts test under tests/<feature_id>/ resolves to feature_id
AC-11: asserts top-level test with no owner resolves to None (orphan boundary)
"""
from __future__ import annotations

import pytest

from bob3.verification.regression_attribution import owning_feature_for_test

FEATURE_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
FEATURE_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class TestOwnerLookupDirectoryConvention:
    """Directory-based ownership: tests/<feature_id>/ subtree."""

    def test_test_under_feature_subdir_resolves_to_feature_id(self):
        path = f"tests/{FEATURE_A}/test_something.py::test_foo"
        result = owning_feature_for_test(path)
        assert result == FEATURE_A

    def test_test_file_only_no_node_id(self):
        path = f"tests/{FEATURE_A}/test_bar.py"
        result = owning_feature_for_test(path)
        assert result == FEATURE_A

    def test_nested_path_under_feature_subdir(self):
        path = f"tests/{FEATURE_B}/subdir/test_nested.py::test_case"
        result = owning_feature_for_test(path)
        assert result == FEATURE_B

    def test_different_feature_id_returns_correct_owner(self):
        path = f"tests/{FEATURE_B}/test_x.py"
        result = owning_feature_for_test(path)
        assert result == FEATURE_B
        assert result != FEATURE_A


class TestOwnerLookupOrphanBoundary:
    """Orphan boundary: tests NOT under any feature subtree resolve to None."""

    def test_top_level_test_no_owner_returns_none(self):
        result = owning_feature_for_test("tests/test_contract_grammar.py::test_bar")
        assert result is None

    def test_top_level_test_file_no_owner(self):
        result = owning_feature_for_test("tests/test_some_integration.py")
        assert result is None

    def test_empty_path_returns_none(self):
        result = owning_feature_for_test("")
        assert result is None

    def test_non_uuid_directory_returns_none(self):
        result = owning_feature_for_test("tests/helpers/test_utils.py")
        assert result is None

    def test_none_all_features_does_not_raise(self):
        result = owning_feature_for_test("tests/test_top_level.py", all_features=None)
        assert result is None


class TestOwnerLookupViaACs:
    """pytest-prefix AC strategy: features with pytest: ACs claim test paths."""

    def test_feature_with_pytest_ac_claims_exact_test(self):
        features = [
            {
                "id": FEATURE_A,
                "acceptance_criteria": f'["pytest: tests/test_feature_a.py::test_foo"]',
            }
        ]
        result = owning_feature_for_test(
            "tests/test_feature_a.py::test_foo",
            all_features=features,
        )
        assert result == FEATURE_A

    def test_feature_with_file_level_pytest_ac_claims_any_test_in_file(self):
        features = [
            {
                "id": FEATURE_B,
                "acceptance_criteria": f'["pytest: tests/test_feature_b.py"]',
            }
        ]
        result = owning_feature_for_test(
            "tests/test_feature_b.py::test_something",
            all_features=features,
        )
        assert result == FEATURE_B

    def test_no_matching_ac_returns_none(self):
        features = [
            {
                "id": FEATURE_A,
                "acceptance_criteria": '["pytest: tests/test_other.py"]',
            }
        ]
        result = owning_feature_for_test(
            "tests/test_unrelated.py::test_x",
            all_features=features,
        )
        assert result is None

    def test_directory_ownership_takes_precedence_over_ac(self):
        """Directory convention wins even when an AC also claims the path."""
        features = [
            {
                "id": FEATURE_B,
                "acceptance_criteria": f'["pytest: tests/{FEATURE_A}/test_foo.py"]',
            }
        ]
        result = owning_feature_for_test(
            f"tests/{FEATURE_A}/test_foo.py::test_bar",
            all_features=features,
        )
        assert result == FEATURE_A
