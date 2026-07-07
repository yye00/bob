"""Blame-the-cause regression cascade — charge only the breaking feature.

Feature b6bfd8c2-254e-49ce-8c96-6dd28ee30c8e

For each failing test, walk the AC table to find the feature whose ``pytest:``
AC owns that test path. Charge a refinement attempt to that feature only.
Features that merely ran during the same verification but don't own any
failing test stay at their pre-verification status.

Public API
----------
- ``charge_breaking_feature`` — batch entry point. Walks the AC table for each
  failing test, charges each unique owning feature exactly once, and records
  unattributed failures via an optional callback.
- ``find_owning_feature`` — returns the feature_id whose ``pytest:`` AC owns a
  single failing test path, or None (raises ``OrphanTestError`` under strict).
- ``preserve_innocent_status`` — statuses for features that were not charged.
- ``OrphanTestError`` — raised when strict=True and no owner is found.

Integration
-----------
``bob.orchestrator`` calls ``charge_breaking_feature`` after the verification
checklist reports failures, replacing unconditional refinement-attempt
increments with targeted blame-the-cause attribution.
"""

from __future__ import annotations

from typing import Any, Callable

from bob.blame_cascade import (
    OrphanTestError,
    charge_breaking_feature as _charge_breaking_feature,
    find_owner_feature as find_owning_feature,
    preserve_innocent_status,
)

__all__ = [
    "charge_breaking_feature",
    "find_owning_feature",
    "preserve_innocent_status",
    "OrphanTestError",
]


def charge_breaking_feature(
    *,
    failing_tests: list[str],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the feature that owns each failing test.

    For each failing test, walks the AC table to find the owning feature (the
    one with a matching ``pytest:`` AC). Each unique owner is charged exactly
    once via *increment_fn*. Features that ran during the same verification but
    own no failing test are not charged — their pre-verification status is
    preserved.

    Args:
        failing_tests: Pytest node-ids that are currently failing, e.g.
            ``["tests/test_foo.py::test_bar", "tests/test_baz.py::test_x"]``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Callable invoked once per unique owning ``feature_id``.
        unowned_record_fn: Optional callback for tests with no owning feature.

    Returns:
        The count of unique features charged.

    Raises:
        ValueError: If ``failing_tests`` is not a list.
    """
    return _charge_breaking_feature(
        failing_tests=failing_tests,
        all_features=all_features,
        increment_fn=increment_fn,
        unowned_record_fn=unowned_record_fn,
    )
