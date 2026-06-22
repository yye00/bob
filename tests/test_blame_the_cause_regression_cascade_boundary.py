"""Boundary tests for blame_the_cause — empty, zero, and minimum input cases.

Feature 240d49a1-cd13-4bf8-8ef1-f44116681194

Verifies that empty or minimal inputs return well-defined results rather
than raising unexpected exceptions.
"""

from __future__ import annotations

from blame_the_cause import charge_feature, find_owning_feature


class TestFindOwningFeatureBoundary:
    def test_empty_features_list_returns_none(self):
        result = find_owning_feature(
            failing_test="tests/test_a.py::test_one",
            all_features=[],
        )
        assert result is None

    def test_single_feature_no_matching_ac_returns_none(self):
        features = [{"id": "feat-x", "acceptance_criteria": ["File exists: src/foo.py"]}]
        result = find_owning_feature(
            failing_test="tests/test_a.py::test_one",
            all_features=features,
        )
        assert result is None

    def test_feature_with_none_ac_returns_none(self):
        features = [{"id": "feat-x", "acceptance_criteria": None}]
        result = find_owning_feature(
            failing_test="tests/test_a.py::test_one",
            all_features=features,
        )
        assert result is None

    def test_feature_with_empty_ac_list_returns_none(self):
        features = [{"id": "feat-x", "acceptance_criteria": []}]
        result = find_owning_feature(
            failing_test="tests/test_a.py::test_one",
            all_features=features,
        )
        assert result is None

    def test_single_matching_feature_returns_its_id(self):
        features = [{"id": "only-feat", "acceptance_criteria": ["pytest: tests/test_a.py"]}]
        result = find_owning_feature(
            failing_test="tests/test_a.py::test_one",
            all_features=features,
        )
        assert result == "only-feat"


class TestChargeFeatureBoundary:
    def test_empty_failing_tests_returns_zero(self):
        charged = []
        result = charge_feature(
            failing_tests=[],
            all_features=[{"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_a.py"]}],
            increment_fn=charged.append,
        )
        assert result == 0
        assert charged == []

    def test_empty_features_list_returns_zero(self):
        charged = []
        result = charge_feature(
            failing_tests=["tests/test_a.py::test_one"],
            all_features=[],
            increment_fn=charged.append,
        )
        assert result == 0
        assert charged == []

    def test_both_empty_returns_zero(self):
        charged = []
        result = charge_feature(
            failing_tests=[],
            all_features=[],
            increment_fn=charged.append,
        )
        assert result == 0
        assert charged == []

    def test_single_failing_test_single_owner_charges_once(self):
        charged = []
        result = charge_feature(
            failing_tests=["tests/test_a.py::test_one"],
            all_features=[{"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_a.py"]}],
            increment_fn=charged.append,
        )
        assert result == 1
        assert charged == ["feat-a"]

    def test_failing_test_with_no_owner_charges_zero(self):
        charged = []
        result = charge_feature(
            failing_tests=["tests/test_unowned.py::test_x"],
            all_features=[{"id": "feat-a", "acceptance_criteria": ["pytest: tests/test_a.py"]}],
            increment_fn=charged.append,
        )
        assert result == 0
        assert charged == []
