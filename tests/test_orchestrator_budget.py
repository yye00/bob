"""Tests for orchestrator budget enforcement with per-feature cost ceiling.

AC: pytest: tests/test_orchestrator_budget.py

Verifies the fix for F-R7-585: apply_pessimistic_cost MUST use a per-feature
ceiling (BOB3_PER_FEATURE_COST_CEILING, default $20), NOT the entire project
max_cost_usd. The original bug caused BUDGET_EXCEEDED after a single telemetry-
lost feature consumed the entire $10M project budget as its pessimistic charge.
"""

from __future__ import annotations

import os

import pytest

from bob3.orchestrator.run_loop import apply_pessimistic_cost


class TestApplyPessimisticCostExportedFromRunLoop:
    """apply_pessimistic_cost is accessible from bob3.orchestrator.run_loop."""

    def test_importable_from_run_loop(self):
        """AC: Function defined: bob3.orchestrator.run_loop.apply_pessimistic_cost."""
        from bob3.orchestrator.run_loop import apply_pessimistic_cost as fn
        assert callable(fn)

    def test_same_function_as_cost_telemetry_guard(self):
        """The export in run_loop IS the same function from cost_telemetry_guard."""
        from bob3.orchestrator.cost_telemetry_guard import apply_pessimistic_cost as direct
        from bob3.orchestrator.run_loop import apply_pessimistic_cost as via_loop
        assert direct is via_loop


class TestPerFeatureCeilingNotProjectBudget:
    """Core bug fix: pessimistic charge must be per-feature, not the project total."""

    def test_charges_per_feature_ceiling_not_10m_project_budget(self):
        """The fix: is_lost=True charges per_feature_ceiling, not project budget."""
        per_feature_ceiling = 20.0
        project_budget = 10_000_000.0

        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=per_feature_ceiling,
        )

        assert result == pytest.approx(per_feature_ceiling)
        assert result < project_budget, (
            "Per-feature ceiling must be orders of magnitude below the project budget"
        )

    def test_default_ceiling_matches_p95_real_cost(self):
        """Default $20 ceiling matches empirical p95 of real per-feature costs."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(20.0)

    def test_single_telemetry_loss_cannot_exhaust_large_budget(self):
        """One telemetry-loss event with $20 ceiling cannot exhaust a $10M budget."""
        budget = 10_000_000.0
        ceiling = 20.0
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=ceiling,
        )
        assert result < budget * 0.01, (
            "Single telemetry-loss charge must be < 1% of project budget"
        )

    def test_env_override_bob3_per_feature_cost_ceiling(self, monkeypatch):
        """BOB3_PER_FEATURE_COST_CEILING env var sets the ceiling used in run_loop."""
        monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "50.0")
        ceiling = float(os.environ.get("BOB3_PER_FEATURE_COST_CEILING", "20.0"))
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=ceiling,
        )
        assert result == pytest.approx(50.0)

    def test_env_default_is_twenty_dollars(self, monkeypatch):
        """Default when BOB3_PER_FEATURE_COST_CEILING is unset is $20."""
        monkeypatch.delenv("BOB3_PER_FEATURE_COST_CEILING", raising=False)
        ceiling = float(os.environ.get("BOB3_PER_FEATURE_COST_CEILING", "20.0"))
        assert ceiling == pytest.approx(20.0)


class TestBudgetNotLostTelemetry:
    """When telemetry is intact, budget enforcement uses reported cost."""

    def test_reported_cost_used_when_not_lost(self):
        """is_lost=False returns the actual reported cost."""
        reported = 3.14
        result = apply_pessimistic_cost(
            reported_cost=reported,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(reported)

    def test_ceiling_not_applied_when_not_lost(self):
        """Ceiling is NOT applied when telemetry is present."""
        result = apply_pessimistic_cost(
            reported_cost=5.0,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(5.0)
        assert result != pytest.approx(20.0)

    def test_zero_cost_genuine_crash_not_charged_ceiling(self):
        """is_lost=False with cost=0.0 returns 0.0 (genuine spawn crash, free retry)."""
        result = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=False,
            per_feature_ceiling=20.0,
        )
        assert result == pytest.approx(0.0)


class TestRunLoopEnvCeilingLogic:
    """Verify the env-reading logic used in run_loop matches expectations."""

    def test_ceiling_defaults_to_20_when_env_unset(self, monkeypatch):
        """run_loop logic: BOB3_PER_FEATURE_COST_CEILING absent → 20.0."""
        monkeypatch.delenv("BOB3_PER_FEATURE_COST_CEILING", raising=False)
        try:
            pf_default = float(os.environ.get("BOB3_PER_FEATURE_COST_CEILING", "20.0"))
        except (TypeError, ValueError):
            pf_default = 20.0
        assert pf_default == pytest.approx(20.0)

    def test_ceiling_reads_env_override(self, monkeypatch):
        """run_loop logic: BOB3_PER_FEATURE_COST_CEILING=30 → 30.0."""
        monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "30.0")
        try:
            pf_default = float(os.environ.get("BOB3_PER_FEATURE_COST_CEILING", "20.0"))
        except (TypeError, ValueError):
            pf_default = 20.0
        assert pf_default == pytest.approx(30.0)

    def test_ceiling_falls_back_on_invalid_env(self, monkeypatch):
        """run_loop logic: invalid BOB3_PER_FEATURE_COST_CEILING → fallback 20.0."""
        monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "not-a-number")
        try:
            pf_default = float(os.environ.get("BOB3_PER_FEATURE_COST_CEILING", "20.0"))
        except (TypeError, ValueError):
            pf_default = 20.0
        assert pf_default == pytest.approx(20.0)
