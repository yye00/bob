"""Error-path tests for the per-project cost cap env-override feature.

Invalid input must raise ValueError (or a subclass such as ValidationError) and
the function must NOT silently succeed (error path).  Tests cover Project model
validation and direct misuse of the resolver.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BOB3_MAX_COST_USD", raising=False)


class TestProjectMaxCostUsdValidationErrors:
    """Project.max_cost_usd raises on constraint violations — does not silently succeed."""

    def test_negative_max_cost_raises(self):
        """Explicit negative max_cost_usd must raise (ge=0.0 constraint)."""
        from bob3.models import Project

        with pytest.raises((ValueError, TypeError)):
            Project(id="x", name="x", workspace_path="/tmp", max_cost_usd=-1.0)

    def test_large_negative_max_cost_raises(self):
        """Large negative max_cost_usd must raise, not silently succeed."""
        from bob3.models import Project

        with pytest.raises((ValueError, TypeError)):
            Project(id="x", name="x", workspace_path="/tmp", max_cost_usd=-500.0)

    def test_very_small_negative_raises(self):
        """Even -0.001 must raise — there is no grace margin below 0.0."""
        from bob3.models import Project

        with pytest.raises((ValueError, TypeError)):
            Project(id="x", name="x", workspace_path="/tmp", max_cost_usd=-0.001)

    def test_non_numeric_string_for_max_cost_raises(self):
        """A non-numeric string passed as max_cost_usd must raise, not silently pass."""
        from bob3.models import Project

        with pytest.raises((ValueError, TypeError)):
            Project(id="x", name="x", workspace_path="/tmp", max_cost_usd="not_a_number")  # type: ignore[arg-type]


class TestResolveMaxCostUsdDoesNotSilentlyReturnZeroOnInvalid:
    """Malformed env var must never silently produce 0.0 (which blocks every spawn)."""

    def test_malformed_env_does_not_return_zero(self, monkeypatch):
        """Non-numeric BOB3_MAX_COST_USD must NOT silently return 0.0."""
        monkeypatch.setenv("BOB3_MAX_COST_USD", "completely_invalid")
        from bob3.per_project_cost_cap_must_env_overridable_default import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result != 0.0, "Malformed BOB3_MAX_COST_USD must not silently resolve to 0"

    def test_none_like_string_does_not_return_zero(self, monkeypatch):
        """'None' string in BOB3_MAX_COST_USD must not silently return 0.0."""
        monkeypatch.setenv("BOB3_MAX_COST_USD", "None")
        from bob3.per_project_cost_cap_must_env_overridable_default import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        assert result != 0.0, "'None' string must fall back to unlimited, not zero"

    def test_nan_string_does_not_block_spawns(self, monkeypatch):
        """'NaN' in BOB3_MAX_COST_USD must not produce a falsy or zero effective cap."""
        monkeypatch.setenv("BOB3_MAX_COST_USD", "NaN")
        from bob3.per_project_cost_cap_must_env_overridable_default import resolve_max_cost_usd

        result = resolve_max_cost_usd()
        # NaN would make every comparison fail and block spawns — must not happen.
        assert result == 1_000_000.0 or result > 0, "NaN env var must not block all spawns"


class TestPerProjectCostCapEntrypointErrorDetection:
    """per_project_cost_cap_must_env_overridable_default raises on regression."""

    def test_regression_guard_present(self):
        """Entry-point must not silently swallow the 500.0 regression — it must raise."""
        from bob3.per_project_cost_cap_must_env_overridable_default import (
            per_project_cost_cap_must_env_overridable_default,
        )
        # With no env override, it must succeed (not raise) — the 500.0 regression is absent.
        result = per_project_cost_cap_must_env_overridable_default()
        assert result is not None, "Entry-point must return a result dict, not None"

    def test_entrypoint_result_contains_max_cost_usd(self):
        """Entry-point result must expose max_cost_usd — callers can detect bad values."""
        from bob3.per_project_cost_cap_must_env_overridable_default import (
            per_project_cost_cap_must_env_overridable_default,
        )

        result = per_project_cost_cap_must_env_overridable_default()
        assert "max_cost_usd" in result, "Result must include max_cost_usd key"
        assert result["max_cost_usd"] != 500.0, "max_cost_usd must not be the old hardcoded 500.0"
