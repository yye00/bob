"""Bootstrap readiness override — one bypass execute per feature.

Exposes a predicate that determines whether a feature may bypass the readiness
gate exactly once, resolving the self-referential deadlock where a feature is
stuck at a low readiness_score with research_iterations==0: research cannot lift
the score because there is no execution signal, and execution is blocked because
the score is too low.

Conditions for the bypass (all must be true):
  - bootstrap_attempts < 1  (the single allowed bypass has not been consumed)
  - research_iterations == 0  (no research signal exists yet)
"""

from __future__ import annotations

from typing import Any

_MAX_BOOTSTRAP_ATTEMPTS = 1


def _coerce_counter(value: Any, name: str) -> int:
    """Normalize a counter attribute to a non-negative int.

    ``None`` is treated as 0 (the model default). Any other non-int, or a
    negative int, is an invariant violation and raises ``ValueError`` — the
    function must never silently succeed on invalid input.
    """
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"{name} must be a non-negative int, got {value!r} "
            f"({type(value).__name__})"
        )
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return value


def should_bootstrap_bypass(feature: Any) -> bool:
    """Return True if this feature may bypass the readiness gate once.

    The canonical entry point for the bootstrap readiness override. A feature is
    eligible for a single bootstrap bypass when it has never been researched
    (``research_iterations == 0``) and the one allowed bypass has not yet been
    consumed (``bootstrap_attempts < 1``).

    Args:
        feature: An object exposing ``bootstrap_attempts`` and
            ``research_iterations`` attributes (e.g. a ``bob.models.Feature``).

    Returns:
        True if the caller should allow one execution despite a failing
        readiness gate; False if the gate should be respected normally.

    Raises:
        TypeError: If *feature* is None or lacks the required attributes.
        ValueError: If either counter is negative or not an int.
    """
    if feature is None:
        raise TypeError("feature must not be None")

    try:
        raw_attempts = feature.bootstrap_attempts
        raw_research = feature.research_iterations
    except AttributeError as exc:
        raise TypeError(
            "feature must expose bootstrap_attempts and research_iterations "
            f"attributes: {exc}"
        ) from exc

    bootstrap_attempts = _coerce_counter(raw_attempts, "bootstrap_attempts")
    research_iterations = _coerce_counter(raw_research, "research_iterations")

    return bootstrap_attempts < _MAX_BOOTSTRAP_ATTEMPTS and research_iterations == 0


def check_bootstrap_bypass(feature: Any) -> bool:
    """Alias for :func:`should_bootstrap_bypass` (bob-side naming parity)."""
    return should_bootstrap_bypass(feature)


def increment_bootstrap_attempts(current: int) -> int:
    """Return the incremented bootstrap_attempts counter (current + 1).

    Raises:
        ValueError: If *current* is negative (counter invariant violation).
    """
    validated = _coerce_counter(current, "current")
    return validated + 1
