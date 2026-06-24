"""Ownership-evidenced regression detection — no scapegoat without proof.

Feature a166a32e-d5b9-436a-938e-243319f03245

Problem solved
--------------
``detect_regression`` previously demoted arbitrary previously-completed
features to ``regression`` status when downstream breakage appeared, without
establishing a causal link.  A prior generation F-15f5b3b8 ("Blame-the-cause
regression cascade") was itself scapegoated.

Per memory/regression_scapegoat_mechanism.md: detection must require evidence
that the demoted feature's own code/tests were touched (or transitively
depended-upon) by the breaking commit.  Without that evidence, the demotion
is rejected and a ``regression_unattributed`` event is filed instead.

Public API
----------
``has_ownership_evidence``
    Return ``(evidence_exists, evidence_list)`` for a candidate feature.
    A causal link is established when at least one owned file (or a file
    transitively imported by an owned file) appears in the breaking diff.

``detect_regression_with_evidence``
    End-to-end pipeline that:
    1. Identifies newly-failing tests (passed before, fail after).
    2. Maps each failing test to its owning feature.
    3. For each candidate feature, calls ``has_ownership_evidence``.
    4. Demotes only features with a confirmed causal link.
    5. Files ``regression_unattributed`` events for unattributable failures.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "has_ownership_evidence",
    "detect_regression_with_evidence",
]

_DEFAULT_MAX_TRANSITIVE_DEPTH = 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _transitive_reachable(
    start_files: set[str],
    transitive_deps: dict[str, set[str]],
    max_depth: int,
) -> set[str]:
    """Return all files reachable from *start_files* within *max_depth* hops."""
    reachable = set(start_files)
    frontier = set(start_files)
    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for f in frontier:
            next_frontier.update(transitive_deps.get(f, set()))
        new = next_frontier - reachable
        if not new:
            break
        reachable.update(new)
        frontier = new
    return reachable


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def has_ownership_evidence(
    *,
    feature_id: str,
    owned_files: set[str],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> tuple[bool, list[str]]:
    """Return ``(evidence_exists, evidence_list)`` for a candidate feature.

    A causal link is established when at least one of the feature's owned files
    (or a file transitively imported by an owned file, up to
    *max_transitive_depth* hops) appears in the set of files touched by the
    breaking commit(s).

    Args:
        feature_id: The feature being evaluated for demotion (used for logging
            and error messages).
        owned_files: Set of file paths owned by *feature_id*.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.  When
            provided, the reachability check follows import edges up to
            *max_transitive_depth* hops.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        ``(evidence_exists, evidence_list)`` where *evidence_exists* is True
        when a causal link is established and *evidence_list* contains
        human-readable strings describing the evidence.  *evidence_list* is
        empty when *evidence_exists* is False.

    Raises:
        ValueError: If *feature_id* is empty, None, or whitespace-only.
        ValueError: If *owned_files* is not a set or frozenset.
        ValueError: If *breaking_files* is not a set or frozenset.
    """
    if not feature_id or (isinstance(feature_id, str) and not feature_id.strip()):
        raise ValueError("feature_id must be a non-empty, non-whitespace string")
    if not isinstance(owned_files, (set, frozenset)):
        raise ValueError(
            f"owned_files must be a set or frozenset, got {type(owned_files)!r}"
        )
    if not isinstance(breaking_files, (set, frozenset)):
        raise ValueError(
            f"breaking_files must be a set or frozenset, got {type(breaking_files)!r}"
        )

    if not owned_files or not breaking_files:
        return False, []

    # Direct overlap
    direct_overlap = sorted(owned_files & breaking_files)
    if direct_overlap:
        evidence = [
            f"owned file {f!r} appears in the breaking commit diff"
            for f in direct_overlap
        ]
        logger.debug(
            "has_ownership_evidence: feature=%s direct overlap=%s",
            feature_id,
            direct_overlap,
        )
        return True, evidence

    # Transitive overlap
    if transitive_deps and max_transitive_depth > 0:
        reachable = _transitive_reachable(owned_files, transitive_deps, max_transitive_depth)
        transitive_touched = sorted((reachable - owned_files) & breaking_files)
        if transitive_touched:
            evidence = [
                f"owned file transitively imports {f!r} which appears in the breaking commit diff"
                for f in transitive_touched
            ]
            logger.debug(
                "has_ownership_evidence: feature=%s transitive overlap=%s",
                feature_id,
                transitive_touched,
            )
            return True, evidence

    return False, []


def detect_regression_with_evidence(
    *,
    project_id: str,
    causing_feature_id: str,
    before_results: dict[str, bool],
    after_results: dict[str, bool],
    test_to_feature_map: dict[str, str],
    ownership_map: dict[str, set[str]],
    recent_commits: list[dict],
    transitive_deps: dict[str, set[str]] | None = None,
    _update_feature_fn=None,
    _emit_event_fn=None,
    _create_regression_event_fn=None,
) -> Any:
    """Detect regressions only when a causal ownership link can be established.

    This replaces the bare ``detect_regression`` heuristic that demoted an
    arbitrary completed feature whenever downstream breakage appeared.

    Algorithm
    ---------
    1. Compare *before_results* and *after_results* to find newly-failing tests.
    2. For each newly-failing test, look up its owning feature in
       *test_to_feature_map*.  Tests with no mapping are emitted as
       ``regression_unattributed`` events and never scapegoated.
    3. For each candidate (owner) feature, call ``has_ownership_evidence``
       using the feature's entry in *ownership_map* and the union of files
       touched across *recent_commits*.
    4. Only demote features for which a causal link is validated.
    5. File a ``regression_unattributed`` event for each test whose owner
       cannot be causally linked to the breakage.

    Args:
        project_id: Bob3 project ID.
        causing_feature_id: Feature whose implementation was just applied.
        before_results: ``{test_nodeid: passed}`` snapshot before the feature.
        after_results: ``{test_nodeid: passed}`` snapshot after the feature.
        test_to_feature_map: ``{test_nodeid: feature_id}`` ownership map.
        ownership_map: ``{feature_id: set[file_path]}`` — files owned by each
            feature, derived from commit history at the call-site.
        recent_commits: List of ``{commit_id, files_touched}`` dicts.  The
            union of all ``files_touched`` values forms the breaking-file set.
        transitive_deps: Optional import-graph for transitive link resolution.
        _update_feature_fn: Callable ``(feature_id, status)`` for DB updates.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.
        _create_regression_event_fn: Callable that creates a RegressionEvent.

    Returns:
        The first RegressionEvent created (if any), or ``None``.

    Raises:
        ValueError: If *project_id* is empty or None.
        ValueError: If *causing_feature_id* is empty or None.
        ValueError: If *before_results* is not a dict.
        ValueError: If *after_results* is not a dict.
        ValueError: If *test_to_feature_map* is not a dict.
        ValueError: If *ownership_map* is not a dict.
        ValueError: If *recent_commits* is not a list.
    """
    if not project_id or not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id must be a non-empty string")
    if not causing_feature_id or not isinstance(causing_feature_id, str) or not causing_feature_id.strip():
        raise ValueError("causing_feature_id must be a non-empty string")
    if not isinstance(before_results, dict):
        raise ValueError(f"before_results must be a dict, got {type(before_results)!r}")
    if not isinstance(after_results, dict):
        raise ValueError(f"after_results must be a dict, got {type(after_results)!r}")
    if not isinstance(test_to_feature_map, dict):
        raise ValueError(f"test_to_feature_map must be a dict, got {type(test_to_feature_map)!r}")
    if not isinstance(ownership_map, dict):
        raise ValueError(f"ownership_map must be a dict, got {type(ownership_map)!r}")
    if not isinstance(recent_commits, list):
        raise ValueError(f"recent_commits must be a list, got {type(recent_commits)!r}")

    if _update_feature_fn is None:
        from bob3 import db as _db
        _update_feature_fn = lambda fid, status: _db.update_feature(fid, status=status)

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs):
            logger.info("regression_unattributed event %s: %s", event_type, kwargs)

    if _create_regression_event_fn is None:
        from bob3 import db as _db
        _create_regression_event_fn = _db.create_regression_event

    # Step 1: find newly-failing tests
    newly_failing: list[str] = [
        test
        for test, before_passed in before_results.items()
        if before_passed and test in after_results and not after_results[test]
    ]

    if not newly_failing:
        return None

    # Step 2: map tests to owning features; separate unmapped tests
    owner_to_tests: dict[str, list[str]] = {}
    unmapped_tests: list[str] = []
    for test in newly_failing:
        owner = test_to_feature_map.get(test)
        if owner is None:
            unmapped_tests.append(test)
        else:
            owner_to_tests.setdefault(owner, []).append(test)

    # Unmapped → unattributed event, never scapegoated
    for test in unmapped_tests:
        logger.info(
            "detect_regression_with_evidence: test %r has no owner; "
            "filing regression_unattributed",
            test,
        )
        _emit_event_fn(
            "regression_unattributed",
            failing_test_id=test,
            recent_commits=recent_commits,
            feature_id=None,
            reason="test not present in test_to_feature_map",
        )

    if not owner_to_tests:
        return None

    # Union of files touched across all recent commits
    breaking_files: set[str] = set()
    for commit in recent_commits:
        breaking_files.update(commit.get("files_touched", []))

    first_event = None

    # Steps 3 & 4: validate causal link; demote only if confirmed
    for owner_id, owned_tests in owner_to_tests.items():
        owned_files = ownership_map.get(owner_id, set())
        if not isinstance(owned_files, (set, frozenset)):
            owned_files = set(owned_files)

        evidence_exists, evidence_list = has_ownership_evidence(
            feature_id=owner_id,
            owned_files=owned_files,
            breaking_files=breaking_files,
            transitive_deps=transitive_deps,
        )

        if not evidence_exists:
            logger.info(
                "detect_regression_with_evidence: causal link NOT established for "
                "feature %s; filing regression_unattributed to avoid scapegoating",
                owner_id,
            )
            for test in owned_tests:
                _emit_event_fn(
                    "regression_unattributed",
                    failing_test_id=test,
                    recent_commits=recent_commits,
                    feature_id=owner_id,
                    reason=(
                        "no owned file (direct or transitive) appears in the "
                        "breaking commit diff; demotion rejected to avoid scapegoating"
                    ),
                )
            continue

        # Causal link confirmed — demote the owner
        logger.info(
            "detect_regression_with_evidence: causal link confirmed for feature %s; "
            "demoting to 'regression'",
            owner_id,
        )
        _update_feature_fn(owner_id, "regression")

        event = _create_regression_event_fn(
            project_id=project_id,
            affected_feature_id=owner_id,
            causing_feature_id=causing_feature_id,
            affected_tests=json.dumps(sorted(owned_tests)),
            evidence_artifacts=json.dumps(evidence_list),
        )
        if first_event is None:
            first_event = event

    return first_event
