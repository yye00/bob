"""Tests: charge_refinement([]) returns 0 charges (empty/zero edge)."""

import pytest
from bob.orchestrator.blame_cascade import charge_refinement, find_owner_feature


def _make_feature(fid: str, pytest_paths: list[str]) -> dict:
    acs = [f"pytest: {p}" for p in pytest_paths]
    return {"id": fid, "acceptance_criteria": acs}


class TestEmptyFailingTests:
    def test_charge_refinement_empty_list_returns_zero(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_alpha.py"])]
        result = charge_refinement(
            failing_tests=[],
            all_features=features,
            increment_fn=charged.append,
        )
        assert result == 0

    def test_charge_refinement_empty_list_calls_no_increment(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_alpha.py"])]
        charge_refinement(
            failing_tests=[],
            all_features=features,
            increment_fn=charged.append,
        )
        assert len(charged) == 0

    def test_charge_refinement_empty_features_returns_zero(self):
        charged = []
        result = charge_refinement(
            failing_tests=["tests/test_foo.py::test_x"],
            all_features=[],
            increment_fn=charged.append,
        )
        assert result == 0

    def test_charge_refinement_both_empty_returns_zero(self):
        charged = []
        result = charge_refinement(
            failing_tests=[],
            all_features=[],
            increment_fn=charged.append,
        )
        assert result == 0

    def test_find_owner_feature_with_empty_features(self):
        owner = find_owner_feature(
            failing_test="tests/test_foo.py::test_x",
            all_features=[],
        )
        assert owner is None

    def test_charge_refinement_no_matching_ac_returns_zero(self):
        """When failing tests have no owning feature, zero charges emitted."""
        charged = []
        features = [_make_feature("feat-a", ["tests/test_alpha.py"])]
        result = charge_refinement(
            failing_tests=["tests/test_totally_unrelated.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert result == 0
        assert charged == []
