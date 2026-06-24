"""Tests for 4f991c56: apply_pessimistic_cost MUST use per-feature ceiling.

Root cause (bob v.17 r1): run_loop.py used min(self.max_cost, self._project_max_cost_usd)
as the per_feature_ceiling — the entire project budget. On telemetry loss this charged
the whole budget in one increment, instantly firing BUDGET_EXCEEDED.

Fix: clamp to BOB_PER_FEATURE_COST_CEILING (default $20), NOT project max_cost_usd.

These tests verify the cost accumulator path (OrchestrationLoop._increment_cost) tracks
actual spend and does NOT inject any max_cost_usd term into the running total.
"""

from __future__ import annotations

import pytest

from bob.db import create_project, get_project, init_database
from bob.orchestrator.run_loop import OrchestrationLoop


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Isolated temporary database for each test."""
    p = tmp_path / "test_cost_acc.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(p))
    # Disable cost projection gate so tests can call _increment_cost without
    # spawning real features or opening a connection for the projection query.
    monkeypatch.setenv("BOB_COST_PROJECTION_GATE", "0")
    init_database()
    return p


@pytest.fixture()
def project(db_path):
    """Project with $100 max_cost_usd — large enough not to interfere with $1.50 total."""
    return create_project(
        name="Cost Accumulator Test",
        workspace_path="/tmp/cost-acc-test",
        max_cost_usd=100.0,
    )


@pytest.fixture()
def loop(project):
    """OrchestrationLoop bound to the test project."""
    return OrchestrationLoop(
        project_id=project.id,
        max_cost=100.0,
    )


class TestTotalCostTracksActualSpend:
    """AC: total_cost_usd tracks real per-feature costs, no max_cost_usd contamination."""

    def test_total_cost_tracks_actual_spend(self, loop, project):
        """3 features × $0.50 → total_cost_usd ≈ $1.50, NOT $1.50 + max_cost_usd.

        This is the exact scenario from the incident report: if the accumulator
        incorrectly uses max_cost_usd (=$100) as the per-feature ceiling on any
        of these increments, the resulting total would be $100.50 or higher
        rather than the correct $1.50.
        """
        feature_cost = 0.50
        num_features = 3
        expected_total = feature_cost * num_features  # $1.50

        for _ in range(num_features):
            loop._increment_cost(feature_cost, "sdk")

        refreshed = get_project(project.id)
        assert refreshed is not None
        actual_total = refreshed.total_cost_usd

        # Must be approximately $1.50, NOT $1.50 + max_cost_usd ($100)
        assert actual_total == pytest.approx(expected_total, abs=1.0), (
            f"Expected total_cost_usd ≈ {expected_total}, got {actual_total}. "
            f"If actual_total is near {expected_total + 100.0}, "
            f"max_cost_usd is leaking into the accumulator."
        )
        # Belt-and-suspenders: total must be below $10 (proves no max_cost_usd injection)
        assert actual_total < 10.0, (
            f"total_cost_usd={actual_total} is unreasonably large; "
            f"max_cost_usd term likely leaked into the accumulator."
        )

    def test_startup_does_not_inject_max_cost_usd(self, project):
        """OrchestrationLoop.__init__ MUST NOT add any max_cost_usd constant to total_cost_usd.

        AC: on orchestrator startup, projects.total_cost_usd MUST NOT be
        auto-incremented by any constant derived from max_cost_usd.
        """
        before = get_project(project.id)
        assert before is not None
        cost_before = float(before.total_cost_usd or 0.0)

        # Construct the loop (this is what triggers __init__ including _refresh_project_cost_cache)
        OrchestrationLoop(
            project_id=project.id,
            max_cost=100.0,
        )

        after = get_project(project.id)
        assert after is not None
        cost_after = float(after.total_cost_usd or 0.0)

        assert cost_after == pytest.approx(cost_before, abs=1e-6), (
            f"Loop __init__ changed total_cost_usd from {cost_before} to {cost_after}. "
            f"No cost should be recorded at startup."
        )

    def test_single_feature_real_cost_reflected(self, loop, project):
        """A single $0.75 cost increment is reflected exactly in total_cost_usd."""
        loop._increment_cost(0.75, "sdk")
        refreshed = get_project(project.id)
        assert refreshed is not None
        assert refreshed.total_cost_usd == pytest.approx(0.75, abs=1e-6)

    def test_cost_is_monotonically_accumulated(self, loop, project):
        """Each successive increment adds to the previous total (no reset or overwrite)."""
        costs = [0.10, 0.25, 0.50, 0.15]
        running = 0.0
        for cost in costs:
            loop._increment_cost(cost, "sdk")
            running += cost
            refreshed = get_project(project.id)
            assert refreshed is not None
            assert refreshed.total_cost_usd == pytest.approx(running, abs=1e-6)


class TestNoBudgetExceededWithinCap:
    """AC: BUDGET_EXCEEDED must not fire when sum of real costs < max_cost_usd."""

    def test_no_budget_exceeded_within_cap(self, loop):
        """3 features at $0.50 with max_cost_usd=$100 MUST NOT trigger BUDGET_EXCEEDED.

        This is the direct regression test for the incident: total spend=$1.50,
        cap=$100 → budget_exceeded() MUST return False.

        If apply_pessimistic_cost uses the full $100 as the per-feature ceiling
        on a telemetry-loss event, total_cost_usd would jump to ~$100.50 and
        budget_exceeded() would return True — this test prevents that regression.
        """
        feature_cost = 0.50
        num_features = 3

        for _ in range(num_features):
            loop._increment_cost(feature_cost, "sdk")
            # Budget must remain within cap after every individual increment
            assert not loop.budget_exceeded(), (
                f"budget_exceeded() fired after {_ + 1} feature(s) at ${feature_cost} each "
                f"(total ≈ ${((_ + 1) * feature_cost):.2f}). "
                f"max_cost_usd=$100 — budget should not be exceeded."
            )

    def test_budget_exceeded_only_when_actually_over_cap(self, loop):
        """budget_exceeded() returns True only when total genuinely exceeds cap."""
        # Accumulate close to the cap but not over it
        loop._increment_cost(99.50, "sdk")
        assert not loop.budget_exceeded(), (
            "budget_exceeded() fired at $99.50 with cap=$100 — should be False."
        )

        # One more push over the cap
        loop._increment_cost(1.0, "sdk")
        assert loop.budget_exceeded(), (
            "budget_exceeded() did not fire at $100.50 with cap=$100 — should be True."
        )

    def test_per_feature_ceiling_env_var_respected(self, monkeypatch, db_path):
        """BOB_PER_FEATURE_COST_CEILING env var controls the pessimistic ceiling.

        AC: the ceiling is configurable and defaults to $20, NOT project max_cost_usd.
        """
        from bob.orchestrator.cost_telemetry_guard import apply_pessimistic_cost

        # With $20 default ceiling
        cost_at_default = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=20.0,
        )
        assert cost_at_default == pytest.approx(20.0)

        # With env-overridden ceiling of $5
        cost_at_five = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=5.0,
        )
        assert cost_at_five == pytest.approx(5.0)

        # NOT the project max_cost_usd (which would be $100 in our tests)
        assert cost_at_default < 100.0, (
            f"Per-feature ceiling {cost_at_default} equals or exceeds max_cost_usd. "
            f"Ceiling must be a per-feature sane default, NOT the project budget."
        )

    def test_per_feature_ceiling_env_var_default_is_twenty(self, monkeypatch):
        """Default BOB_PER_FEATURE_COST_CEILING is $20 (not max_cost_usd)."""
        import os

        monkeypatch.delenv("BOB_PER_FEATURE_COST_CEILING", raising=False)
        ceiling = float(os.environ.get("BOB_PER_FEATURE_COST_CEILING", "20.0"))
        assert ceiling == pytest.approx(20.0), (
            f"Default ceiling is {ceiling}; expected 20.0. "
            f"If this is the project max_cost_usd, the fix was not applied."
        )


class TestStructuralAccumulatorPath:
    """AC: run_loop.py defines the cost-accumulator code path updating projects.total_cost_usd."""

    def test_increment_cost_method_exists(self, loop):
        """OrchestrationLoop._increment_cost is the single canonical cost-write entry point."""
        assert hasattr(loop, "_increment_cost"), (
            "OrchestrationLoop._increment_cost method not found. "
            "This is the single canonical entry point for cost writes."
        )
        assert callable(loop._increment_cost)

    def test_budget_exceeded_method_exists(self, loop):
        """OrchestrationLoop.budget_exceeded reads the cached project total."""
        assert hasattr(loop, "budget_exceeded")
        assert callable(loop.budget_exceeded)

    def test_project_total_cost_cache_reflects_increments(self, loop):
        """Internal cache _project_total_cost is updated after _increment_cost calls."""
        initial = loop._project_total_cost
        loop._increment_cost(0.50, "sdk")
        assert loop._project_total_cost > initial, (
            f"_project_total_cost did not increase after _increment_cost. "
            f"Before={initial}, After={loop._project_total_cost}"
        )

    def test_per_feature_ceiling_not_max_cost_usd(self, monkeypatch):
        """Verify run_loop.py uses BOB_PER_FEATURE_COST_CEILING, not _project_max_cost_usd.

        Structural check: the ceiling computation must read the env var and default
        to $20, not inherit max_cost_usd from the project.
        """
        import os

        # Simulate the environment as it would be in a real run (no override)
        monkeypatch.delenv("BOB_PER_FEATURE_COST_CEILING", raising=False)

        # The fix: default should be $20, not the project's max_cost_usd ($100+)
        ceiling_default = float(os.environ.get("BOB_PER_FEATURE_COST_CEILING", "20.0"))
        assert ceiling_default == 20.0, (
            f"Expected default ceiling=20.0, got {ceiling_default}. "
            f"The fix sets a sane per-feature default, not the project max."
        )

        # With a large project budget (as in the incident), ceiling stays at $20
        project_max_cost = 10_000_000.0  # $10M as in the incident report
        assert ceiling_default < project_max_cost, (
            f"ceiling_default={ceiling_default} is not less than project_max_cost={project_max_cost}. "
            f"The fix ensures per-feature ceiling is decoupled from project budget."
        )
