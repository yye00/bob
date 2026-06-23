"""Boundary-case tests: empty, zero, or minimum input returns well-defined result.

AC: pytest: tests/test_composite_spec_quality_score_8_sub_metrics_geometr_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than
    raising (boundary case).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec_quality.composite_score import SUB_METRIC_WEIGHTS, compute_spec_quality_score


def _all_metrics(value: float) -> dict:
    return {k: value for k in SUB_METRIC_WEIGHTS}


def test_zero_all_metrics_returns_score_zero_not_raise():
    """All metrics at 0.0 — returns refuse with score 0.0 rather than raising."""
    result = compute_spec_quality_score(_all_metrics(0.0))
    assert isinstance(result, dict)
    assert result["score"] == pytest.approx(0.0, abs=1e-9)
    assert result["gate"] == "refuse"


def test_minimum_nonzero_returns_defined_score():
    """Very small nonzero values produce a defined float, not an exception."""
    result = compute_spec_quality_score(_all_metrics(1e-10))
    assert isinstance(result, dict)
    assert isinstance(result["score"], float)
    assert result["gate"] == "refuse"


def test_exactly_zero_single_metric_returns_zero_score():
    """One metric at exactly zero drives the whole score to 0.0 (geometric mean property)."""
    metrics = _all_metrics(0.9)
    metrics["ac_atomicity"] = 0.0
    result = compute_spec_quality_score(metrics)
    assert result["score"] == pytest.approx(0.0, abs=1e-9)
    assert result["gate"] == "refuse"


def test_boundary_0_65_returns_warn_not_refuse():
    """Score exactly at 0.65 is warn, not refuse (inclusive lower bound for warn)."""
    result = compute_spec_quality_score(_all_metrics(0.65))
    assert result["score"] == pytest.approx(0.65, abs=1e-5)
    assert result["gate"] == "warn"


def test_boundary_0_80_returns_green_not_warn():
    """Score exactly at 0.80 is green, not warn (inclusive lower bound for green)."""
    result = compute_spec_quality_score(_all_metrics(0.80))
    assert result["score"] == pytest.approx(0.80, abs=1e-5)
    assert result["gate"] == "green"


def test_all_ones_returns_score_one_green():
    """Maximum input (1.0) yields score 1.0 and gate 'green'."""
    result = compute_spec_quality_score(_all_metrics(1.0))
    assert result["score"] == pytest.approx(1.0, abs=1e-9)
    assert result["gate"] == "green"


def test_over_one_clamped_returns_score_at_most_one():
    """Values above 1.0 are clamped; result is well-defined and score <= 1.0."""
    result = compute_spec_quality_score(_all_metrics(2.0))
    assert isinstance(result, dict)
    assert result["score"] <= 1.0


def test_just_below_0_65_returns_refuse():
    """Score just below 0.65 yields refuse, not warn."""
    result = compute_spec_quality_score(_all_metrics(0.64))
    assert result["score"] < 0.65
    assert result["gate"] == "refuse"


def test_just_below_0_80_returns_warn():
    """Score just below 0.80 yields warn, not green."""
    result = compute_spec_quality_score(_all_metrics(0.79))
    assert result["score"] < 0.80
    assert result["gate"] == "warn"
