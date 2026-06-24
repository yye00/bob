"""Tests for bob3.verification.charge_feature_from_test.

Feature 3310e08a-0932-4664-a7b2-b93bb01d88e5

Verifies that charge_feature_from_test is importable from bob3.verification
and behaves correctly: charges only the feature whose pytest: AC owns the
failing test, leaves innocent features untouched.
"""

from __future__ import annotations

import pytest
from bob3.verification.blame_feature_charger import charge_feature_from_test


class TestChargeFeatureFromTestImport:
    def test_importable_from_bob3_verification(self):
        from bob3.verification import charge_feature_from_test as cft  # noqa: F401
        assert cft is not None

    def test_importable_from_blame_feature_charger(self):
        from bob3.verification.blame_feature_charger import charge_feature_from_test as cft
        assert callable(cft)

    def test_function_has_expected_name(self):
        assert charge_feature_from_test.__name__ == "charge_feature_from_test"


class TestChargeFeatureFromTestBehavior:
    def test_charges_owning_feature(self):
        charged = []
        features = [
            {"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_foo.py"]},
        ]
        result = charge_feature_from_test(
            failing_test="tests/test_foo.py::test_bar",
            all_features=features,
            increment_fn=charged.append,
        )
        assert result == "feat-a"
        assert charged == ["feat-a"]

    def test_does_not_charge_innocent_feature(self):
        charged = []
        features = [
            {"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_foo.py"]},
            {"id": "feat-b", "acceptance_criteria": ["pytest: tests/test_bar.py"]},
        ]
        result = charge_feature_from_test(
            failing_test="tests/test_foo.py::test_case",
            all_features=features,
            increment_fn=charged.append,
        )
        assert result == "feat-a"
        assert "feat-b" not in charged

    def test_returns_none_for_unowned_test(self):
        charged = []
        features = [
            {"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_foo.py"]},
        ]
        result = charge_feature_from_test(
            failing_test="tests/test_unowned.py::test_something",
            all_features=features,
            increment_fn=charged.append,
        )
        assert result is None
        assert charged == []

    def test_calls_unowned_record_fn_when_no_owner(self):
        orphans = []
        features = [
            {"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_foo.py"]},
        ]
        charge_feature_from_test(
            failing_test="tests/test_orphan.py::test_x",
            all_features=features,
            increment_fn=lambda x: None,
            unowned_record_fn=orphans.append,
        )
        assert len(orphans) == 1
        assert orphans[0]["type"] == "unattributed_failure"

    def test_empty_features_list_returns_none(self):
        result = charge_feature_from_test(
            failing_test="tests/test_foo.py::test_bar",
            all_features=[],
            increment_fn=lambda x: None,
        )
        assert result is None

    def test_raises_value_error_for_empty_failing_test(self):
        with pytest.raises(ValueError):
            charge_feature_from_test(
                failing_test="",
                all_features=[],
                increment_fn=lambda x: None,
            )

    def test_raises_value_error_for_whitespace_failing_test(self):
        with pytest.raises(ValueError):
            charge_feature_from_test(
                failing_test="   ",
                all_features=[],
                increment_fn=lambda x: None,
            )

    def test_increment_fn_called_exactly_once(self):
        call_count = []
        features = [
            {"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_foo.py"]},
        ]
        charge_feature_from_test(
            failing_test="tests/test_foo.py::test_bar",
            all_features=features,
            increment_fn=lambda fid: call_count.append(fid),
        )
        assert len(call_count) == 1
        assert call_count[0] == "feat-a"

    def test_object_feature_with_attributes(self):
        """Features can be objects with .id and .acceptance_criteria attributes."""
        class Feature:
            def __init__(self, fid, acs):
                self.id = fid
                self.acceptance_criteria = acs

        charged = []
        features = [Feature("feat-obj", ["pytest: tests/test_obj.py"])]
        result = charge_feature_from_test(
            failing_test="tests/test_obj.py::test_one",
            all_features=features,
            increment_fn=charged.append,
        )
        assert result == "feat-obj"
        assert charged == ["feat-obj"]

    def test_exact_nodeid_match(self):
        charged = []
        features = [
            {
                "id": "feat-exact",
                "acceptance_criteria": ["pytest: tests/test_exact.py::test_specific"],
            }
        ]
        result = charge_feature_from_test(
            failing_test="tests/test_exact.py::test_specific",
            all_features=features,
            increment_fn=charged.append,
        )
        assert result == "feat-exact"
        assert charged == ["feat-exact"]

    def test_exact_nodeid_does_not_match_different_test(self):
        charged = []
        features = [
            {
                "id": "feat-exact",
                "acceptance_criteria": ["pytest: tests/test_exact.py::test_specific"],
            }
        ]
        result = charge_feature_from_test(
            failing_test="tests/test_exact.py::test_other",
            all_features=features,
            increment_fn=charged.append,
        )
        assert result is None
        assert charged == []
