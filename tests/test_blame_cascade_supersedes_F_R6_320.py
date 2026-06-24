"""Tests: blame_cascade supersedes F-R6-320 unconditional charge.

F-R6-320 was the old behavior: any feature that ran during verification
got a refinement charge, regardless of which tests it owned. blame_cascade
replaces this with targeted attribution.

These tests verify that blame_cascade is NOT the old behavior.
"""

import pytest
from bob.orchestrator.blame_cascade import (
    find_owner_feature,
    charge_refinement,
    preserve_innocent_status,
)


def _make_feature(fid: str, pytest_paths: list[str]) -> dict:
    acs = [f"pytest: {p}" for p in pytest_paths]
    return {"id": fid, "acceptance_criteria": acs}


class TestSupersededBehavior:
    def test_non_owning_feature_is_never_charged(self):
        """Old F-R6-320 would charge all features; new logic charges only owners."""
        charged = []
        features = [
            _make_feature("breaker", ["tests/test_breaker.py"]),
            _make_feature("victim-1", ["tests/test_victim1.py"]),
            _make_feature("victim-2", ["tests/test_victim2.py"]),
        ]
        charge_refinement(
            failing_tests=["tests/test_breaker.py::test_regression"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert "victim-1" not in charged
        assert "victim-2" not in charged

    def test_only_the_breaking_feature_is_charged(self):
        charged = []
        features = [
            _make_feature("breaker", ["tests/test_breaker.py"]),
            _make_feature("innocent-a", ["tests/test_innocent_a.py"]),
            _make_feature("innocent-b", ["tests/test_innocent_b.py"]),
        ]
        charge_refinement(
            failing_tests=["tests/test_breaker.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert len(charged) == 1
        assert charged[0] == "breaker"

    def test_attribution_is_by_pytest_ac_ownership(self):
        """Only the feature with a matching pytest: AC is charged."""
        features = [
            _make_feature("feat-with-ac", ["tests/test_owned.py"]),
            _make_feature("feat-without-ac", []),  # no pytest: ACs at all
        ]
        owner = find_owner_feature(
            failing_test="tests/test_owned.py::test_something",
            all_features=features,
        )
        assert owner == "feat-with-ac"

    def test_feature_without_pytest_ac_is_never_charged(self):
        charged = []
        features = [
            _make_feature("has-ac", ["tests/test_foo.py"]),
            _make_feature("no-ac", []),  # no pytest ACs, so can never be an owner
        ]
        charge_refinement(
            failing_tests=["tests/test_foo.py::test_x"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert "no-ac" not in charged

    def test_targeted_charge_preserves_innocent_pre_verification_status(self):
        features = [
            {"id": "breaker", "acceptance_criteria": ["pytest: tests/test_breaker.py"], "status": "executing"},
            {"id": "innocent", "acceptance_criteria": ["pytest: tests/test_innocent.py"], "status": "ready"},
        ]
        charged_ids = {"breaker"}
        preserved = preserve_innocent_status(
            all_features=features,
            charged_feature_ids=charged_ids,
        )
        # Innocent feature keeps pre-verification status
        assert preserved["innocent"] == "ready"
