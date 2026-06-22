"""Tests for bob3.orchestrator.cost_ceiling.compute_per_feature_ceiling.

AC: pytest: tests/test_cost_ceiling.py
AC: Function defined: bob3.orchestrator.cost_ceiling.compute_per_feature_ceiling
"""

from __future__ import annotations

import os

import pytest

from bob3.orchestrator.cost_ceiling import compute_per_feature_ceiling


class TestComputePerFeatureCeiling:
    """Tests for compute_per_feature_ceiling."""

    def test_returns_default_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("BOB3_PER_FEATURE_COST_CEILING", raising=False)
        result = compute_per_feature_ceiling()
        assert result == pytest.approx(20.0)

    def test_returns_float(self, monkeypatch):
        monkeypatch.delenv("BOB3_PER_FEATURE_COST_CEILING", raising=False)
        assert isinstance(compute_per_feature_ceiling(), float)

    def test_env_override_positive_float(self, monkeypatch):
        monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "5.0")
        assert compute_per_feature_ceiling() == pytest.approx(5.0)

    def test_env_override_integer_string(self, monkeypatch):
        monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "10")
        assert compute_per_feature_ceiling() == pytest.approx(10.0)

    def test_env_invalid_string_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "not-a-number")
        assert compute_per_feature_ceiling() == pytest.approx(20.0)

    def test_env_zero_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "0")
        assert compute_per_feature_ceiling() == pytest.approx(20.0)

    def test_env_negative_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "-5.0")
        assert compute_per_feature_ceiling() == pytest.approx(20.0)

    def test_env_empty_string_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BOB3_PER_FEATURE_COST_CEILING", "")
        assert compute_per_feature_ceiling() == pytest.approx(20.0)

    def test_default_ceiling_is_sane_for_per_feature_use(self, monkeypatch):
        """Default must be << project budget (e.g. $10M). $20 is the p95 empirical value."""
        monkeypatch.delenv("BOB3_PER_FEATURE_COST_CEILING", raising=False)
        ceiling = compute_per_feature_ceiling()
        # Must be much smaller than any realistic project budget
        assert ceiling < 1_000.0
        assert ceiling > 0.0

    def test_result_is_always_positive(self, monkeypatch):
        monkeypatch.delenv("BOB3_PER_FEATURE_COST_CEILING", raising=False)
        assert compute_per_feature_ceiling() > 0.0
