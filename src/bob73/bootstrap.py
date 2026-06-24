"""Bootstrap readiness override — one bypass execute per feature (bob73).

Exposes check_bootstrap_readiness, a predicate that determines whether a
feature may bypass the readiness gate exactly once.

Conditions for bypass (all must hold):
  - bootstrap_attempts < 1   (haven't used the bypass yet)
  - research_iterations == 0 (no research signal exists yet)

Negative counter values are invalid and raise ValueError.

Integrates with bob.feature_timeout: the timeout contract applies to any
bypass execution so hung subagents are still cancelled at the hard
wall-clock deadline set by resolve_feature_timeout_seconds().
"""

from __future__ import annotations

from bob.feature_timeout import resolve_feature_timeout_seconds  # noqa: F401 — integration
from bob.models import Feature

_MAX_BOOTSTRAP_ATTEMPTS = 1


def check_bootstrap_readiness(feature: Feature) -> bool:
    """Return True if this feature may bypass the readiness gate once.

    A feature is eligible for a bootstrap bypass when it has never been
    researched (research_iterations == 0) and the single allowed bypass has
    not yet been consumed (bootstrap_attempts < 1).

    Args:
        feature: The Feature instance to evaluate.

    Returns:
        True if the caller should allow one execution despite a failing
        readiness gate; False if the gate should be respected normally.

    Raises:
        ValueError: If bootstrap_attempts or research_iterations is negative.
    """
    bootstrap_attempts: int = feature.bootstrap_attempts or 0
    research_iterations: int = feature.research_iterations or 0

    if bootstrap_attempts < 0:
        raise ValueError(
            f"bootstrap_attempts cannot be negative: got {bootstrap_attempts}"
        )
    if research_iterations < 0:
        raise ValueError(
            f"research_iterations cannot be negative: got {research_iterations}"
        )

    return bootstrap_attempts < _MAX_BOOTSTRAP_ATTEMPTS and research_iterations == 0
