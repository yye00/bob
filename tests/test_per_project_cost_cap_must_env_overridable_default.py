"""Tests for per_project_cost_cap_must_env_overridable_default feature.

Validates that the per-project cost cap (Project.max_cost_usd) is:
- env-overridable via BOB3_MAX_COST_USD
- defaults to effectively-unlimited (1_000_000.0) when env var is absent
- never defaults to the old hardcoded 500.0 ceiling
- rejects empty/malformed BOB3_MAX_COST_USD gracefully (falls back to unlimited)
"""

import importlib
import os

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove BOB3_MAX_COST_USD from env before each test."""
    monkeypatch.delenv("BOB3_MAX_COST_USD", raising=False)


# ---------------------------------------------------------------------------
# AC: Function defined
# ---------------------------------------------------------------------------


def test_per_project_cost_cap_must_env_overridable_default():
    """The public entry-point is importable and callable."""
    from bob3.per_project_cost_cap_must_env_overridable_default import (
        per_project_cost_cap_must_env_overridable_default,
    )

    assert callable(per_project_cost_cap_must_env_overridable_default)


# ---------------------------------------------------------------------------
# Behavioural tests
# ---------------------------------------------------------------------------


def test_default_is_effectively_unlimited_no_env_var():
    """Without BOB3_MAX_COST_USD, resolve_max_cost_usd() returns 1_000_000."""
    from bob3.per_project_cost_cap_must_env_overridable_default import (
        resolve_max_cost_usd,
    )

    assert resolve_max_cost_usd() == 1_000_000.0


def test_default_is_not_500():
    """Default must NOT be the old hardcoded 500.0 ceiling."""
    from bob3.per_project_cost_cap_must_env_overridable_default import (
        resolve_max_cost_usd,
    )

    assert resolve_max_cost_usd() != 500.0


def test_env_var_overrides_default(monkeypatch):
    """When BOB3_MAX_COST_USD=250, resolve_max_cost_usd() returns 250.0."""
    monkeypatch.setenv("BOB3_MAX_COST_USD", "250")
    from bob3.per_project_cost_cap_must_env_overridable_default import (
        resolve_max_cost_usd,
    )

    assert resolve_max_cost_usd() == 250.0


def test_env_var_float_value(monkeypatch):
    """Decimal values in BOB3_MAX_COST_USD are accepted correctly."""
    monkeypatch.setenv("BOB3_MAX_COST_USD", "1500.75")
    from bob3.per_project_cost_cap_must_env_overridable_default import (
        resolve_max_cost_usd,
    )

    assert resolve_max_cost_usd() == 1500.75


def test_empty_env_var_falls_back_to_unlimited(monkeypatch):
    """An empty BOB3_MAX_COST_USD must fall back to unlimited, not zero."""
    monkeypatch.setenv("BOB3_MAX_COST_USD", "")
    from bob3.per_project_cost_cap_must_env_overridable_default import (
        resolve_max_cost_usd,
    )

    result = resolve_max_cost_usd()
    assert result == 1_000_000.0
    assert result != 0.0


def test_malformed_env_var_falls_back_to_unlimited(monkeypatch):
    """A non-numeric BOB3_MAX_COST_USD must fall back to unlimited, not raise."""
    monkeypatch.setenv("BOB3_MAX_COST_USD", "not_a_number")
    from bob3.per_project_cost_cap_must_env_overridable_default import (
        resolve_max_cost_usd,
    )

    result = resolve_max_cost_usd()
    assert result == 1_000_000.0


def test_zero_env_var_not_blocked(monkeypatch):
    """BOB3_MAX_COST_USD=0 is valid (user explicitly set budget to 0), but
    empty/malformed must NOT produce 0 (that would block every spawn)."""
    monkeypatch.setenv("BOB3_MAX_COST_USD", "0")
    from bob3.per_project_cost_cap_must_env_overridable_default import (
        resolve_max_cost_usd,
    )

    # Explicit 0 is honored; empty/malformed handled by other tests
    assert resolve_max_cost_usd() == 0.0


def test_models_project_default_uses_env(monkeypatch):
    """Project.max_cost_usd default_factory reads BOB3_MAX_COST_USD."""
    monkeypatch.setenv("BOB3_MAX_COST_USD", "999")
    # Re-import needed to pick up env change in default_factory
    import bob3.models as _models
    importlib.reload(_models)
    try:
        p = _models.Project(id="x", name="x", workspace_path="/tmp")
        assert p.max_cost_usd == 999.0
    finally:
        importlib.reload(_models)


def test_models_project_default_unlimited_without_env():
    """Project.max_cost_usd defaults to 1_000_000 when env var is absent."""
    import bob3.models as _models
    importlib.reload(_models)
    p = _models.Project(id="x", name="x", workspace_path="/tmp")
    assert p.max_cost_usd == 1_000_000.0
    assert p.max_cost_usd != 500.0
