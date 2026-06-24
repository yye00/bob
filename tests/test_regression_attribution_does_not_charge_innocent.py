"""Tests ensuring innocent bystander features are NOT charged.

Feature 15f5b3b8-a57f-4fb7-91e7-859767805eca — the blame-the-cause invariant.

When feature A's tests break and feature B is simultaneously being verified,
only feature A (the owner of the failing pytest: AC) must be charged a
refinement attempt. Feature B must stay at its pre-verification status.
"""

from __future__ import annotations

import json
import pytest


def _make_feature(
    feature_id: str,
    name: str,
    ac_list: list[str] | None = None,
    status: str = "executing",
):
    class FakeFeature:
        pass

    f = FakeFeature()
    f.id = feature_id
    f.name = name
    f.acceptance_criteria = json.dumps(ac_list or [])
    f.status = status
    f.refinement_attempts = 0
    f.max_refinement_attempts = 5
    return f


class TestInnocentFeatureNotCharged:
    """The core contract: bystander features must NOT lose refinement budget."""

    def test_bystander_not_in_charged_set(self):
        """Feature B owns no failing test → charge_owners must not include it."""
        from bob.orchestrator.regression_attribution import (
            attribute_failures,
            charge_owners,
        )

        feature_a = _make_feature(
            "feat-a", "Feature A",
            ["pytest: tests/test_a.py::test_broken"],
        )
        feature_b = _make_feature(
            "feat-b", "Feature B",
            ["pytest: tests/test_b.py::test_still_passing"],
        )

        failing = ["tests/test_a.py::test_broken"]
        attribution = attribute_failures(
            failing_tests=failing,
            all_features=[feature_a, feature_b],
        )
        called = {}

        def fake_increment(fid):
            called[fid] = called.get(fid, 0) + 1

        charged = charge_owners(attribution=attribution, increment_fn=fake_increment)

        assert "feat-b" not in charged
        assert called.get("feat-b") is None

    def test_only_cause_feature_charged_not_bystander(self):
        """A → breaks test; B has no failing test → only A is charged."""
        from bob.orchestrator.regression_attribution import (
            attribute_failures,
            charge_owners,
        )

        feature_a = _make_feature(
            "feat-a", "Feature A",
            ["pytest: tests/test_a.py::test_broken"],
        )
        feature_b = _make_feature(
            "feat-b", "Feature B",
            ["File exists: src/b.py", "Function defined: b.run"],
        )
        feature_c = _make_feature(
            "feat-c", "Feature C",
            ["pytest: tests/test_c.py::test_still_passing"],
        )

        failing = ["tests/test_a.py::test_broken"]
        attribution = attribute_failures(
            failing_tests=failing,
            all_features=[feature_a, feature_b, feature_c],
        )
        called = {}

        def fake_increment(fid):
            called[fid] = called.get(fid, 0) + 1

        charged = charge_owners(attribution=attribution, increment_fn=fake_increment)

        assert "feat-a" in charged
        assert "feat-b" not in charged
        assert "feat-c" not in charged
        assert called.get("feat-a") == 1
        assert called.get("feat-b") is None
        assert called.get("feat-c") is None

    def test_bystander_with_no_ac_not_charged(self):
        """Feature with no AC at all must not be charged."""
        from bob.orchestrator.regression_attribution import (
            attribute_failures,
            charge_owners,
        )

        feature_a = _make_feature("feat-a", "Feature A",
                                  ["pytest: tests/test_a.py::test_broken"])
        feature_bystander = _make_feature("feat-bystand", "Bystander", ac_list=None)

        failing = ["tests/test_a.py::test_broken"]
        attribution = attribute_failures(
            failing_tests=failing,
            all_features=[feature_a, feature_bystander],
        )
        called = {}

        def fake_increment(fid):
            called[fid] = called.get(fid, 0) + 1

        charged = charge_owners(attribution=attribution, increment_fn=fake_increment)

        assert "feat-bystand" not in charged
        assert called.get("feat-bystand") is None

    def test_unowned_failing_test_does_not_charge_anyone(self):
        """If no feature claims a failing test, no one is charged."""
        from bob.orchestrator.regression_attribution import (
            attribute_failures,
            charge_owners,
        )

        feature_a = _make_feature("feat-a", "Feature A",
                                  ["pytest: tests/test_a.py::test_something"])
        feature_b = _make_feature("feat-b", "Feature B",
                                  ["pytest: tests/test_b.py::test_other"])

        failing = ["tests/test_orphan.py::test_nobody_owns_me"]
        attribution = attribute_failures(
            failing_tests=failing,
            all_features=[feature_a, feature_b],
        )
        called = {}

        def fake_increment(fid):
            called[fid] = called.get(fid, 0) + 1

        charged = charge_owners(attribution=attribution, increment_fn=fake_increment)

        assert charged == set()
        assert called == {}

    def test_partial_responsibility_only_owner_charged(self):
        """Mixed batch: some tests attributed, some not — only owners charged."""
        from bob.orchestrator.regression_attribution import (
            attribute_failures,
            charge_owners,
        )

        feature_a = _make_feature("feat-a", "Feature A",
                                  ["pytest: tests/test_a.py::test_owned"])
        feature_b = _make_feature("feat-b", "Feature B",
                                  ["pytest: tests/test_b.py::test_b_passing"])

        # Two failing tests: one owned by A, one unowned
        failing = [
            "tests/test_a.py::test_owned",
            "tests/test_orphan.py::test_not_owned",
        ]
        attribution = attribute_failures(
            failing_tests=failing,
            all_features=[feature_a, feature_b],
        )
        called = {}

        def fake_increment(fid):
            called[fid] = called.get(fid, 0) + 1

        charged = charge_owners(attribution=attribution, increment_fn=fake_increment)

        assert "feat-a" in charged
        assert "feat-b" not in charged
        assert called.get("feat-a") == 1
        assert called.get("feat-b") is None


class TestRunLoopIntegration:
    """Integration: module can be imported from run_loop's scope."""

    def test_regression_attribution_importable_from_orchestrator(self):
        """The module must be importable as bob.orchestrator.regression_attribution."""
        import importlib
        mod = importlib.import_module("bob.orchestrator.regression_attribution")
        assert hasattr(mod, "attribute_failures")
        assert hasattr(mod, "charge_owners")

    def test_run_loop_module_importable_with_regression_attribution(self):
        """run_loop can be imported after regression_attribution exists."""
        import importlib
        mod = importlib.import_module("bob.orchestrator.run_loop")
        assert mod is not None
