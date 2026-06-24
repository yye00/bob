"""Bootstrap readiness override — one bypass execute per feature (d0ce1fba).

Resolves the self-referential deadlock where a feature is stuck at a low
readiness_score with research_iterations==0: research cannot lift the score
because there is no execution signal, and execution is blocked because the
score is too low.

The fix: allow exactly ONE bypass of the readiness gate per feature when:
  - The readiness gate would normally block execution
  - bootstrap_attempts < 1  (haven't used the bypass yet)
  - research_iterations == 0  (no research signal exists yet)

After the bypass execution, the result becomes the seed signal for the next
research pass. ``bootstrap_attempts`` is then 1, so the bypass cannot fire
again for this feature.
"""

from __future__ import annotations

from bob3.models import Feature

_MAX_BOOTSTRAP_ATTEMPTS = 1


def bootstrap_attempt_allowed(feature: Feature) -> bool:
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


def should_allow_bootstrap_bypass(feature: Feature) -> bool:
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


def check_bootstrap_override(feature: Feature) -> bool:
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


def increment_bootstrap_attempts(current: int) -> int:
    """Return the incremented bootstrap_attempts counter.

    Args:
        current: The current bootstrap_attempts value.

    Returns:
        current + 1

    Raises:
        ValueError: If current is negative (counter invariant violation).
    """
    if current < 0:
        raise ValueError(
            f"bootstrap_attempts counter cannot be negative: got {current}"
        )
    return current + 1
