"""Blame-the-cause regression cascade — public top-level facade.

Feature 56ca0fd2-72e1-4399-afa3-d636f58b065f

For each failing test, walk the AC table to find the feature whose ``pytest:``
AC owns that test path.  Charge a refinement attempt to that feature only.
Features that merely ran during the same verification but don't own any
failing test stay at their pre-verification status.

This module is the canonical entry point.  It delegates to the richer
``bob3.orchestrator.blame_cascade`` sub-module for all logic.

Integration with bob3.verification
-----------------------------------
``bob3.verification`` exposes ``filter_attributable_failures`` for the
regression-vs-baseline gate.  ``charge_feature_for_failures`` is the
*write* side: once attribution is decided, use this function to actually
increment refinement_attempts on the owning features.
"""

from __future__ import annotations

from typing import Any, Callable

from bob3.orchestrator.blame_cascade import (
    OrphanTestError,
    charge_refinement,
    find_owner_feature,
    handle_unowned_failure,
    preserve_innocent_status,
)

__all__ = [
    "charge_feature_for_failures",
    "charge_refinement",
    "charge_refinement_attempt",
    "find_owner_feature",
    "find_owning_feature",
    "preserve_innocent_status",
    "handle_unowned_failure",
    "OrphanTestError",
]

# Alias required by AC: "Function defined: blame_cascade.find_owning_feature"
find_owning_feature = find_owner_feature


def charge_refinement_attempt(
    *,
    failing_test: str,
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> str | None:
    """Charge a single refinement attempt to the feature that owns *failing_test*.

    Walks the AC table to find the feature whose ``pytest:`` AC owns the given
    failing test path.  Charges refinement_attempts on that feature only.
    Features that merely ran during the same verification but don't own this
    test stay at their pre-verification status (i.e. are not charged).

    Args:
        failing_test: A pytest node-id, e.g. ``"tests/test_foo.py::test_bar"``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Called with the owning ``feature_id`` when an owner is found.
        unowned_record_fn: Optional callback invoked when no owner is found,
            receiving ``{"type": "unattributed_failure", "failing_test": <path>}``.

    Returns:
        The owning feature_id if one was found and charged, or ``None`` if the
        test has no owning feature.
    """
    owner = find_owner_feature(
        failing_test=failing_test,
        all_features=all_features,
        strict=False,
    )
    if owner is not None:
        increment_fn(owner)
    else:
        if unowned_record_fn is not None:
            handle_unowned_failure(
                failing_test=failing_test,
                record_fn=unowned_record_fn,
            )
    return owner


def charge_feature_for_failures(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the feature that owns each failing test.

    For each failing test, the AC table is searched for a feature with a
    matching ``pytest: <path>`` acceptance criterion.  The owning feature is
    charged exactly once, regardless of how many of its tests are failing.
    Features that ran during the same verification but own no failing test are
    not charged — their pre-verification status is preserved.

    Args:
        failing_tests: Pytest node-ids that are currently failing, e.g.
            ``["tests/test_foo.py::test_bar", "tests/test_baz.py::test_x"]``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Callable invoked once per unique owning ``feature_id``.
            Typically ``db.increment_refinement_attempts``.
        unowned_record_fn: Optional callback for tests that have no owning
            feature.  Each call receives an event dict
            ``{"type": "unattributed_failure", "failing_test": <path>}``.

    Returns:
        The count of unique features charged (0 when no failing test has an
        owner, or when *failing_tests* is empty).
    """
    return charge_refinement(
        failing_tests=failing_tests,
        all_features=all_features,
        increment_fn=increment_fn,
        unowned_record_fn=unowned_record_fn,
    )
