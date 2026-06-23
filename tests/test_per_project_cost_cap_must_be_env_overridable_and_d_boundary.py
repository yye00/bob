"""Boundary tests for the per-project cost cap env-override feature.

Empty, zero, or minimum input returns a well-defined result rather than raising
(boundary case).  Specifically tests resolve_max_cost_usd() and
Project.max_cost_usd with edge-case BOB3_MAX_COST_USD values.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BOB3_MAX_COST_USD", raising=False)


class TestResolveMaxCostUsdBoundary:
    """resolve_max_cost_usd() returns well-defined floats for boundary inputs."""

    def test_no_env_var_returns_unlimited(self):
        """Absent BOB3_MAX_COST_USD → 1_000_000.0, does not raise."""
        from bob3.per_project_cost_cap_must_env_overridable_default import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result == 1_000_000.0

    def test_empty_string_env_var_returns_unlimited(self, monkeypatch):
        """Empty BOB3_MAX_COST_USD → 1_000_000.0, does not raise."""
        monkeypatch.setenv("BOB3_MAX_COST_USD", "")
        from bob3.per_project_cost_cap_must_env_overridable_default import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result == 1_000_000.0
        assert result != 0.0

    def test_zero_env_var_returns_zero(self, monkeypatch):
        """BOB3_MAX_COST_USD=0 → 0.0, does not raise (explicit user budget of 0)."""
        monkeypatch.setenv("BOB3_MAX_COST_USD", "0")
        from bob3.per_project_cost_cap_must_env_overridable_default import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result == 0.0

    def test_minimum_positive_env_var_returns_that_value(self, monkeypatch):
        """Very small positive BOB3_MAX_COST_USD (0.01) → 0.01, does not raise."""
        monkeypatch.setenv("BOB3_MAX_COST_USD", "0.01")
        from bob3.per_project_cost_cap_must_env_overridable_default import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result == pytest.approx(0.01)

    def test_negative_env_var_clamped_to_zero(self, monkeypatch):
        """Negative BOB3_MAX_COST_USD is clamped to 0.0, does not raise."""
        monkeypatch.setenv("BOB3_MAX_COST_USD", "-100")
        from bob3.per_project_cost_cap_must_env_overridable_default import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result == 0.0

    def test_whitespace_only_env_var_returns_unlimited(self, monkeypatch):
        """Whitespace-only BOB3_MAX_COST_USD → unlimited (treats as empty), does not raise."""
        monkeypatch.setenv("BOB3_MAX_COST_USD", "   ")
        from bob3.per_project_cost_cap_must_env_overridable_default import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result == 1_000_000.0

    def test_return_value_is_always_float(self, monkeypatch):
        """Return value is always a float regardless of input."""
        from bob3.per_project_cost_cap_must_env_overridable_default import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert isinstance(result, float)


class TestProjectMaxCostUsdBoundary:
    """Project.max_cost_usd handles boundary default values without raising."""

    def test_project_default_unlimited_when_no_env(self):
        """Project created without explicit max_cost_usd gets unlimited default."""
        from bob3.models import Project

        p = Project(id="test-id", name="test", workspace_path="/tmp")
        assert p.max_cost_usd == 1_000_000.0

    def test_project_explicit_zero_max_cost_is_accepted(self):
        """Project created with explicit max_cost_usd=0.0 does not raise."""
        from bob3.models import Project

        p = Project(id="test-id", name="test", workspace_path="/tmp", max_cost_usd=0.0)
        assert p.max_cost_usd == 0.0

    def test_project_minimum_positive_max_cost_is_accepted(self):
        """Project created with max_cost_usd=0.01 does not raise."""
        from bob3.models import Project

        p = Project(id="test-id", name="test", workspace_path="/tmp", max_cost_usd=0.01)
        assert p.max_cost_usd == pytest.approx(0.01)


class TestPerProjectCostCapEntrypointBoundary:
    """per_project_cost_cap_must_env_overridable_default() handles boundary env cleanly."""

    def test_entrypoint_no_env_returns_ok(self):
        """Entry-point with no env var returns ok=True, does not raise."""
        from bob3.per_project_cost_cap_must_env_overridable_default import (
            per_project_cost_cap_must_env_overridable_default,
        )

        result = per_project_cost_cap_must_env_overridable_default()
        assert result["ok"] is True

    def test_entrypoint_empty_env_returns_ok(self, monkeypatch):
        """Entry-point with empty BOB3_MAX_COST_USD returns ok=True, does not raise."""
        monkeypatch.setenv("BOB3_MAX_COST_USD", "")
        from bob3.per_project_cost_cap_must_env_overridable_default import (
            per_project_cost_cap_must_env_overridable_default,
        )

        result = per_project_cost_cap_must_env_overridable_default()
        assert result["ok"] is True

    def test_entrypoint_zero_env_returns_ok(self, monkeypatch):
        """Entry-point with BOB3_MAX_COST_USD=0 returns ok=True, does not raise."""
        monkeypatch.setenv("BOB3_MAX_COST_USD", "0")
        from bob3.per_project_cost_cap_must_env_overridable_default import (
            per_project_cost_cap_must_env_overridable_default,
        )

        result = per_project_cost_cap_must_env_overridable_default()
        assert result["ok"] is True
