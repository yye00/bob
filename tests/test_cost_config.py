"""Tests for bob.cost_config.resolve_max_cost_usd.

Covers the env-overridable per-project cost ceiling resolver:
- Default (no env var) returns the effectively-unlimited value.
- Valid numeric BOB_MAX_COST_USD is honoured.
- Malformed / edge-case values fall back to unlimited without raising.
- Return value is always a non-NaN, non-Inf float.
"""

from __future__ import annotations

import math

import pytest
from bob.models import UNLIMITED_MAX_COST_USD


UNLIMITED = UNLIMITED_MAX_COST_USD


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BOB_MAX_COST_USD", raising=False)


class TestResolveMaxCostUsdDefault:
    """Default behaviour when BOB_MAX_COST_USD is not set."""

    def test_no_env_var_returns_unlimited(self):
        from bob.cost_config import resolve_max_cost_usd

        assert resolve_max_cost_usd() == UNLIMITED

    def test_return_type_is_float(self):
        from bob.cost_config import resolve_max_cost_usd

        assert isinstance(resolve_max_cost_usd(), float)


class TestResolveMaxCostUsdWithEnv:
    """BOB_MAX_COST_USD is read and returned when set to a valid number."""

    def test_valid_integer_string(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "200")
        from bob.cost_config import resolve_max_cost_usd

        assert resolve_max_cost_usd() == pytest.approx(200.0)

    def test_valid_float_string(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "750.50")
        from bob.cost_config import resolve_max_cost_usd

        assert resolve_max_cost_usd() == pytest.approx(750.50)

    def test_zero_is_accepted(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "0")
        from bob.cost_config import resolve_max_cost_usd

        assert resolve_max_cost_usd() == 0.0

    def test_small_positive_value(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "0.01")
        from bob.cost_config import resolve_max_cost_usd

        assert resolve_max_cost_usd() == pytest.approx(0.01)

    def test_large_value_is_honoured(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "5000000")
        from bob.cost_config import resolve_max_cost_usd

        assert resolve_max_cost_usd() == pytest.approx(5_000_000.0)

    def test_negative_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "-50")
        from bob.cost_config import resolve_max_cost_usd

        assert resolve_max_cost_usd() == 0.0


class TestResolveMaxCostUsdMalformedEnv:
    """Malformed BOB_MAX_COST_USD falls back to unlimited, never raises."""

    def test_empty_string_returns_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "")
        from bob.cost_config import resolve_max_cost_usd

        assert resolve_max_cost_usd() == UNLIMITED

    def test_whitespace_only_returns_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "   ")
        from bob.cost_config import resolve_max_cost_usd

        assert resolve_max_cost_usd() == UNLIMITED

    def test_non_numeric_string_returns_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "not_a_number")
        from bob.cost_config import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result == UNLIMITED

    def test_nan_string_returns_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "NaN")
        from bob.cost_config import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result == UNLIMITED
        assert not math.isnan(result)

    def test_inf_string_returns_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "Inf")
        from bob.cost_config import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result == UNLIMITED
        assert not math.isinf(result)

    def test_none_like_string_returns_unlimited(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "None")
        from bob.cost_config import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result == UNLIMITED

    def test_malformed_never_returns_zero(self, monkeypatch):
        """Malformed env must not silently produce 0.0 — that blocks all spawns."""
        monkeypatch.setenv("BOB_MAX_COST_USD", "garbage")
        from bob.cost_config import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result != 0.0


class TestCostConfigIntegration:
    """resolve_max_cost_usd result is consistent with models.Project default."""

    def test_result_matches_project_default_when_no_env(self):
        from bob.cost_config import resolve_max_cost_usd
        from bob.models import Project

        cfg = resolve_max_cost_usd()
        p = Project(id="x", name="x", workspace_path="/tmp")
        assert p.max_cost_usd == cfg

    def test_result_matches_project_default_when_env_set(self, monkeypatch):
        monkeypatch.setenv("BOB_MAX_COST_USD", "300")
        from bob.cost_config import resolve_max_cost_usd
        from bob.models import Project

        cfg = resolve_max_cost_usd()
        p = Project(id="x", name="x", workspace_path="/tmp")
        assert p.max_cost_usd == pytest.approx(cfg)
