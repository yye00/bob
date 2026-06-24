"""Tests for the per-feature cost ceiling fix in the orchestrator.

AC: pytest: tests/test_orchestrator_cost_ceiling.py
AC: integration: bob.orchestrator.run_loop
AC: Function defined: bob.orchestrator.run_loop.apply_pessimistic_cost

Verifies that apply_pessimistic_cost uses a per-feature ceiling (NOT the
entire project budget), so telemetry-loss can never charge $10M for a
single feature and instantly trip BUDGET_EXCEEDED.
"""

from __future__ import annotations

import os

import pytest

from bob.orchestrator.run_loop import apply_pessimistic_cost
from bob.orchestrator.per_feature_ceiling import compute_per_feature_ceiling


# ---------------------------------------------------------------------------
# Integration: apply_pessimistic_cost is importable from run_loop
# ---------------------------------------------------------------------------

def test_apply_pessimistic_cost_importable_from_run_loop():
    """apply_pessimistic_cost must be importable from bob.orchestrator.run_loop."""
    assert callable(apply_pessimistic_cost)


# ---------------------------------------------------------------------------
# Core behaviour: per-feature ceiling, NOT project budget
# ---------------------------------------------------------------------------

def test_is_lost_returns_per_feature_ceiling():
    """When is_lost=True the charged cost equals per_feature_ceiling, not the project budget."""
    project_budget = 10_000_000.0  # $10M — the whole project
    per_feature = 20.0             # $20  — sane per-feature default

    charged = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=per_feature,
    )

    assert charged == pytest.approx(per_feature), (
        f"Expected {per_feature}, got {charged}. "
        "apply_pessimistic_cost must charge the per-feature ceiling, "
        "not the project-wide max_cost_usd."
    )
    assert charged < project_budget, (
        "Charged cost must be well below the project budget to avoid "
        "instantly tripping BUDGET_EXCEEDED on telemetry loss."
    )


def test_is_not_lost_returns_reported_cost():
    """When is_lost=False the reported cost is returned as-is."""
    charged = apply_pessimistic_cost(
        reported_cost=1.23,
        is_lost=False,
        per_feature_ceiling=20.0,
    )
    assert charged == pytest.approx(1.23)


def test_default_ceiling_is_sane():
    """compute_per_feature_ceiling() default must be <= $100 (not project-scale)."""
    os.environ.pop("BOB_PER_FEATURE_COST_CEILING", None)
    ceiling = compute_per_feature_ceiling()
    assert ceiling > 0.0, "Ceiling must be positive"
    assert ceiling <= 100.0, (
        f"Default ceiling {ceiling} is too large — it should reflect a "
        "real per-feature cost cap (~$20), not the project budget."
    )


def test_env_override_ceiling():
    """BOB_PER_FEATURE_COST_CEILING env var overrides the default ceiling."""
    os.environ["BOB_PER_FEATURE_COST_CEILING"] = "5.0"
    try:
        ceiling = compute_per_feature_ceiling()
        assert ceiling == pytest.approx(5.0)
    finally:
        del os.environ["BOB_PER_FEATURE_COST_CEILING"]


def test_invalid_env_ceiling_falls_back_to_default():
    """Invalid BOB_PER_FEATURE_COST_CEILING falls back to default (no raise)."""
    os.environ["BOB_PER_FEATURE_COST_CEILING"] = "not-a-number"
    try:
        ceiling = compute_per_feature_ceiling()
        assert ceiling > 0.0  # falls back to default ($20)
        assert ceiling <= 100.0
    finally:
        del os.environ["BOB_PER_FEATURE_COST_CEILING"]


def test_negative_env_ceiling_falls_back_to_default():
    """Negative BOB_PER_FEATURE_COST_CEILING is rejected and falls back to default."""
    os.environ["BOB_PER_FEATURE_COST_CEILING"] = "-5.0"
    try:
        ceiling = compute_per_feature_ceiling()
        assert ceiling > 0.0
    finally:
        del os.environ["BOB_PER_FEATURE_COST_CEILING"]


def test_zero_env_ceiling_falls_back_to_default():
    """Zero BOB_PER_FEATURE_COST_CEILING is rejected and falls back to default."""
    os.environ["BOB_PER_FEATURE_COST_CEILING"] = "0.0"
    try:
        ceiling = compute_per_feature_ceiling()
        assert ceiling > 0.0
    finally:
        del os.environ["BOB_PER_FEATURE_COST_CEILING"]


# ---------------------------------------------------------------------------
# Integration: ceiling fed into apply_pessimistic_cost produces safe charges
# ---------------------------------------------------------------------------

def test_compute_then_apply_ceiling_does_not_charge_project_budget():
    """End-to-end: compute ceiling, apply it, confirm result is << project budget."""
    os.environ.pop("BOB_PER_FEATURE_COST_CEILING", None)
    ceiling = compute_per_feature_ceiling()
    charged = apply_pessimistic_cost(
        reported_cost=0.0,
        is_lost=True,
        per_feature_ceiling=ceiling,
    )
    assert charged == pytest.approx(ceiling)
    assert charged < 10_000_000.0, (
        "A single telemetry-lost feature must never be charged the project budget."
    )


def test_apply_pessimistic_cost_with_env_ceiling():
    """apply_pessimistic_cost respects a custom env ceiling end-to-end."""
    os.environ["BOB_PER_FEATURE_COST_CEILING"] = "7.5"
    try:
        ceiling = compute_per_feature_ceiling()
        charged = apply_pessimistic_cost(
            reported_cost=0.0,
            is_lost=True,
            per_feature_ceiling=ceiling,
        )
        assert charged == pytest.approx(7.5)
    finally:
        del os.environ["BOB_PER_FEATURE_COST_CEILING"]
