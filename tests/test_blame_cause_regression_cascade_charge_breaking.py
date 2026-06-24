"""Tests for blame_cause_regression_cascade_charge_breaking.

Feature 258d8dc4-ec52-4360-88fc-0e5f02708693

Verifies that blame_cause_regression_cascade_charge_breaking correctly walks
the AC table, charges only the breaking feature, and leaves innocent features
at their pre-verification status.
"""

from __future__ import annotations

import pytest
from bob3.blame_cause_regression_cascade_charge_breaking import (
    blame_cause_regression_cascade_charge_breaking,
)


def _make_feature(fid: str, pytest_paths: list[str], status: str = "executing") -> dict:
    acs = [f"pytest: {p}" for p in pytest_paths]
    return {"id": fid, "acceptance_criteria": acs, "status": status}


def test_blame_cause_regression_cascade_charge_breaking():
    """Canonical AC test: owner charged, innocent feature untouched."""
    charged = []
    features = [
        _make_feature("breaking", ["tests/test_breaking.py"]),
        _make_feature("innocent", ["tests/test_innocent.py"]),
    ]
    result = blame_cause_regression_cascade_charge_breaking(
        failing_tests=["tests/test_breaking.py::test_one"],
        all_features=features,
        increment_fn=charged.append,
    )
    assert "breaking" in charged
    assert "innocent" not in charged
    assert result == 1


class TestBlameCauseRegressionCascadeChargeBreaking:
    def test_charges_owner_of_failing_test(self):
        charged = []
        features = [
            _make_feature("feat-a", ["tests/test_a.py"]),
            _make_feature("feat-b", ["tests/test_b.py"]),
        ]
        result = blame_cause_regression_cascade_charge_breaking(
            failing_tests=["tests/test_a.py::test_one"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert "feat-a" in charged
        assert "feat-b" not in charged

    def test_innocent_feature_not_charged(self):
        charged = []
        features = [
            _make_feature("guilty", ["tests/test_guilty.py"]),
            _make_feature("innocent", ["tests/test_innocent.py"]),
        ]
        blame_cause_regression_cascade_charge_breaking(
            failing_tests=["tests/test_guilty.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert "innocent" not in charged
        assert "guilty" in charged

    def test_charges_each_unique_owner_once(self):
        charged = []
        features = [
            _make_feature("feat-a", ["tests/test_a.py"]),
            _make_feature("feat-b", ["tests/test_b.py"]),
        ]
        result = blame_cause_regression_cascade_charge_breaking(
            failing_tests=[
                "tests/test_a.py::test_one",
                "tests/test_a.py::test_two",
                "tests/test_b.py::test_one",
            ],
            all_features=features,
            increment_fn=charged.append,
        )
        assert sorted(charged) == ["feat-a", "feat-b"]
        assert result == 2

    def test_does_not_charge_same_feature_multiple_times(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        blame_cause_regression_cascade_charge_breaking(
            failing_tests=[
                "tests/test_a.py::test_one",
                "tests/test_a.py::test_two",
                "tests/test_a.py::test_three",
            ],
            all_features=features,
            increment_fn=charged.append,
        )
        assert charged.count("feat-a") == 1

    def test_empty_failing_tests_returns_zero(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        result = blame_cause_regression_cascade_charge_breaking(
            failing_tests=[],
            all_features=features,
            increment_fn=charged.append,
        )
        assert result == 0
        assert charged == []

    def test_no_ac_match_returns_zero(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        result = blame_cause_regression_cascade_charge_breaking(
            failing_tests=["tests/test_unrelated.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert result == 0
        assert charged == []

    def test_preserve_innocent_statuses(self):
        charged = []
        features = [
            _make_feature("breaking", ["tests/test_breaking.py"], status="executing"),
            _make_feature("bystander", ["tests/test_bystander.py"], status="completed"),
        ]
        blame_cause_regression_cascade_charge_breaking(
            failing_tests=["tests/test_breaking.py::test_something"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert "breaking" in charged
        assert "bystander" not in charged

    def test_multiple_features_multiple_failing_tests(self):
        charged = []
        features = [
            _make_feature("feat-x", ["tests/test_x.py"]),
            _make_feature("feat-y", ["tests/test_y.py"]),
            _make_feature("feat-z", ["tests/test_z.py"]),
        ]
        result = blame_cause_regression_cascade_charge_breaking(
            failing_tests=[
                "tests/test_x.py::test_1",
                "tests/test_z.py::test_1",
            ],
            all_features=features,
            increment_fn=charged.append,
        )
        assert sorted(charged) == ["feat-x", "feat-z"]
        assert "feat-y" not in charged
        assert result == 2

    def test_json_serialized_ac_list(self):
        """AC list may be a JSON-serialized string instead of a Python list."""
        import json
        charged = []
        features = [
            {
                "id": "feat-json",
                "acceptance_criteria": json.dumps(["pytest: tests/test_json.py"]),
                "status": "executing",
            }
        ]
        result = blame_cause_regression_cascade_charge_breaking(
            failing_tests=["tests/test_json.py::test_one"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert charged == ["feat-json"]
        assert result == 1
