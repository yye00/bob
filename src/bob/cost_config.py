"""Per-project cost cap configuration — env-overridable resolver.

Exposes ``resolve_max_cost_usd``, the single source-of-truth for the
effective per-project cost ceiling.  All subsystems (models, db, orchestrator)
delegate to this function so the policy is consistent.

Rules
-----
- ``BOB_MAX_COST_USD`` absent/empty/whitespace → canonical ``1.0e300`` sentinel.
- NaN or Inf value → canonical ``1.0e300`` sentinel.
- Malformed string → canonical ``1.0e300`` sentinel, never 0.
- Valid numeric value → clamped to >= 0.0.
- Per-attempt cap (``BOB_PER_ATTEMPT_COST_CAP``) and per-feature telemetry
  ceiling (``BOB_PER_FEATURE_COST_CEILING``) remain in force; only the
  run-level project ceiling is made env-overridable here.
"""

from __future__ import annotations

from bob.models import UNLIMITED_MAX_COST_USD, resolve_max_cost_usd


__all__ = ["UNLIMITED_MAX_COST_USD", "resolve_max_cost_usd"]
