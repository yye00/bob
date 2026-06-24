"""Blame-the-cause regression cascade — charge the breaking feature.

Feature d55f745b-2ca5-443b-bfd0-5c9f9d33b0fb

For each failing test, walks the AC table to find the feature whose
``pytest:`` AC owns that test path. Charges a refinement attempt only to
that owning feature. Features that merely ran during the same verification
but own no failing test remain at their pre-verification status.

Public API
----------
- ``charge_breaking_feature`` — top-level entry point for the blame cascade.
  Delegates to ``bob.orchestrator.blame_cascade.charge_refinement``.
"""

from __future__ import annotations

from typing import Any, Callable

from bob.orchestrator.blame_cascade import (
    charge_refinement,
    find_owner_feature,
    handle_unowned_failure,
    preserve_innocent_status,
    OrphanTestError,
)

__all__ = [
    "charge_breaking_feature",
    "OrphanTestError",
]


def charge_breaking_feature(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to each feature that broke its own tests.

    For each failing test, walks the AC table to find the owning feature
    (the one with a matching ``pytest:`` AC). Each unique owner is charged
    exactly once via *increment_fn*. Features that ran during the same
    verification but own no failing test are not charged.

    Args:
        failing_tests: Pytest node-ids that are currently failing.
        all_features: All features in scope, each with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Called once per unique owning feature_id.
        unowned_record_fn: Optional callback for tests with no owning feature.

    Returns:
        The count of unique features charged.
    """
    if not isinstance(failing_tests, list):
        raise ValueError(
            f"failing_tests must be a list, got {type(failing_tests).__name__!r}"
        )

    return charge_refinement(
        failing_tests=failing_tests,
        all_features=all_features,
        increment_fn=increment_fn,
        unowned_record_fn=unowned_record_fn,
    )
