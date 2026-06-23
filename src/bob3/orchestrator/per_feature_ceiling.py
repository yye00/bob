"""Per-feature cost ceiling computation.

Centralises the logic for deriving a sane per-feature pessimistic-cost
ceiling so that telemetry-loss never charges the *entire* project budget
for a single feature attempt.

The empirical p95 of real per-feature costs observed in bob3 v.16/17 runs
is ~$20.  That is the default; operators can override via the environment
variable ``BOB3_PER_FEATURE_COST_CEILING``.
"""

from __future__ import annotations

import os

_DEFAULT_CEILING: float = 20.0
_ENV_VAR: str = "BOB3_PER_FEATURE_COST_CEILING"


def compute_per_feature_ceiling() -> float:
    """Return the per-feature cost ceiling in USD.

    The value is read from the environment variable
    ``BOB3_PER_FEATURE_COST_CEILING``.  If the variable is unset or
    cannot be parsed as a positive float, the built-in default of
    ``$20.00`` is used instead.

    Returns
    -------
    float
        A positive USD ceiling suitable for passing to
        :func:`bob3.orchestrator.cost_telemetry_guard.apply_pessimistic_cost`
        as ``per_feature_ceiling``.

    Raises
    ------
    ValueError
        Never raised — invalid env values fall back to the default.

    Examples
    --------
    >>> import os
    >>> os.environ.pop("BOB3_PER_FEATURE_COST_CEILING", None)
    >>> compute_per_feature_ceiling()
    20.0
    >>> os.environ["BOB3_PER_FEATURE_COST_CEILING"] = "5.0"
    >>> compute_per_feature_ceiling()
    5.0
    """
    raw = os.environ.get(_ENV_VAR)
    if raw is None:
        return _DEFAULT_CEILING
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_CEILING
    if value <= 0.0:
        return _DEFAULT_CEILING
    return value
