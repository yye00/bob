"""Tests for blame_the_cause — charge_feature and find_owning_feature.

Feature 240d49a1-cd13-4bf8-8ef1-f44116681194

Verifies that:
- ``find_owning_feature`` returns the correct feature_id for a failing test
- ``charge_feature`` charges only the feature that owns the failing test
- Innocent features (no failing tests) are not charged
"""

from __future__ import annotations

import pytest
from blame_the_cause import (
    charge_feature,
    find_owning_feature,
    OrphanTestError,
    preserve_innocent_status,
)


def _make_feature(fid: str, pytest_paths: list[str], status: str = "executing") -> dict:
    acs = [f"pytest: {p}" for p in pytest_paths]
    return {"id": fid, "acceptance_criteria": acs, "status": status}


class TestFindOwningFeature:
    def test_finds_owner_by_file_prefix(self):
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        owner = find_owning_feature(
            failing_test="tests/test_a.py::test_one",
            all_features=features,
        )
        assert owner == "feat-a"

    def test_finds_second_feature_owner(self):
        features = [
            _make_feature("feat-a", ["tests/test_a.py"]),
            _make_feature("feat-b", ["tests/test_b.py"]),
        ]
        owner = find_owning_feature(
            failing_test="tests/test_b.py::test_x",
            all_features=features,
        )
        assert owner == "feat-b"

    def test_returns_none_when_no_owner(self):
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        owner = find_owning_feature(
            failing_test="tests/test_unowned.py::test_x",
            all_features=features,
        )
        assert owner is None

    def test_strict_raises_orphan_error_when_no_owner(self):
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        with pytest.raises(OrphanTestError):
            find_owning_feature(
                failing_test="tests/test_unowned.py::test_x",
                all_features=features,
                strict=True,
            )

    def test_exact_nodeid_match(self):
        features = [_make_feature("feat-x", ["tests/test_x.py::test_exact"])]
        owner = find_owning_feature(
            failing_test="tests/test_x.py::test_exact",
            all_features=features,
        )
        assert owner == "feat-x"

    def test_exact_nodeid_does_not_match_other_test_same_file(self):
        features = [_make_feature("feat-x", ["tests/test_x.py::test_exact"])]
        owner = find_owning_feature(
            failing_test="tests/test_x.py::test_other",
            all_features=features,
        )
        assert owner is None

    def test_empty_features_list_returns_none(self):
        owner = find_owning_feature(
            failing_test="tests/test_a.py::test_one",
            all_features=[],
        )
        assert owner is None

    def test_invalid_failing_test_raises_value_error(self):
        with pytest.raises(ValueError):
            find_owning_feature(
                failing_test="",
                all_features=[],
            )


class TestChargeFeature:
    def test_charges_owning_feature(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        count = charge_feature(
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
        charge_feature(
            failing_tests=["tests/test_guilty.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert "innocent" not in charged
        assert "guilty" in charged

    def test_charges_each_unique_owner_once(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        count = charge_feature(
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
        count = charge_feature(
            failing_tests=[],
            all_features=features,
            increment_fn=charged.append,
        )
        assert charged == []
        assert count == 0

    def test_calls_unowned_record_fn_for_orphan(self):
        orphans = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        charge_feature(
            failing_tests=["tests/test_unowned.py::test_x"],
            all_features=features,
            increment_fn=lambda x: None,
            unowned_record_fn=orphans.append,
        )
        assert len(orphans) == 1
        assert orphans[0]["type"] == "unattributed_failure"

    def test_charges_multiple_distinct_owners(self):
        charged = []
        features = [
            _make_feature("feat-a", ["tests/test_a.py"]),
            _make_feature("feat-b", ["tests/test_b.py"]),
        ]
        count = charge_feature(
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
            charge_feature(
                failing_tests="not-a-list",
                all_features=[],
                increment_fn=lambda x: None,
            )


class TestPreserveInnocentStatus:
    def test_preserves_non_charged_features(self):
        features = [
            _make_feature("feat-a", ["tests/test_a.py"], status="executing"),
            _make_feature("feat-b", ["tests/test_b.py"], status="ready"),
        ]
        preserved = preserve_innocent_status(
            all_features=features,
            charged_feature_ids={"feat-a"},
        )
        assert "feat-b" in preserved
        assert preserved["feat-b"] == "ready"
        assert "feat-a" not in preserved

    def test_all_innocent_when_none_charged(self):
        features = [
            _make_feature("feat-a", ["tests/test_a.py"]),
            _make_feature("feat-b", ["tests/test_b.py"]),
        ]
        preserved = preserve_innocent_status(
            all_features=features,
            charged_feature_ids=set(),
        )
        assert set(preserved.keys()) == {"feat-a", "feat-b"}
