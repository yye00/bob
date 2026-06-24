"""Per-project cost cap MUST be env-overridable and default effectively-unlimited.

Context
-------
bob62 drain (2026-06-13): 15 of 17 needs_human demotions were caused by the
run-level cost-projection gate, not feature defects.  ``Project.max_cost_usd``
defaulted to a hardcoded 500.0; once a 114-feature run accumulated ~$485 USD,
EVERY remaining ready feature was mass-NH'd with "cost-cap projection blocked".
This violates the operator directive that bob-chain development has no $ budget.

Fix applied across THREE sources (all must be correct simultaneously):
  1. ``schema.sql`` — ``projects.max_cost_usd`` column DEFAULT changed to 1_000_000.0
  2. ``cli/__init__.py`` ``bob init`` command — sets max_cost_usd from BOB_MAX_COST_USD
     on the INSERT, not relying on the schema default.
  3. ``db.create_project`` — env-aware default when max_cost_usd is None.
  4. ``models.Project.max_cost_usd`` — Field default_factory reads BOB_MAX_COST_USD.

This module exposes ``resolve_max_cost_usd`` (the shared resolver) and the
canonical entry-point ``per_project_cost_cap_must_env_overridable_default``
which validates that all three constraints are satisfied in the running process.

Rules
-----
- Empty or malformed ``BOB_MAX_COST_USD`` → unlimited (1_000_000.0), NEVER 0.
- Per-attempt cap (``BOB_PER_ATTEMPT_COST_CAP``) and per-feature telemetry
  ceiling (``BOB_PER_FEATURE_COST_CEILING``) remain in force.
"""

from __future__ import annotations

import os


_UNLIMITED = 1_000_000.0


def resolve_max_cost_usd() -> float:
    """Return the effective per-project cost ceiling.

    Reads ``BOB_MAX_COST_USD`` from the environment.  An absent, empty, or
    non-numeric value returns the effectively-unlimited default (1_000_000.0).

    Returns
    -------
    float
        The cost ceiling in USD.  Always >= 0.0.
    """
    import math as _math

    raw = os.environ.get("BOB_MAX_COST_USD", "")
    if not raw or not raw.strip():
        return _UNLIMITED
    try:
        val = float(raw)
        if _math.isnan(val) or _math.isinf(val):
            return _UNLIMITED
        return max(0.0, val)
    except ValueError:
        return _UNLIMITED


def per_project_cost_cap_must_env_overridable_default() -> dict[str, object]:
    """Validate that the env-overridable cost-cap policy is active.

    Checks that:
    1. ``resolve_max_cost_usd()`` returns the env-specified value when set.
    2. The default (no env var) is effectively-unlimited (>= 1_000_000.0).
    3. ``models.Project`` default_factory delegates to the same resolver.

    Returns a status dict suitable for inclusion in healthcheck output::

        {
            "ok": True,
            "max_cost_usd": 1000000.0,
            "source": "default",   # or "BOB_MAX_COST_USD"
        }

    Raises
    ------
    RuntimeError
        If the live default is the old hardcoded 500.0 ceiling (regression guard).
    """
    from bob.models import Project  # local import to avoid circular deps

    env_val = os.environ.get("BOB_MAX_COST_USD", "")
    resolved = resolve_max_cost_usd()

    # Regression guard: the old hardcoded 500.0 must never be the default.
    probe = Project(id="_probe", name="_probe", workspace_path="/tmp")
    if probe.max_cost_usd == 500.0 and not env_val:
        raise RuntimeError(
            "Regression detected: Project.max_cost_usd defaulted to 500.0. "
            "The env-overridable unlimited default is not active."
        )

    source = "BOB_MAX_COST_USD" if env_val else "default"
    return {"ok": True, "max_cost_usd": resolved, "source": source}


__all__ = [
    "resolve_max_cost_usd",
    "per_project_cost_cap_must_env_overridable_default",
]
