"""Blame-the-cause regression cascade — charge only the breaking feature.

Feature c5c2c05e-d408-4351-a38f-14cfb9aac2d1

For each failing test, walk the AC table to find the feature whose ``pytest:``
AC owns that test path. Charge a refinement attempt to that feature only.
Features that merely ran during the same verification but don't own any
failing test stay at their pre-verification status.

Public API
----------
- ``charge_failing_feature`` — for a single failing test, find its owner
  and charge refinement_attempts to it via the caller-supplied increment_fn.
- ``charge_failing_features`` — batch version; charges all unique owning
  features across a list of failing tests.
- ``find_owning_feature`` — returns the feature_id whose pytest: AC matches a
  single failing test path, or None if unowned.
- ``preserve_innocent_status`` — returns statuses for uncharged features.
- ``OrphanTestError`` — raised when strict=True and no owner is found.

Integration
-----------
``bob.orchestrator`` calls these helpers after ``run_verification_checklist``
reports failures, replacing unconditional ``increment_refinement_attempts``
with targeted blame-the-cause attribution.
"""

from __future__ import annotations

from typing import Any, Callable

from bob.blame_cascade import (
    OrphanTestError,
    charge_breaking_feature as _charge_breaking_feature,
    charge_failing_features,
    find_owner_feature,
    handle_unowned_failure,
    preserve_innocent_status,
)

__all__ = [
    "charge_breaking_feature",
    "charge_failing_feature",
    "charge_failing_features",
    "charge_regression_cascade",
    "find_owning_feature",
    "preserve_innocent_status",
    "handle_unowned_failure",
    "OrphanTestError",
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


def charge_failing_feature(
    *,
    failing_test: str,
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> str | None:
    """Find the owning feature for a single failing test and charge it.

    Walks the AC table for each feature looking for a ``pytest: <path>`` AC
    that matches *failing_test*. If an owner is found, ``increment_fn`` is
    called once with the owner's feature_id and that id is returned. Features
    that own no failing test are not charged.

    Args:
        failing_test: A pytest node-id such as
            ``"tests/test_foo.py::test_bar"``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Called once with the owning feature_id when found.
        unowned_record_fn: Optional callback invoked when no owner is found.

    Returns:
        The charged feature_id, or ``None`` if the test has no owning feature.

    Raises:
        ValueError: If ``failing_test`` is not a non-empty string.
    """
    if not isinstance(failing_test, str) or not failing_test.strip():
        raise ValueError(
            f"failing_test must be a non-empty string; got {failing_test!r}"
        )

    owner = find_owner_feature(
        failing_test=failing_test,
        all_features=all_features,
        strict=False,
    )

    if owner is not None:
        increment_fn(owner)
        return owner

    if unowned_record_fn is not None:
        handle_unowned_failure(
            failing_test=failing_test,
            record_fn=unowned_record_fn,
        )
    return None


def charge_breaking_feature(
    *,
    failing_tests: list[Any],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the feature that owns each failing test.

    For each failing test, walks the AC table to find the owning feature
    (the one with a matching ``pytest:`` AC). Each unique owner is charged
    exactly once via *increment_fn*. Features that ran during the same
    verification but own no failing test are not charged.

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
    return _charge_breaking_feature(
        failing_tests=failing_tests,
        all_features=all_features,
        increment_fn=increment_fn,
        unowned_record_fn=unowned_record_fn,
    )


def charge_regression_cascade(
    *,
    failing_tests: list[Any],
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> int:
    """Charge refinement_attempts to the feature that owns each failing test.

    Feature 43bfef8a-8c14-40d9-85ba-49b24b1b1873

    For each failing test, walks the AC table to find the feature whose
    ``pytest:`` AC owns that test path. Charges a refinement attempt to that
    feature only. Features that merely ran during the same verification but
    don't own any failing test stay at their pre-verification status.

    Args:
        failing_tests: Pytest node-ids that are currently failing, e.g.
            ``["tests/test_foo.py::test_bar", "tests/test_baz.py::test_x"]``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Callable invoked once per unique owning ``feature_id``.
        unowned_record_fn: Optional callback for tests that have no owning
            feature.

    Returns:
        The count of unique features charged.

    Raises:
        ValueError: If ``failing_tests`` is not a list.
    """
    if not isinstance(failing_tests, list):
        raise ValueError(
            f"failing_tests must be a list; got {type(failing_tests).__name__!r}"
        )
    return _charge_breaking_feature(
        failing_tests=failing_tests,
        all_features=all_features,
        increment_fn=increment_fn,
        unowned_record_fn=unowned_record_fn,
    )
