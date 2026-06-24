"""Bootstrap readiness override — one bypass execute per feature (bob77).

Exposes check_bootstrap_readiness, a predicate that determines whether a
feature may bypass the readiness gate exactly once.

The bypass breaks the self-referential deadlock where a feature is stuck at a
low readiness_score with research_iterations==0: research cannot lift the
score because there is no execution signal, and execution is blocked because
the score is too low.

Conditions for bypass (all must hold):
  - bootstrap_attempts < 1   (haven't used the bypass yet)
  - research_iterations == 0 (no research signal exists yet)

Negative counter values are invalid and raise ValueError.

Integrates with bob.features: callers compose this check alongside
bob.features utilities when deciding whether to allow a gated execution.
"""

from __future__ import annotations

import bob.features as _features  # noqa: F401 — integration: bob.features

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
