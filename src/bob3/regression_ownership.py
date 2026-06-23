"""Ownership-evidenced regression detection — no scapegoat without proof.

Feature c68b3042-7e9d-41f9-9816-b99d99cc23f3

Provides the canonical entry points required by the feature AC:
- ``detect_regression_with_evidence``: end-to-end ownership-gated pipeline
- ``validate_ownership_link``: confirm a causal link between a feature and a
  regression before any demotion is permitted

Both functions enforce the invariant: a feature MUST NOT be demoted to
``regression`` status unless there is concrete evidence that its own files
(directly or transitively) appear in the breaking commit's diff.  Without
that evidence, the demotion is rejected and a ``regression_unattributed``
event is filed instead.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TRANSITIVE_DEPTH = 3


def _transitive_reachable(
    start_files: set,
    transitive_deps: dict,
    max_depth: int,
) -> set:
    """Return all files reachable from *start_files* within *max_depth* hops."""
    reachable = set(start_files)
    frontier = set(start_files)
    for _ in range(max_depth):
        next_frontier: set = set()
        for f in frontier:
            next_frontier.update(transitive_deps.get(f, set()))
        new = next_frontier - reachable
        if not new:
            break
        reachable.update(new)
        frontier = new
    return reachable


def validate_ownership_link(
    *,
    feature_id: str,
    owned_files,
    breaking_files,
    transitive_deps: dict | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> tuple[bool, list[str]]:
    """Validate whether a causal ownership link exists between a feature and a regression.

    A regression demotion is only valid when the feature's own code or tests
    were touched (directly or transitively depended upon) by the breaking
    commit.  Without that evidence, the demotion MUST be rejected.

    Args:
        feature_id: Non-empty string identifying the candidate feature.
        owned_files: Set (or frozenset) of file paths owned by the feature.
        breaking_files: Set (or frozenset) of file paths touched by the breaking
            commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}`` import graph.
            When provided, the reachability check follows import edges up to
            *max_transitive_depth* hops.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        ``(has_link, evidence_list)`` where *has_link* is True when a causal
        ownership link is established, and *evidence_list* contains
        human-readable strings describing the evidence.  *evidence_list* is
        empty when *has_link* is False.

    Raises:
        ValueError: If *feature_id* is None, empty, or whitespace-only.
        ValueError: If *owned_files* is not a set or frozenset.
        ValueError: If *breaking_files* is not a set or frozenset.
    """
    if feature_id is None or not isinstance(feature_id, str) or not feature_id.strip():
        raise ValueError(
            f"feature_id must be a non-empty, non-whitespace string; got {feature_id!r}"
        )
    if not isinstance(owned_files, (set, frozenset)):
        raise ValueError(
            f"owned_files must be a set or frozenset; got {type(owned_files)!r}"
        )
    if not isinstance(breaking_files, (set, frozenset)):
        raise ValueError(
            f"breaking_files must be a set or frozenset; got {type(breaking_files)!r}"
        )

    if not owned_files or not breaking_files:
        return False, []

    # Direct overlap
    direct_overlap = owned_files & breaking_files
    if direct_overlap:
        evidence = [
            f"owned file {f!r} was touched by the breaking commit"
            for f in sorted(direct_overlap)
        ]
        logger.debug(
            "validate_ownership_link: feature=%s direct evidence: %s",
            feature_id,
            direct_overlap,
        )
        return True, evidence

    # Transitive overlap (only when depth > 0)
    if transitive_deps and max_transitive_depth > 0:
        reachable = _transitive_reachable(
            owned_files, transitive_deps, max_transitive_depth
        )
        transitive_touched = (reachable - owned_files) & breaking_files
        if transitive_touched:
            evidence = [
                f"owned file transitively imports {f!r} which was touched by the breaking commit"
                for f in sorted(transitive_touched)
            ]
            logger.debug(
                "validate_ownership_link: feature=%s transitive evidence: %s",
                feature_id,
                transitive_touched,
            )
            return True, evidence

    return False, []


def detect_regression_with_evidence(
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
) -> Any:
    """Detect regressions only when a causal ownership link can be established.

    This replaces the bare ``detect_regression`` heuristic that would demote
    an arbitrary completed feature whenever downstream breakage appeared —
    exactly the scapegoat bug observed with F-15f5b3b8.

    Algorithm
    ---------
    1. Compare *before_results* and *after_results* to find newly-failing tests.
    2. For each newly-failing test, look up its owning feature in
       *test_to_feature_map*.  Tests with no mapping are emitted as
       ``regression_unattributed`` events; they are never scapegoated.
    3. For each candidate (owner) feature, call ``validate_ownership_link``
       using the feature's entry in *ownership_map* and the union of files
       touched across *recent_commits*.
    4. Only demote features for which the ownership link is validated.
    5. File a ``regression_unattributed`` event for each failure that cannot
       be causally attributed to any specific feature.

    Args:
        project_id: Bob3 project ID.
        causing_feature_id: The feature whose implementation was just applied.
        before_results: ``{test_nodeid: passed}`` snapshot before the feature.
        after_results: ``{test_nodeid: passed}`` snapshot after the feature.
        test_to_feature_map: ``{test_nodeid: feature_id}`` ownership map.
        ownership_map: ``{feature_id: set[file_path]}`` — files owned by each
            feature.
        recent_commits: List of ``{commit_id, files_touched}`` dicts.
        transitive_deps: Optional import-graph for transitive link resolution.
        _update_feature_fn: Callable ``(feature_id, status)`` for DB updates.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.
        _create_regression_event_fn: Callable that creates a RegressionEvent.

    Returns:
        The first RegressionEvent created (if any), or None.
    """
    import json

    if _update_feature_fn is None:
        from bob3 import db as _db
        _update_feature_fn = lambda fid, status: _db.update_feature(fid, status=status)

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs):
            logger.info("regression_ownership event %s: %s", event_type, kwargs)

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
            "regression_ownership: test %r has no owner; filing regression_unattributed",
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

    # Steps 3 & 4: validate ownership link; demote only if confirmed
    for owner_id, owned_tests in owner_to_tests.items():
        owned_files = ownership_map.get(owner_id, set())
        has_link, evidence = validate_ownership_link(
            feature_id=owner_id,
            owned_files=set(owned_files),
            breaking_files=breaking_files,
            transitive_deps=transitive_deps,
        )

        if not has_link:
            logger.info(
                "regression_ownership: causal link NOT established for feature %s; "
                "filing regression_unattributed to avoid scapegoating",
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
                        "breaking commit's diff; demotion rejected to avoid scapegoating"
                    ),
                )
            continue

        # Ownership link confirmed — demote the owner
        logger.info(
            "regression_ownership: ownership link confirmed for feature %s; "
            "demoting to 'regression'",
            owner_id,
        )
        _update_feature_fn(owner_id, "regression")

        event = _create_regression_event_fn(
            project_id=project_id,
            affected_feature_id=owner_id,
            causing_feature_id=causing_feature_id,
            affected_tests=json.dumps(sorted(owned_tests)),
            evidence_artifacts=json.dumps(evidence),
        )
        if first_event is None:
            first_event = event

    return first_event
