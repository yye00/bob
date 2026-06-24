"""tests_pass regression-vs-baseline: attribute failures to originating feature.

Feature a3c427e8-cc9d-447f-b7c4-5715abe95580

Problem solved
--------------
The regression-vs-baseline check ran whole-suite and attributed all
newly-failing tests to whichever feature was currently being verified.
When sibling-feature test stubs regressed (e.g. feature 73879589 left broken
stubs after being NH-demoted), the current feature was incorrectly gate-blocked.
Feature 9b2e1060 was observed demoted to NH at attempt=5 due to 7 failing tests
that all belonged to sibling/orphan features.

Fix
---
This module provides the canonical entry point for the regression-vs-baseline
gate.  It delegates to ``bob.regression_attribution.attribute_failures_to_owning_feature``
which filters failing tests so only those attributable to the
currently-verifying feature count as gate failures.

Tests owned by sibling features (tests/<other_feature_id>/ subtree) or orphan
tests (no UUID subdir, no pytest-prefix AC claim) are routed to their true
owner for re-opening/logging — the currently-verifying feature is NOT penalised.

Public API
----------
``tests_pass_regression_vs_baseline_must_attribute_failures_originating_feature_sibling_feature_broken_test_stubs_currently_gate_block_unrelated_current_feature_s_verification``
    Top-level entry point.  Returns ``(attributable, non_attributable)`` tuple.
    Only *attributable* tests count toward the gate decision for the current
    feature.
"""

from __future__ import annotations

from typing import Any

from bob.regression_attribution import attribute_failures_to_owning_feature

__all__ = [
    "tests_pass_regression_vs_baseline_must_attribute_failures_originating_feature_sibling_feature_broken_test_stubs_currently_gate_block_unrelated_current_feature_s_verification",
]


def tests_pass_regression_vs_baseline_must_attribute_failures_originating_feature_sibling_feature_broken_test_stubs_currently_gate_block_unrelated_current_feature_s_verification(
    failing_tests: list[str],
    current_feature_id: str,
    *,
    all_features: list[Any] | None = None,
    workspace_root: str | None = None,
    previously_passed_at: str | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> tuple[list[str], list[str]]:
    """Filter regression-vs-baseline failures to only those owned by the current feature.

    The regression-vs-baseline verification gate MUST call this function and
    count only the returned *attributable* tests toward its gate decision.
    Tests in *non_attributable* belong to sibling features or have no owner;
    they are re-opened or orphan-logged by the underlying sub-module.

    Ownership is resolved by two strategies (tried in order):

    1. **Directory convention**: ``tests/<feature_id>/`` paths are owned by
       the feature whose UUID appears in the subtree.
    2. **pytest-prefix ACs**: features that declare ``pytest: <path>`` own
       those test paths.

    A sibling or orphan test that newly fails triggers re-opening of its true
    owner (if in a terminal state) or emission of an ``orphan_test_regression``
    event — but NEVER counts against the current feature.

    Args:
        failing_tests: Pytest node-ids that newly fail vs the pre-impl baseline.
        current_feature_id: The feature currently under verification.
        all_features: Optional list of feature dicts/objects for the
            pytest-prefix AC strategy.  Pass None to rely on directory
            convention only.
        workspace_root: Workspace root path (forwarded to the sub-module).
        previously_passed_at: ISO-8601 timestamp from the baseline snapshot.
        _update_feature_fn: Callable for DB update (forwarded to sub-module).
        _emit_event_fn: Callable for event emission (forwarded to sub-module).

    Returns:
        A ``(attributable, non_attributable)`` tuple:
        - *attributable*: tests owned by *current_feature_id* that should
          count toward the gate decision.
        - *non_attributable*: tests owned by another feature (or orphaned);
          these have been re-opened / logged by the sub-module already.
    """
    return attribute_failures_to_owning_feature(
        failing_tests,
        current_feature_id,
        all_features=all_features,
        workspace_root=workspace_root,
        previously_passed_at=previously_passed_at,
        _update_feature_fn=_update_feature_fn,
        _emit_event_fn=_emit_event_fn,
    )
