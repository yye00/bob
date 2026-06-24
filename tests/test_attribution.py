"""Tests for bob.test_attribution — regression-vs-baseline ownership attribution.

Feature afdcbc2c-a87f-4ed2-867e-6755b931feaf

Verifies that:
- build_test_to_feature_map builds a correct {test_path: feature_id} map
- attribute_regression_to_owner attributes failures to their true owning feature
  rather than blindly blaming the currently-verifying feature
"""

from __future__ import annotations

import pytest

from bob.test_attribution import (
    attribute_regression_to_owner,
    build_test_to_feature_map,
)


CURRENT_FEATURE = "afdcbc2c-a87f-4ed2-867e-6755b931feaf"
SIBLING_FEATURE = "73879589-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# build_test_to_feature_map
# ---------------------------------------------------------------------------

class TestBuildTestToFeatureMap:
    def test_empty_features_returns_empty_map(self):
        result = build_test_to_feature_map([])
        assert result == {}

    def test_feature_with_pytest_ac_is_mapped(self):
        features = [
            {
                "id": CURRENT_FEATURE,
                "acceptance_criteria": '["pytest: tests/test_foo.py"]',
            }
        ]
        result = build_test_to_feature_map(features)
        assert result["tests/test_foo.py"] == CURRENT_FEATURE

    def test_multiple_features_map_independently(self):
        features = [
            {
                "id": CURRENT_FEATURE,
                "acceptance_criteria": '["pytest: tests/test_current.py"]',
            },
            {
                "id": SIBLING_FEATURE,
                "acceptance_criteria": '["pytest: tests/test_sibling.py"]',
            },
        ]
        result = build_test_to_feature_map(features)
        assert result["tests/test_current.py"] == CURRENT_FEATURE
        assert result["tests/test_sibling.py"] == SIBLING_FEATURE

    def test_non_pytest_acs_are_excluded(self):
        features = [
            {
                "id": CURRENT_FEATURE,
                "acceptance_criteria": (
                    '["File exists: src/bob/foo.py", "pytest: tests/test_foo.py"]'
                ),
            }
        ]
        result = build_test_to_feature_map(features)
        assert "tests/test_foo.py" in result
        assert "File exists: src/bob/foo.py" not in result
        assert len(result) == 1

    def test_feature_with_no_pytest_ac_contributes_nothing(self):
        features = [
            {
                "id": CURRENT_FEATURE,
                "acceptance_criteria": '["File exists: src/bob/foo.py"]',
            }
        ]
        result = build_test_to_feature_map(features)
        assert result == {}

    def test_node_id_path_is_preserved(self):
        features = [
            {
                "id": SIBLING_FEATURE,
                "acceptance_criteria": (
                    '["pytest: tests/test_bar.py::test_specific"]'
                ),
            }
        ]
        result = build_test_to_feature_map(features)
        assert result["tests/test_bar.py::test_specific"] == SIBLING_FEATURE

    def test_workspace_root_kwarg_accepted(self):
        result = build_test_to_feature_map([], workspace_root="/some/path")
        assert result == {}


# ---------------------------------------------------------------------------
# attribute_regression_to_owner
# ---------------------------------------------------------------------------

class TestAttributeRegressionToOwner:
    def test_sibling_feature_test_is_attributed_to_sibling(self):
        """Tests under tests/<sibling_id>/ are attributed to the sibling, not current."""
        test_path = f"tests/{SIBLING_FEATURE}/test_ac_12.py"
        owner = attribute_regression_to_owner(test_path, all_features=[])
        assert owner == SIBLING_FEATURE

    def test_orphan_test_returns_none(self):
        """Tests with no UUID directory component and no pytest-AC owner return None."""
        owner = attribute_regression_to_owner(
            "tests/test_orphan_unknown.py::test_x", all_features=[]
        )
        assert owner is None

    def test_pytest_ac_owner_returned_for_sibling(self):
        """A test claimed by a sibling via pytest: AC is attributed to that sibling."""
        features = [
            {
                "id": SIBLING_FEATURE,
                "acceptance_criteria": (
                    '["pytest: tests/test_contract_grammar_blame.py"]'
                ),
                "status": "completed",
            }
        ]
        owner = attribute_regression_to_owner(
            "tests/test_contract_grammar_blame.py::test_some_case",
            all_features=features,
        )
        assert owner == SIBLING_FEATURE

    def test_returns_none_for_unknown_path_with_features(self):
        """An orphan test returns None even when features list is non-empty."""
        features = [
            {
                "id": SIBLING_FEATURE,
                "acceptance_criteria": '["pytest: tests/test_other.py"]',
                "status": "completed",
            }
        ]
        owner = attribute_regression_to_owner(
            "tests/test_completely_unrelated.py::test_mystery",
            all_features=features,
        )
        assert owner is None

    def test_owner_is_str_or_none(self):
        """Return value is always str (feature_id) or None — never another type."""
        owner = attribute_regression_to_owner(
            f"tests/{SIBLING_FEATURE}/test_x.py", all_features=[]
        )
        assert owner is None or isinstance(owner, str)

    def test_workspace_root_none_does_not_raise(self):
        """workspace_root=None is valid and must not raise."""
        owner = attribute_regression_to_owner(
            "tests/test_foo.py", workspace_root=None, all_features=[]
        )
        assert owner is None or isinstance(owner, str)


# ---------------------------------------------------------------------------
# Integration: both functions are accessible via bob.enhanced_verification
# ---------------------------------------------------------------------------

class TestEnhancedVerificationIntegration:
    def test_build_test_to_feature_map_accessible_via_test_attribution(self):
        """build_test_to_feature_map is importable from bob.test_attribution."""
        from bob.test_attribution import build_test_to_feature_map as fn
        assert callable(fn)

    def test_attribute_regression_to_owner_accessible_via_test_attribution(self):
        """attribute_regression_to_owner is importable from bob.test_attribution."""
        from bob.test_attribution import attribute_regression_to_owner as fn
        assert callable(fn)

    def test_integration_with_verifier_namespace(self):
        """Key functions are re-exported through bob.verification.verifier."""
        from bob.verification import verifier
        assert hasattr(verifier, "attribute_regression_to_owning_feature")
        assert hasattr(verifier, "build_test_to_feature_map")
