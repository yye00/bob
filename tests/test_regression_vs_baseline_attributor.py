"""Tests for bob3.regression_vs_baseline_attributor.

AC: pytest: tests/test_regression_vs_baseline_attributor.py

Feature 69972c5e-bf50-4e8a-a1f9-8740e2e487ff

Tests for the two public entry points:
- build_test_path_to_feature_map
- attribute_failure_to_owning_feature
"""

from __future__ import annotations

import pytest

from bob3.regression_vs_baseline_attributor import (
    attribute_failure_to_owning_feature,
    build_test_path_to_feature_map,
)


# ---------------------------------------------------------------------------
# build_test_path_to_feature_map
# ---------------------------------------------------------------------------

class TestBuildTestPathToFeatureMap:
    def test_empty_features_returns_empty_map(self):
        result = build_test_path_to_feature_map([])
        assert result == {}

    def test_none_features_raises_type_error(self):
        with pytest.raises(TypeError):
            build_test_path_to_feature_map(None)

    def test_feature_with_empty_id_raises_value_error(self):
        with pytest.raises(ValueError):
            build_test_path_to_feature_map([{"id": "", "acceptance_criteria": []}])

    def test_feature_with_pytest_ac_populates_map(self):
        feature_id = "aaaaaaaa-bbbb-cccc-dddd-000000000001"
        features = [
            {
                "id": feature_id,
                "acceptance_criteria": [f"pytest: tests/{feature_id}/test_foo.py"],
            }
        ]
        result = build_test_path_to_feature_map(features)
        assert f"tests/{feature_id}/test_foo.py" in result
        assert result[f"tests/{feature_id}/test_foo.py"] == feature_id

    def test_feature_with_no_pytest_acs_contributes_nothing(self):
        feature_id = "aaaaaaaa-bbbb-cccc-dddd-000000000002"
        features = [
            {
                "id": feature_id,
                "acceptance_criteria": ["File exists: src/bob3/foo.py"],
            }
        ]
        result = build_test_path_to_feature_map(features)
        assert result == {}

    def test_first_writer_wins_for_duplicate_paths(self):
        fid1 = "11111111-1111-1111-1111-111111111111"
        fid2 = "22222222-2222-2222-2222-222222222222"
        shared_path = "tests/test_shared.py"
        features = [
            {"id": fid1, "acceptance_criteria": [f"pytest: {shared_path}"]},
            {"id": fid2, "acceptance_criteria": [f"pytest: {shared_path}"]},
        ]
        result = build_test_path_to_feature_map(features)
        assert result[shared_path] == fid1

    def test_multiple_features_populate_distinct_paths(self):
        fid1 = "aaaaaaaa-bbbb-cccc-dddd-111111111111"
        fid2 = "aaaaaaaa-bbbb-cccc-dddd-222222222222"
        features = [
            {"id": fid1, "acceptance_criteria": ["pytest: tests/test_a.py"]},
            {"id": fid2, "acceptance_criteria": ["pytest: tests/test_b.py"]},
        ]
        result = build_test_path_to_feature_map(features)
        assert result["tests/test_a.py"] == fid1
        assert result["tests/test_b.py"] == fid2

    def test_returns_dict(self):
        result = build_test_path_to_feature_map([])
        assert isinstance(result, dict)

    def test_ac_with_em_dash_annotation_is_still_parsed(self):
        feature_id = "aaaaaaaa-bbbb-cccc-dddd-333333333333"
        features = [
            {
                "id": feature_id,
                "acceptance_criteria": [
                    "pytest: tests/test_x.py — some boundary description"
                ],
            }
        ]
        result = build_test_path_to_feature_map(features)
        assert "tests/test_x.py" in result
        assert result["tests/test_x.py"] == feature_id

    def test_json_string_acceptance_criteria_is_parsed(self):
        feature_id = "aaaaaaaa-bbbb-cccc-dddd-444444444444"
        import json
        features = [
            {
                "id": feature_id,
                "acceptance_criteria": json.dumps(["pytest: tests/test_json.py"]),
            }
        ]
        result = build_test_path_to_feature_map(features)
        assert "tests/test_json.py" in result

    def test_object_style_feature_is_handled(self):
        """Features passed as objects (not dicts) are accepted."""
        feature_id = "aaaaaaaa-bbbb-cccc-dddd-555555555555"

        class FakeFeature:
            id = feature_id
            acceptance_criteria = ["pytest: tests/test_obj.py"]

        result = build_test_path_to_feature_map([FakeFeature()])
        assert "tests/test_obj.py" in result
        assert result["tests/test_obj.py"] == feature_id


# ---------------------------------------------------------------------------
# attribute_failure_to_owning_feature
# ---------------------------------------------------------------------------

class TestAttributeFailureToOwningFeature:
    def test_none_test_path_raises_value_error(self):
        with pytest.raises(ValueError, match="test_path"):
            attribute_failure_to_owning_feature(None)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="test_path"):
            attribute_failure_to_owning_feature("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError, match="test_path"):
            attribute_failure_to_owning_feature("   ")

    def test_uuid_directory_path_returns_feature_id(self):
        feature_id = "73879589-0000-0000-0000-000000000000"
        test_path = f"tests/{feature_id}/test_ac_12.py::test_stub"
        result = attribute_failure_to_owning_feature(test_path)
        assert result == feature_id

    def test_uuid_directory_path_without_node_returns_feature_id(self):
        feature_id = "73879589-0000-0000-0000-000000000000"
        test_path = f"tests/{feature_id}/test_ac_12.py"
        result = attribute_failure_to_owning_feature(test_path)
        assert result == feature_id

    def test_non_uuid_path_without_features_returns_none(self):
        result = attribute_failure_to_owning_feature(
            "tests/test_contract_grammar_emits_runnable_decorators.py"
        )
        assert result is None

    def test_pytest_ac_match_returns_feature_id(self):
        feature_id = "aaaaaaaa-bbbb-cccc-dddd-666666666666"
        features = [
            {
                "id": feature_id,
                "acceptance_criteria": [
                    "pytest: tests/test_contract_grammar_emits_runnable_decorators.py"
                ],
            }
        ]
        result = attribute_failure_to_owning_feature(
            "tests/test_contract_grammar_emits_runnable_decorators.py",
            all_features=features,
        )
        assert result == feature_id

    def test_sibling_feature_does_not_match_unrelated_test(self):
        sibling_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        features = [
            {
                "id": sibling_id,
                "acceptance_criteria": ["pytest: tests/test_sibling.py"],
            }
        ]
        result = attribute_failure_to_owning_feature(
            "tests/test_completely_different.py",
            all_features=features,
        )
        assert result is None

    def test_all_features_none_does_not_raise(self):
        result = attribute_failure_to_owning_feature(
            "tests/test_orphan.py",
            all_features=None,
        )
        assert result is None

    def test_workspace_root_none_does_not_raise(self):
        result = attribute_failure_to_owning_feature(
            "tests/test_orphan.py",
            workspace_root=None,
        )
        assert result is None

    def test_return_type_is_str_for_owned_test(self):
        feature_id = "12345678-abcd-ef01-2345-6789abcdef01"
        result = attribute_failure_to_owning_feature(
            f"tests/{feature_id}/test_x.py"
        )
        assert isinstance(result, str)

    def test_return_type_is_none_for_orphan(self):
        result = attribute_failure_to_owning_feature("tests/test_orphan.py")
        assert result is None

    def test_9b2e1060_scenario_sibling_tests_are_not_attributed_to_current(self):
        """Regression scenario: 7 sibling tests must NOT block the current feature.

        The AC description describes feature 9b2e1060 being wrongly NH-demoted
        because 7 tests from sibling feature 73879589 were counted against it.
        Those tests should be attributed to 73879589, not to 9b2e1060.
        """
        # Tests that belong to sibling 73879589
        sibling_paths = [
            "tests/73879589/test_ac_12_pytest_tests_test_contract_grammar_blame.py",
        ]
        current_feature_id = "9b2e1060-0000-0000-0000-000000000000"

        for path in sibling_paths:
            owner = attribute_failure_to_owning_feature(path)
            # Owner should be the 73879589 feature, NOT the current feature
            assert owner != current_feature_id, (
                f"Test {path!r} was wrongly attributed to current feature {current_feature_id}"
            )
            # It should be attributed to the 73879589 sibling
            assert owner is not None and owner.startswith("73879589"), (
                f"Expected sibling 73879589* owner, got {owner!r}"
            )

    def test_node_id_matching_for_pytest_ac(self):
        """File-level pytest: AC matches node-id variants of that file."""
        feature_id = "aaaaaaaa-bbbb-cccc-dddd-777777777777"
        features = [
            {
                "id": feature_id,
                "acceptance_criteria": ["pytest: tests/test_something.py"],
            }
        ]
        result = attribute_failure_to_owning_feature(
            "tests/test_something.py::test_specific_case",
            all_features=features,
        )
        assert result == feature_id
