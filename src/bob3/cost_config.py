"""Per-project cost cap configuration — env-overridable resolver.

Exposes ``resolve_max_cost_usd``, the single source-of-truth for the
effective per-project cost ceiling.  All subsystems (models, db, orchestrator)
delegate to this function so the policy is consistent.

Rules
-----
- ``BOB3_MAX_COST_USD`` absent/empty/whitespace → 1_000_000.0 (unlimited).
- NaN or Inf value → 1_000_000.0 (unlimited).
- Malformed string → 1_000_000.0 (unlimited, NEVER 0 — zero blocks all spawns).
- Valid numeric value → clamped to >= 0.0.
- Per-attempt cap (``BOB3_PER_ATTEMPT_COST_CAP``) and per-feature telemetry
  ceiling (``BOB3_PER_FEATURE_COST_CEILING``) remain in force; only the
  run-level project ceiling is made env-overridable here.
"""

from __future__ import annotations

import math
import os


_UNLIMITED: float = 1_000_000.0


def resolve_max_cost_usd() -> float:
    """Return the effective per-project cost ceiling in USD.

    Reads ``BOB3_MAX_COST_USD`` from the environment.  Falls back to the
    effectively-unlimited default (1_000_000.0) for any absent, empty,
    whitespace-only, non-numeric, NaN, or Inf value.

    Returns
    -------
    float
        Cost ceiling in USD.  Always >= 0.0.  Never NaN or Inf.
    """
    raw = os.environ.get("BOB3_MAX_COST_USD", "")
    if not raw or not raw.strip():
        return _UNLIMITED
    try:
        val = float(raw)
        if math.isnan(val) or math.isinf(val):
            return _UNLIMITED
        return max(0.0, val)
    except ValueError:
        return _UNLIMITED


__all__ = ["resolve_max_cost_usd"]
