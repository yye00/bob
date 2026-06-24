"""Blame-the-cause regression cascade — charge the breaking feature.

Feature adf5fbf3-5c88-40f0-a668-c151a7c49a1b

For each failing test, walk the AC table to find the feature whose
``pytest:`` AC owns that test path. Charge a refinement attempt to that
feature only. Features that merely ran during the same verification but
don't own any failing test stay at their pre-verification status.

Public API
----------
- ``walk_ac_table`` — for a single failing test, scan all features' ACs and
  return the feature_id whose ``pytest:`` AC path matches, or None.
- ``charge_feature_by_test_ownership`` — for each failing test, walk the AC
  table, charge the owning feature exactly once, and return the count of
  unique features charged.
"""

from __future__ import annotations

from typing import Any, Callable

from bob3.orchestrator.blame_cascade import (  # noqa: F401
    OrphanTestError,
    charge_refinement,
    find_owner_feature,
    handle_unowned_failure,
    preserve_innocent_status,
)

__all__ = [
    "walk_ac_table",
    "charge_feature_by_test_ownership",
    "OrphanTestError",
]


def walk_ac_table(
    *,
    failing_test: str,
    all_features: list[Any],
    strict: bool = False,
) -> str | None:
    """Walk the AC table to find the feature that owns *failing_test*.

    Scans each feature's ``acceptance_criteria`` for a ``pytest: <path>`` AC
    whose path prefix matches the given failing test node-id. The first
    matching feature_id is returned.

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


def charge_feature_by_test_ownership(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the feature that owns each failing test.

    For each failing test, ``walk_ac_table`` is called to find the owning
    feature. Each unique owning feature is charged exactly once via
    ``increment_fn``, regardless of how many of its tests are failing.
    Features that ran during the same verification but own no failing test
    are not charged — their pre-verification status is preserved.

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
