"""Bootstrap readiness override — one bypass execute per feature.

Exposes a single predicate that determines whether a feature may bypass
the readiness gate exactly once.

The bypass resolves the self-referential deadlock where a feature is stuck at
a low readiness_score with research_iterations==0: research cannot lift the
score because there is no execution signal, and execution is blocked because
the score is too low.

Conditions for the bypass:
  - bootstrap_attempts < 1  (haven't used the bypass yet)
  - research_iterations == 0  (no research signal exists yet)
"""

from __future__ import annotations

from bob3.models import Feature

_MAX_BOOTSTRAP_ATTEMPTS = 1


def check_bootstrap_override(feature: Feature) -> bool:
    """Return True if this feature may bypass the readiness gate once.

    A feature is eligible for a bootstrap bypass when it has never been
    researched (research_iterations == 0) and the single allowed bypass has
    not yet been consumed (bootstrap_attempts < 1).

    Raises ValueError if bootstrap_attempts or research_iterations is negative.

    Args:
        feature: The Feature instance to evaluate.

    Returns:
        True if the caller should allow one execution despite a failing
        readiness gate; False if the gate should be respected normally.
    """
    bootstrap_attempts = feature.bootstrap_attempts or 0
    research_iterations = feature.research_iterations or 0

    if bootstrap_attempts < 0:
        raise ValueError(
            f"bootstrap_attempts must be non-negative, got {bootstrap_attempts}"
        )
    if research_iterations < 0:
        raise ValueError(
            f"research_iterations must be non-negative, got {research_iterations}"
        )

    return bootstrap_attempts < _MAX_BOOTSTRAP_ATTEMPTS and research_iterations == 0


def check_bootstrap_readiness_override(feature: Feature) -> bool:
    """Return True if this feature may bypass the readiness gate once.

    Canonical entry point for the bootstrap readiness override predicate.
    A feature may bypass the readiness gate exactly once when:
      - bootstrap_attempts < 1  (the single bypass has not been consumed)
      - research_iterations == 0  (no research signal exists yet)

    Raises ValueError if bootstrap_attempts or research_iterations is negative.

    Args:
        feature: The Feature instance to evaluate.

    Returns:
        True if the caller should allow one execution despite a failing
        readiness gate; False if the gate should be respected normally.
    """
    return check_bootstrap_override(feature)
