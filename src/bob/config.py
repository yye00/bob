"""bob.config — Central configuration resolver for Bob.

Exposes ``get_max_cost_usd``, the canonical entry-point for reading the
per-project cost ceiling.  All subsystems should call this rather than
reaching directly into the environment.

See ``bob.cost_config.resolve_max_cost_usd`` for the low-level resolver.
"""

from __future__ import annotations

from bob.cost_config import resolve_max_cost_usd


def get_max_cost_usd() -> float:
    """Return the effective per-project cost ceiling in USD.

    Reads ``BOB_MAX_COST_USD`` from the environment.  An absent, empty,
    whitespace-only, non-numeric, NaN, or Inf value returns the effectively-
    unlimited default (1_000_000.0).  A valid numeric value is clamped to
    >= 0.0.  Never returns 0.0 for a malformed env var (which would block
    every spawn).

    Returns
    -------
    float
        Cost ceiling in USD.  Always >= 0.0.  Never NaN or Inf.
    """
    return resolve_max_cost_usd()


__all__ = ["get_max_cost_usd"]
