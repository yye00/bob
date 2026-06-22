"""Regression baseline attribution for the tests_pass regression-vs-baseline gate.

Feature ee144b68-21ad-4a5e-b1bb-da2e9087f69a

This module provides ``attribute_failure_to_owner``, the canonical entry point
for the regression-vs-baseline gate to determine whether a newly-failing test
belongs to the currently-verifying feature or to a sibling/orphan.

Problem solved
--------------
The regression-vs-baseline check previously attributed ALL newly-failing tests
to the currently-verifying feature, even when they belonged to sibling features
that were NH-demoted earlier (leaving broken test stubs uncleaned).  This caused
innocent features to be gate-blocked and demoted to ``needs_human``.

The fix: every failing test is first attributed to its true owner via
``bob3.test_attribution_map.get_test_owning_feature``.  Only tests owned by
the currently-verifying feature count toward that feature's gate decision.

Integration with bob3.verification
------------------------------------
The regression-vs-baseline step in the verifier calls
``attribute_failure_to_owner`` for each newly-failing test and only counts
those for which the returned owner matches ``current_feature_id``.
"""

from __future__ import annotations

from typing import Any

from bob3.test_attribution import attribute_failure_to_owner

__all__ = [
    "attribute_failure_to_owner",
    "filter_failures_for_current_feature",
]


def filter_failures_for_current_feature(
    failing_tests: list[str],
    current_feature_id: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    previously_passed_at: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> tuple[list[str], list[str]]:
    """Filter *failing_tests* into tests attributable to the current feature and others.

    For each test in *failing_tests*:
    - If owned by *current_feature_id*, it is placed in the *attributable* list
      and counts toward the gate decision.
    - If owned by a sibling feature or orphaned, it is placed in the
      *non_attributable* list and does NOT count against the current feature.

    Sibling owners are re-opened if in a terminal state, and orphan tests are
    logged — all side-effects are handled by the attribution layer.

    Args:
        failing_tests: Test node-ids that newly fail vs the pre-impl baseline.
        current_feature_id: The feature currently under verification.
        all_features: Optional list of feature dicts/objects for pytest-prefix
            AC ownership strategy.
        workspace_root: Workspace root path (forwarded to attribution layer).
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot.
        _update_feature_fn: Callable for DB update (for testing/mocking).
        _emit_event_fn: Callable for event emission (for testing/mocking).

    Returns:
        A ``(attributable, non_attributable)`` tuple:
        - *attributable*: tests owned by *current_feature_id*.
        - *non_attributable*: tests owned by another feature or unowned.
    """
    attributable: list[str] = []
    non_attributable: list[str] = []

    for test_path in failing_tests:
        owner = attribute_failure_to_owner(
            test_path,
            current_feature_id,
            all_features=all_features,
            workspace_root=workspace_root,
            previously_passed_at=previously_passed_at,
            _update_feature_fn=_update_feature_fn,
            _emit_event_fn=_emit_event_fn,
        )
        if owner == current_feature_id:
            attributable.append(test_path)
        else:
            non_attributable.append(test_path)

    return attributable, non_attributable
