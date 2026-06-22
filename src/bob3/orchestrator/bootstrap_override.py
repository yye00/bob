"""Bootstrap readiness override — one bypass execute per feature (73d63cdc).

Resolves the self-referential deadlock where a feature is stuck at a low
readiness_score with research_iterations==0: research cannot lift the
score because there is no execution signal, and execution is blocked
because the score is too low.

The fix: allow exactly ONE bypass of the readiness gate per feature when:
  - The readiness gate would normally block execution
  - bootstrap_attempts < 1  (haven't used the bypass yet)
  - research_iterations == 0  (no research signal exists yet)

After the bypass execution, the result becomes the seed signal for the
next research pass. ``bootstrap_attempts`` is then 1, so the bypass
cannot fire again for this feature.
"""

from __future__ import annotations

from bob3.models import Feature

_MAX_BOOTSTRAP_ATTEMPTS = 1


def may_bypass_readiness(feature: Feature) -> bool:
    """Return True if this feature is eligible for a bootstrap readiness bypass.

    A feature may bypass the readiness gate exactly once, and only when it
    has never been researched (research_iterations == 0).  This breaks the
    chicken-and-egg deadlock described in the module docstring.

    Args:
        feature: The Feature instance to evaluate.

    Returns:
        True if the caller should allow one execution despite a failing
        readiness gate; False if the gate should be respected normally.
    """
    bootstrap_attempts = feature.bootstrap_attempts or 0
    research_iterations = feature.research_iterations or 0

    return bootstrap_attempts < _MAX_BOOTSTRAP_ATTEMPTS and research_iterations == 0


def max_bootstrap_attempts() -> int:
    """Return the maximum number of bootstrap bypass attempts allowed per feature."""
    return _MAX_BOOTSTRAP_ATTEMPTS


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


def handle_second_attempt_denied(feature: Feature) -> bool:
    """Return False when bootstrap_attempts >= 1 (bypass already used).

    Used to make explicit the denial path: once the single bypass has been
    consumed, all subsequent calls return False without side effects.

    Args:
        feature: The Feature instance to evaluate.

    Returns:
        False when bootstrap_attempts >= max_bootstrap_attempts (1).
    """
    bootstrap_attempts = feature.bootstrap_attempts or 0
    return bootstrap_attempts < _MAX_BOOTSTRAP_ATTEMPTS
