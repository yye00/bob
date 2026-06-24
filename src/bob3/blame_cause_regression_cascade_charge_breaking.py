"""Blame-the-cause regression cascade — charge only the breaking feature.

Feature 258d8dc4-ec52-4360-88fc-0e5f02708693

For each failing test, walks the AC table to find the feature whose
``pytest:`` AC owns that test path. Charges a refinement attempt only to
that owning feature. Features that merely ran during the same verification
but own no failing test stay at their pre-verification status.

Public API
----------
- ``blame_cause_regression_cascade_charge_breaking`` — top-level entry point.
  Delegates to ``bob3.orchestrator.blame_cascade.charge_refinement``.
"""

from __future__ import annotations

from typing import Any, Callable

from bob3.orchestrator.blame_cascade import charge_refinement

__all__ = ["blame_cause_regression_cascade_charge_breaking"]


def blame_cause_regression_cascade_charge_breaking(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to each feature that broke its own tests.

    Walks the AC table for each failing test to identify the owning feature
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
    return charge_refinement(
        failing_tests=failing_tests,
        all_features=all_features,
        increment_fn=increment_fn,
        unowned_record_fn=unowned_record_fn,
    )
