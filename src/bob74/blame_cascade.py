"""Blame-the-cause regression cascade — charge the breaking feature.

Feature ccf9fa48-ea6f-4487-9854-568191831b0c

For each failing test, walk the AC table to find the feature whose
``pytest:`` AC owns that test path. Charge a refinement attempt to that
feature only. Features that merely ran during the same verification but don't
own any failing test stay at their pre-verification status.

Public API
----------
- ``charge_failing_features`` — top-level entry point. For each failing test,
  finds the owning feature and charges exactly one refinement attempt to it.
- ``find_owning_feature`` — returns the feature_id whose pytest: AC matches a
  single failing test path, or None if unowned.
- ``preserve_innocent_status`` — returns statuses of uncharged features.

Integration with bob.verification
------------------------------------
``bob.verification`` is the upstream consumer. After a verification run
reports test failures, call ``charge_failing_features`` in place of a blanket
``increment_refinement_attempts`` so only the true owner is penalised.
"""

from __future__ import annotations

from typing import Any, Callable

from bob.orchestrator.blame_cascade import (
    OrphanTestError,
    charge_refinement,
    find_owner_feature,
    handle_unowned_failure,
    preserve_innocent_status,
)

__all__ = [
    "charge_failing_features",
    "find_owning_feature",
    "preserve_innocent_status",
    "handle_unowned_failure",
    "OrphanTestError",
]

# Public alias matching the AC: "Function defined: bob74.blame_cascade.find_owning_feature"
find_owning_feature = find_owner_feature


def charge_failing_features(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to each feature that owns a failing test.

    For each failing test, the AC table is searched for a feature with a
    matching ``pytest: <path>`` acceptance criterion. Each unique owning
    feature is charged exactly once via *increment_fn*, regardless of how many
    of its tests are failing. Features that ran during the same verification
    but own no failing test are not charged — their status is preserved.

    Args:
        failing_tests: Pytest node-ids that are currently failing, e.g.
            ``["tests/test_foo.py::test_bar", "tests/test_baz.py::test_x"]``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Callable invoked once per unique owning feature_id.
            Typically ``db.increment_refinement_attempts``.
        unowned_record_fn: Optional callback for tests that have no owning
            feature. Each call receives an event dict
            ``{"type": "unattributed_failure", "failing_test": <path>}``.

    Returns:
        The count of unique features charged (0 when *failing_tests* is empty
        or no failing test has an owner).

    Raises:
        ValueError: If *failing_tests* is not a list.
    """
    if not isinstance(failing_tests, list):
        raise ValueError(
            f"failing_tests must be a list; got {type(failing_tests).__name__!r}"
        )
    return charge_refinement(
        failing_tests=failing_tests,
        all_features=all_features,
        increment_fn=increment_fn,
        unowned_record_fn=unowned_record_fn,
    )
