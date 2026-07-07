"""Regression tests: telemetry-loss must charge a per-feature ceiling, NOT the
whole project budget.

AC: pytest: tests/test_per_feature_cost_ceiling.py

Background (F-R7-585): a prior generation terminated with BUDGET_EXCEEDED
reporting total_cost=$10,000,600 after one feature attempt whose real cost was
~$1. run_loop passed ``self._project_max_cost_usd`` (the ENTIRE project budget)
as ``per_feature_ceiling`` to ``apply_pessimistic_cost``. When a feature's
telemetry was lost, the guard correctly charged the ceiling — but the ceiling
was the whole budget, so total jumped to budget+epsilon in one increment.

The fix routes the ceiling through
``bob.orchestrator.per_feature_ceiling.compute_per_feature_ceiling`` which
returns a sane default ($20, override via BOB_PER_FEATURE_COST_CEILING) that
matches the p95 of real per-feature costs.
"""

from __future__ import annotations

import pytest

from bob.orchestrator.run_loop import apply_pessimistic_cost
from bob.orchestrator.per_feature_ceiling import compute_per_feature_ceiling


_ENV_VAR = "BOB_PER_FEATURE_COST_CEILING"


# --- compute_per_feature_ceiling: default + override ---

def test_default_ceiling_is_twenty(monkeypatch):
    """With no env override, the per-feature ceiling defaults to $20."""
    monkeypatch.delenv(_ENV_VAR, raising=False)
    assert compute_per_feature_ceiling() == pytest.approx(20.0)


def test_env_override_positive_float(monkeypatch):
    """A valid positive env value overrides the default."""
    monkeypatch.setenv(_ENV_VAR, "7.5")
    assert compute_per_feature_ceiling() == pytest.approx(7.5)


def test_env_override_invalid_falls_back_to_default(monkeypatch):
    """A non-numeric env value falls back to the $20 default (never raises)."""
    monkeypatch.setenv(_ENV_VAR, "not-a-number")
    assert compute_per_feature_ceiling() == pytest.approx(20.0)


def test_env_override_zero_falls_back_to_default(monkeypatch):
    """A zero env value is not a usable ceiling → default $20."""
    monkeypatch.setenv(_ENV_VAR, "0")
    assert compute_per_feature_ceiling() == pytest.approx(20.0)


def test_env_override_negative_falls_back_to_default(monkeypatch):
    """A negative env value is not a usable ceiling → default $20."""
    monkeypatch.setenv(_ENV_VAR, "-100")
    assert compute_per_feature_ceiling() == pytest.approx(20.0)


def test_ceiling_return_type_is_float(monkeypatch):
    monkeypatch.delenv(_ENV_VAR, raising=False)
    assert isinstance(compute_per_feature_ceiling(), float)


# --- The core regression: charge the per-feature ceiling, not the budget ---

def test_telemetry_loss_charges_per_feature_ceiling_not_project_budget(monkeypatch):
    """On telemetry loss the charge is the per-feature ceiling ($20), never
    the multi-million-dollar project budget (the F-R7-585 bug)."""
    monkeypatch.delenv(_ENV_VAR, raising=False)
    ceiling = compute_per_feature_ceiling()
    project_budget = 10_000_000.0

    charged = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=ceiling,
    )

    assert charged == pytest.approx(20.0)
    assert charged < project_budget
    # Regression guard: the charge must be many orders of magnitude below budget.
    assert charged <= project_budget / 1000


def test_telemetry_present_charges_reported_cost(monkeypatch):
    """When telemetry is not lost, the exact reported cost is charged."""
    monkeypatch.delenv(_ENV_VAR, raising=False)
    charged = apply_pessimistic_cost(
        reported_cost=1.23,
        is_lost=False,
        per_feature_ceiling=compute_per_feature_ceiling(),
    )
    assert charged == pytest.approx(1.23)


def test_ceiling_override_flows_into_pessimistic_charge(monkeypatch):
    """Operator override of the ceiling is honored by the charged amount."""
    monkeypatch.setenv(_ENV_VAR, "50")
    ceiling = compute_per_feature_ceiling()
    charged = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=ceiling,
    )
    assert charged == pytest.approx(50.0)
