"""Bootstrap readiness override — one bypass execute per feature.

Exposes a predicate that determines whether a feature may bypass
the readiness gate exactly once.

The bypass resolves the self-referential deadlock where a feature is stuck at
a low readiness_score with research_iterations==0: research cannot lift the
score because there is no execution signal, and execution is blocked because
the score is too low.

Conditions for the bypass (all must be true):
  - bootstrap_attempts < 1  (haven't used the bypass yet)
  - research_iterations == 0  (no research signal exists yet)
"""

from __future__ import annotations

from bob.models import Feature

_MAX_BOOTSTRAP_ATTEMPTS = 1


def check_bootstrap_bypass(feature: Feature) -> bool:
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
    bootstrap_attempts = feature.bootstrap_attempts if feature.bootstrap_attempts is not None else 0
    research_iterations = feature.research_iterations if feature.research_iterations is not None else 0

    if bootstrap_attempts < 0:
        raise ValueError(
            f"bootstrap_attempts must be non-negative, got {bootstrap_attempts}"
        )
    if research_iterations < 0:
        raise ValueError(
            f"research_iterations must be non-negative, got {research_iterations}"
        )

    return bootstrap_attempts < _MAX_BOOTSTRAP_ATTEMPTS and research_iterations == 0


def should_bypass_readiness_gate(feature: Feature) -> bool:
    """Return True if the readiness gate should be bypassed for this feature.

    This is the canonical entry point for the bootstrap readiness override.
    A feature may bypass the readiness gate exactly once when:
      - bootstrap_attempts < 1  (the single bypass has not been consumed)
      - research_iterations == 0  (no research signal exists yet)

    Args:
        feature: The Feature instance to evaluate.

    Returns:
        True if one bypass execution should be allowed despite the gate;
        False if the gate should be enforced normally.

    Raises:
        ValueError: If bootstrap_attempts or research_iterations is negative.
    """
    return check_bootstrap_bypass(feature)


def increment_bootstrap_attempts(current: int) -> int:
    """Return the incremented bootstrap_attempts counter (current + 1).

    Args:
        current: The current bootstrap_attempts value (must be >= 0).

    Returns:
        current + 1

    Raises:
        ValueError: If current is negative (counter invariant violation).
    """
    if current < 0:
        raise ValueError(
            f"bootstrap_attempts must be non-negative, got {current}"
        )
    return current + 1


def decrement_bootstrap_attempts(current: int) -> int:
    """Return the decremented bootstrap_attempts counter (current - 1), clamped to 0.

    Semantically "gives back" a bootstrap attempt that was reserved but not
    consumed (e.g. the bypass was granted but the execution was aborted before
    the attempt was spent).  The counter is clamped at 0 because negative
    attempt counts are invalid.

    Args:
        current: The current bootstrap_attempts value (must be >= 0).

    Returns:
        max(0, current - 1)

    Raises:
        ValueError: If current is negative (counter invariant violation).
    """
    if current < 0:
        raise ValueError(
            f"bootstrap_attempts must be non-negative, got {current}"
        )
    return max(0, current - 1)
