"""Tests for blame_cascade.charge_feature_for_failures.

Feature 56ca0fd2-72e1-4399-afa3-d636f58b065f

Verifies that the public facade correctly delegates to the orchestrator
blame_cascade sub-module, charging only the feature whose pytest: AC owns the
failing test and leaving innocent features untouched.
"""

from __future__ import annotations

import pytest
from blame_cascade import (
    charge_feature_for_failures,
    find_owner_feature,
    preserve_innocent_status,
    handle_unowned_failure,
    OrphanTestError,
)


def _make_feature(fid: str, pytest_paths: list[str], status: str = "executing") -> dict:
    acs = [f"pytest: {p}" for p in pytest_paths]
    return {"id": fid, "acceptance_criteria": acs, "status": status}


class TestChargeFeatureForFailures:
    def test_charges_owning_feature(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        result = charge_feature_for_failures(
            failing_tests=["tests/test_a.py::test_one"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert charged == ["feat-a"]
        assert result == 1

    def test_innocent_feature_not_charged(self):
        charged = []
        features = [
            _make_feature("guilty", ["tests/test_guilty.py"]),
            _make_feature("innocent", ["tests/test_innocent.py"]),
        ]
        charge_feature_for_failures(
            failing_tests=["tests/test_guilty.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert "innocent" not in charged
        assert charged == ["guilty"]

    def test_charges_each_unique_owner_once(self):
        charged = []
        features = [
            _make_feature("feat-a", ["tests/test_a.py"]),
            _make_feature("feat-b", ["tests/test_b.py"]),
        ]
        result = charge_feature_for_failures(
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
        charge_feature_for_failures(
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
        result = charge_feature_for_failures(
            failing_tests=[],
            all_features=features,
            increment_fn=charged.append,
        )
        assert result == 0
        assert charged == []

    def test_no_matching_ac_returns_zero(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        result = charge_feature_for_failures(
            failing_tests=["tests/test_unrelated.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert result == 0
        assert charged == []

    def test_unowned_test_triggers_record_fn(self):
        events = []
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        charge_feature_for_failures(
            failing_tests=["tests/test_orphan.py::test_x"],
            all_features=features,
            increment_fn=lambda _: None,
            unowned_record_fn=events.append,
        )
        assert len(events) == 1

    def test_unowned_record_fn_optional(self):
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        result = charge_feature_for_failures(
            failing_tests=["tests/test_orphan.py::test_x"],
            all_features=features,
            increment_fn=lambda _: None,
        )
        assert result == 0


class TestFindOwnerFeaturePublicApi:
    def test_finds_owner_by_file(self):
        features = [_make_feature("feat-a", ["tests/test_a.py"])]
        owner = find_owner_feature(
            failing_test="tests/test_a.py::test_something",
            all_features=features,
        )
        assert owner == "feat-a"

    def test_returns_none_for_orphan(self):
        owner = find_owner_feature(
            failing_test="tests/test_orphan.py::test_x",
            all_features=[],
        )
        assert owner is None

    def test_raises_in_strict_mode(self):
        with pytest.raises(OrphanTestError):
            find_owner_feature(
                failing_test="tests/test_orphan.py::test_x",
                all_features=[],
                strict=True,
            )


class TestPreserveInnocentStatus:
    def test_returns_statuses_for_uncharged_features(self):
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

    def test_all_features_innocent_when_none_charged(self):
        features = [
            _make_feature("feat-a", ["tests/test_a.py"], status="executing"),
        ]
        preserved = preserve_innocent_status(
            all_features=features,
            charged_feature_ids=set(),
        )
        assert preserved["feat-a"] == "executing"


class TestHandleUnownedFailure:
    def test_records_event_with_type(self):
        events = []
        handle_unowned_failure(
            failing_test="tests/test_orphan.py::test_x",
            record_fn=events.append,
        )
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, dict)
        assert event.get("type") == "unattributed_failure"

    def test_event_contains_test_path(self):
        events = []
        handle_unowned_failure(
            failing_test="tests/test_orphan.py::test_x",
            record_fn=events.append,
        )
        assert events[0]["failing_test"] == "tests/test_orphan.py::test_x"
