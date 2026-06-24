"""Tests for bob3.orchestrator.per_feature_ceiling.compute_per_feature_ceiling.

AC: pytest: tests/test_per_feature_ceiling.py
    File exists: src/bob3/orchestrator/per_feature_ceiling.py
    Function defined: bob3.orchestrator.per_feature_ceiling.compute_per_feature_ceiling
"""

from __future__ import annotations

import os

import pytest

from bob3.orchestrator.per_feature_ceiling import compute_per_feature_ceiling


_ENV = "BOB3_PER_FEATURE_COST_CEILING"


# ---------------------------------------------------------------------------
# Default behaviour (env var absent)
# ---------------------------------------------------------------------------

def test_default_ceiling_when_env_unset(monkeypatch):
    """Returns the $20 default when the env var is not set."""
    monkeypatch.delenv(_ENV, raising=False)
    assert compute_per_feature_ceiling() == pytest.approx(20.0)


def test_return_type_is_float_default(monkeypatch):
    """Return type is float when falling back to default."""
    monkeypatch.delenv(_ENV, raising=False)
    result = compute_per_feature_ceiling()
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Valid env-var overrides
# ---------------------------------------------------------------------------

def test_env_override_small_value(monkeypatch):
    """Env override of 5.0 is returned as 5.0."""
    monkeypatch.setenv(_ENV, "5.0")
    assert compute_per_feature_ceiling() == pytest.approx(5.0)


def test_env_override_large_value(monkeypatch):
    """Env override of 100.0 is returned as 100.0."""
    monkeypatch.setenv(_ENV, "100.0")
    assert compute_per_feature_ceiling() == pytest.approx(100.0)


def test_env_override_integer_string(monkeypatch):
    """Integer string '10' is valid and returns 10.0."""
    monkeypatch.setenv(_ENV, "10")
    assert compute_per_feature_ceiling() == pytest.approx(10.0)


def test_return_type_is_float_with_env_override(monkeypatch):
    """Return type is float when env var is set."""
    monkeypatch.setenv(_ENV, "15.0")
    result = compute_per_feature_ceiling()
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Fallback to default for invalid/non-positive env values
# ---------------------------------------------------------------------------

def test_non_numeric_env_falls_back_to_default(monkeypatch):
    """Non-numeric env value falls back to default ($20) without raising."""
    monkeypatch.setenv(_ENV, "not-a-number")
    assert compute_per_feature_ceiling() == pytest.approx(20.0)


def test_empty_string_env_falls_back_to_default(monkeypatch):
    """Empty string env value falls back to default ($20) without raising."""
    monkeypatch.setenv(_ENV, "")
    assert compute_per_feature_ceiling() == pytest.approx(20.0)


def test_zero_env_falls_back_to_default(monkeypatch):
    """Zero is not a positive ceiling; falls back to default."""
    monkeypatch.setenv(_ENV, "0")
    assert compute_per_feature_ceiling() == pytest.approx(20.0)


def test_negative_env_falls_back_to_default(monkeypatch):
    """Negative ceiling is invalid; falls back to default."""
    monkeypatch.setenv(_ENV, "-5.0")
    assert compute_per_feature_ceiling() == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Result is always positive
# ---------------------------------------------------------------------------

def test_result_is_always_positive_default(monkeypatch):
    """Returned ceiling is always > 0.0 (default path)."""
    monkeypatch.delenv(_ENV, raising=False)
    assert compute_per_feature_ceiling() > 0.0


def test_result_is_always_positive_with_env(monkeypatch):
    """Returned ceiling is always > 0.0 (env override path)."""
    monkeypatch.setenv(_ENV, "7.5")
    assert compute_per_feature_ceiling() > 0.0


def test_result_is_always_positive_on_invalid_env(monkeypatch):
    """Returned ceiling is always > 0.0 even when env is invalid."""
    monkeypatch.setenv(_ENV, "garbage")
    assert compute_per_feature_ceiling() > 0.0


# ---------------------------------------------------------------------------
# Integration: ceiling is suitable for apply_pessimistic_cost
# ---------------------------------------------------------------------------

def test_ceiling_is_finite(monkeypatch):
    """The returned ceiling is a finite (non-inf, non-nan) float."""
    import math

    monkeypatch.delenv(_ENV, raising=False)
    result = compute_per_feature_ceiling()
    assert math.isfinite(result)


def test_ceiling_with_env_is_finite(monkeypatch):
    """Env-overridden ceiling is finite."""
    import math

    monkeypatch.setenv(_ENV, "25.0")
    result = compute_per_feature_ceiling()
    assert math.isfinite(result)
