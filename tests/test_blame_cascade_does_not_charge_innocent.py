"""Tests: innocent features (non-owners) are not charged refinement attempts."""

import pytest
from bob3.orchestrator.blame_cascade import (
    find_owner_feature,
    charge_refinement,
    preserve_innocent_status,
)


def _make_feature(fid: str, pytest_paths: list[str], status: str = "executing") -> dict:
    acs = [f"pytest: {p}" for p in pytest_paths]
    return {"id": fid, "acceptance_criteria": acs, "status": status}


class TestDoesNotChargeInnocent:
    def test_innocent_feature_not_in_charged_set(self):
        charged = []
        features = [
            _make_feature("guilty", ["tests/test_guilty.py"]),
            _make_feature("innocent", ["tests/test_innocent.py"]),
        ]
        charge_refinement(
            failing_tests=["tests/test_guilty.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert "innocent" not in charged

    def test_only_guilty_feature_is_charged(self):
        charged = []
        features = [
            _make_feature("guilty", ["tests/test_guilty.py"]),
            _make_feature("innocent-1", ["tests/test_innocent1.py"]),
            _make_feature("innocent-2", ["tests/test_innocent2.py"]),
        ]
        charge_refinement(
            failing_tests=["tests/test_guilty.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert charged == ["guilty"]

    def test_multiple_innocents_not_charged(self):
        charged = []
        features = [
            _make_feature("guilty", ["tests/test_guilty.py"]),
            _make_feature("innocent-a", ["tests/test_innocent_a.py"]),
            _make_feature("innocent-b", ["tests/test_innocent_b.py"]),
            _make_feature("innocent-c", ["tests/test_innocent_c.py"]),
        ]
        charge_refinement(
            failing_tests=["tests/test_guilty.py::test_broken"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert len(charged) == 1
        assert charged[0] == "guilty"


class TestPreserveInnocentStatus:
    def test_preserve_innocent_status_returns_pre_verification_status(self):
        features = [
            _make_feature("f-owner", ["tests/test_owner.py"]),
            _make_feature("f-innocent", ["tests/test_innocent.py"]),
        ]
        charged_ids = {"f-owner"}
        preserved = preserve_innocent_status(
            all_features=features,
            charged_feature_ids=charged_ids,
        )
        assert "f-innocent" in preserved
        assert "f-owner" not in preserved

    def test_preserve_innocent_status_returns_dict_of_statuses(self):
        features = [
            _make_feature("f-owner", ["tests/test_owner.py"], status="failed"),
            _make_feature("f-innocent", ["tests/test_innocent.py"], status="ready"),
        ]
        charged_ids = {"f-owner"}
        preserved = preserve_innocent_status(
            all_features=features,
            charged_feature_ids=charged_ids,
        )
        assert preserved["f-innocent"] == "ready"

    def test_all_features_innocent_all_statuses_preserved(self):
        features = [
            _make_feature("f-a", ["tests/test_a.py"], status="executing"),
            _make_feature("f-b", ["tests/test_b.py"], status="ready"),
        ]
        charged_ids: set = set()
        preserved = preserve_innocent_status(
            all_features=features,
            charged_feature_ids=charged_ids,
        )
        assert preserved["f-a"] == "executing"
        assert preserved["f-b"] == "ready"
