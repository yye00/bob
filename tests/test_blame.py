"""Tests for bob.blame — charge_breaking_feature.

Feature d55f745b-2ca5-443b-bfd0-5c9f9d33b0fb

Verifies that:
- charge_breaking_feature charges the owning feature for each failing test
- Innocent features (no failing tests) are not charged
- Each unique owner is charged exactly once
- Invalid input raises ValueError
"""

from __future__ import annotations

import pytest
from bob.blame import charge_breaking_feature, OrphanTestError


def _make_feature(fid: str, pytest_paths: list[str], status: str = "executing") -> dict:
    acs = [f"pytest: {p}" for p in pytest_paths]
    return {"id": fid, "acceptance_criteria": acs, "status": status}


class TestChargeBreakingFeature:
    def test_charges_owning_feature(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        count = charge_breaking_feature(
            failing_tests=["tests/test_a.py::test_one"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert charged == ["feat-a"]
        assert count == 1

    def test_does_not_charge_innocent_feature(self):
        charged = []
        features = [
            _make_feature("guilty", ["tests/test_guilty.py"]),
            _make_feature("innocent", ["tests/test_innocent.py"]),
        ]
        charge_breaking_feature(
            failing_tests=["tests/test_guilty.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert "innocent" not in charged
        assert "guilty" in charged

    def test_charges_each_unique_owner_once(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        count = charge_breaking_feature(
            failing_tests=[
                "tests/test_a.py::test_one",
                "tests/test_a.py::test_two",
                "tests/test_a.py::test_three",
            ],
            all_features=features,
            increment_fn=charged.append,
        )
        assert charged.count("feat-a") == 1
        assert count == 1

    def test_empty_failing_tests_returns_zero(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        count = charge_breaking_feature(
            failing_tests=[],
            all_features=features,
            increment_fn=charged.append,
        )
        assert charged == []
        assert count == 0

    def test_charges_multiple_distinct_owners(self):
        charged = []
        features = [
            _make_feature("feat-a", ["tests/test_a.py"]),
            _make_feature("feat-b", ["tests/test_b.py"]),
        ]
        count = charge_breaking_feature(
            failing_tests=[
                "tests/test_a.py::test_one",
                "tests/test_b.py::test_two",
            ],
            all_features=features,
            increment_fn=charged.append,
        )
        assert set(charged) == {"feat-a", "feat-b"}
        assert count == 2

    def test_invalid_failing_tests_type_raises_value_error(self):
        with pytest.raises(ValueError):
            charge_breaking_feature(
                failing_tests="not-a-list",
                all_features=[],
                increment_fn=lambda x: None,
            )

    def test_unowned_test_calls_unowned_record_fn(self):
        orphans = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        charge_breaking_feature(
            failing_tests=["tests/test_unowned.py::test_x"],
            all_features=features,
            increment_fn=lambda x: None,
            unowned_record_fn=orphans.append,
        )
        assert len(orphans) == 1
        assert orphans[0]["type"] == "unattributed_failure"

    def test_empty_features_returns_zero(self):
        charged = []
        count = charge_breaking_feature(
            failing_tests=["tests/test_a.py::test_one"],
            all_features=[],
            increment_fn=charged.append,
        )
        assert count == 0
        assert charged == []

    def test_module_exposes_orphan_test_error(self):
        assert OrphanTestError is not None

    def test_unowned_failing_test_charges_zero(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        count = charge_breaking_feature(
            failing_tests=["tests/test_unowned.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert count == 0
        assert charged == []
