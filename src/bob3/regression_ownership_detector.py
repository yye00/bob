"""Ownership-evidenced regression detection — no scapegoat without proof.

Feature 5d250d36-ec56-4377-9971-2dda437b0c90

Public API
----------
``has_ownership_evidence``
    Return ``(evidence_exists, evidence_list)`` for a candidate feature.
    A causal link is established when at least one owned file (or a file
    transitively imported by an owned file) appears in the breaking diff.

``detect_regression_with_ownership``
    End-to-end ownership-evidenced regression detection pipeline.
    Only demotes features with a confirmed causal link to the breaking commit.
    Files ``regression_unattributed`` events for tests that cannot be causally
    attributed — these are never scapegoated.

This module re-exports the canonical implementations from
``bob3.regression.ownership_detector`` so all call-sites can import from a
single location under the canonical module path required by the feature ACs.
"""

from __future__ import annotations

from bob3.regression.ownership_detector import (  # noqa: F401
    has_ownership_evidence,
    detect_regression_with_evidence as _detect_regression_with_evidence,
)

__all__ = [
    "has_ownership_evidence",
    "detect_regression_with_ownership",
]


def detect_regression_with_ownership(
    *,
    project_id: str,
    causing_feature_id: str,
    before_results: dict,
    after_results: dict,
    test_to_feature_map: dict,
    ownership_map: dict,
    recent_commits: list,
    transitive_deps: dict | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
    _create_regression_event_fn=None,
):
    """Detect regressions only when ownership evidence is established.

    Delegates to ``bob3.regression.ownership_detector.detect_regression_with_evidence``.
    A feature MUST NOT be demoted to ``regression`` unless its own files (or
    files it transitively depends upon) appear in the breaking commit's diff.
    Without that evidence, a ``regression_unattributed`` event is filed instead.

    Args:
        project_id: Bob3 project ID.
        causing_feature_id: Feature whose implementation was just applied.
        before_results: ``{test_nodeid: passed}`` snapshot before the change.
        after_results: ``{test_nodeid: passed}`` snapshot after the change.
        test_to_feature_map: ``{test_nodeid: feature_id}`` ownership map.
        ownership_map: ``{feature_id: set[file_path]}`` files owned by each feature.
        recent_commits: List of ``{commit_id, files_touched}`` dicts.
        transitive_deps: Optional import-graph for transitive link resolution.
        _update_feature_fn: Callable ``(feature_id, status)`` for DB updates.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.
        _create_regression_event_fn: Callable that creates a RegressionEvent.

    Returns:
        The first RegressionEvent created (if any), or ``None``.

    Raises:
        ValueError: If required arguments are missing, empty, or wrong type.
    """
    return _detect_regression_with_evidence(
        project_id=project_id,
        causing_feature_id=causing_feature_id,
        before_results=before_results,
        after_results=after_results,
        test_to_feature_map=test_to_feature_map,
        ownership_map=ownership_map,
        recent_commits=recent_commits,
        transitive_deps=transitive_deps,
        _update_feature_fn=_update_feature_fn,
        _emit_event_fn=_emit_event_fn,
        _create_regression_event_fn=_create_regression_event_fn,
    )
