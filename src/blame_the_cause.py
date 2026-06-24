"""Blame-the-cause regression cascade — charge only the breaking feature.

Feature 240d49a1-cd13-4bf8-8ef1-f44116681194

For each failing test, walk the AC table to find the feature whose ``pytest:``
AC owns that test path. Charge a refinement attempt to that feature only.
Features that merely ran during the same verification but don't own any
failing test stay at their pre-verification status.

Public API
----------
- ``find_owning_feature`` — returns the feature_id whose pytest: AC matches a
  single failing test path, or None if unowned.
- ``charge_feature`` — charges refinement_attempts on the owning features for
  each failing test; returns the count of unique features charged.
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
    "find_owning_feature",
    "charge_feature",
    "OrphanTestError",
    "preserve_innocent_status",
    "handle_unowned_failure",
]


def find_owning_feature(
    *,
    failing_test: str,
    all_features: list[Any],
    strict: bool = False,
) -> str | None:
    """Return the feature_id whose pytest: AC owns *failing_test*.

    Args:
        failing_test: A pytest node-id, e.g. ``"tests/test_foo.py::test_bar"``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        strict: When True, raises ``OrphanTestError`` if no owner is found.

    Returns:
        The owning feature_id string, or ``None`` if not found (and not strict).

    Raises:
        OrphanTestError: If ``strict=True`` and no owner is found.
        ValueError: If ``failing_test`` is not a non-empty string.
    """
    if not isinstance(failing_test, str) or not failing_test.strip():
        raise ValueError(
            f"failing_test must be a non-empty string; got {failing_test!r}"
        )
    return find_owner_feature(
        failing_test=failing_test,
        all_features=all_features,
        strict=strict,
    )


def charge_feature(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the feature that owns each failing test.

    For each failing test, the AC table is searched for a feature with a
    matching ``pytest: <path>`` acceptance criterion. The owning feature is
    charged exactly once, regardless of how many of its tests are failing.
    Features that ran during the same verification but own no failing test are
    not charged.

    Args:
        failing_tests: Pytest node-ids that are currently failing.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Called once per unique owning feature_id.
        unowned_record_fn: Optional callback for tests with no owning feature.

    Returns:
        The count of unique features charged.

    Raises:
        ValueError: If ``failing_tests`` is not a list.
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
