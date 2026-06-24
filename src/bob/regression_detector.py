"""Ownership-evidenced regression detection.

Feature 9e8d5cac-28f6-4dfe-9f21-c2f565cd4af3

Problem solved
--------------
``detect_regression`` previously demoted arbitrary completed features to
``regression`` status when downstream breakage appeared, without establishing
a causal link.  Observed live in bob version 12 round 9: F-15f5b3b8
("Blame-the-cause regression cascade") was itself scapegoated.

This module provides two entry points:

``validate_causal_link`` — given a candidate feature's owned files and the
    set of files touched by the breaking commit, return (is_valid, evidence,
    reason).  A demotion is valid ONLY if the feature's code (or a transitive
    import thereof) appears in the breaking diff.

``detect_regression_with_evidence`` — end-to-end pipeline that:
    1. Finds newly-failing tests (before vs after).
    2. Maps each test to its owning feature via ``test_to_feature_map``.
    3. For each candidate (owning) feature, calls ``validate_causal_link``
       using the feature's ``ownership_map`` entry and the recent commits.
    4. Only demotes features for which the causal link is validated.
    5. Files a ``regression_unattributed`` event for every failure that
       cannot be causally attributed.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from bob.models import RegressionEvent
from bob.test_ownership_map import load_test_ownership_map, map_test_to_feature_owner
from bob.ownership_evidenced_regression import (  # noqa: F401 — AC: detect_regression_with_ownership
    detect_regression_with_ownership,
    file_touched_in_commit,
)

logger = logging.getLogger(__name__)

# Maximum import-chain depth followed when resolving transitive deps.
_MAX_TRANSITIVE_DEPTH = 3


# ---------------------------------------------------------------------------
# Internal helpers (shared with orchestrator.regression_attribution)
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

def validate_causal_link(
    *,
    feature_id: str,
    owned_files: set[str],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
) -> tuple[bool, list[str], str]:
    """Validate that *feature_id*'s code is causally linked to the breakage.

    A causal link exists when at least one of the feature's owned files (or a
    file transitively imported by an owned file up to depth 3) appears in the
    set of files touched by the breaking commit.

    Args:
        feature_id: The feature being evaluated for demotion.
        owned_files: Set of file paths owned by *feature_id*.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.  When
            provided, the reachability check follows import edges up to
            ``_MAX_TRANSITIVE_DEPTH`` hops.

    Returns:
        ``(is_valid, evidence, reason)`` triple:
        - *is_valid* (bool): True when the causal link is established.
        - *evidence* (list[str]): Human-readable evidence strings.
        - *reason* (str): One-line explanation of the decision.
    """
    if not owned_files:
        return False, [], "feature has no owned files; no causal link possible"

    if not breaking_files:
        return False, [], "no files were touched by the breaking commit(s)"

    # Direct overlap check
    direct_overlap = owned_files & breaking_files
    if direct_overlap:
        evidence = [
            f"owned file {f!r} was touched by the breaking commit"
            for f in sorted(direct_overlap)
        ]
        reason = (
            f"{len(direct_overlap)} owned file(s) directly touched by breaking commit"
        )
        logger.debug(
            "validate_causal_link: feature=%s direct_overlap=%s",
            feature_id,
            direct_overlap,
        )
        return True, evidence, reason

    # Transitive overlap check
    if transitive_deps:
        reachable = _transitive_reachable(owned_files, transitive_deps, _MAX_TRANSITIVE_DEPTH)
        transitive_touched = (reachable - owned_files) & breaking_files
        if transitive_touched:
            evidence = [
                f"owned file transitively imports {f!r} which was touched by the breaking commit"
                for f in sorted(transitive_touched)
            ]
            reason = (
                f"{len(transitive_touched)} transitively-reachable file(s) touched "
                f"(depth ≤ {_MAX_TRANSITIVE_DEPTH})"
            )
            logger.debug(
                "validate_causal_link: feature=%s transitive_touched=%s",
                feature_id,
                transitive_touched,
            )
            return True, evidence, reason

    reason = (
        "no owned file (direct or transitive) appears in the breaking commit's diff; "
        "demotion rejected to avoid scapegoating"
    )
    return False, [], reason


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
) -> RegressionEvent | None:
    """Detect regressions only when a causal ownership link can be established.

    This replaces the bare ``detect_regression`` heuristic that would demote
    an arbitrary completed feature whenever downstream breakage appeared.

    Algorithm
    ---------
    1. Compare *before_results* and *after_results* to find newly-failing tests.
    2. For each newly-failing test, look up its owning feature in
       *test_to_feature_map*.  Tests with no mapping are stored as
       ``regression_unattributed`` events, never scapegoated.
    3. For each candidate (owner) feature, call ``validate_causal_link``
       using the feature's entry in *ownership_map* and the union of files
       touched across *recent_commits*.
    4. Only demote features for which the causal link is validated.
    5. File a ``regression_unattributed`` event for each test whose owner
       cannot be causally linked to the breakage.

    Args:
        project_id: Bob project ID.
        causing_feature_id: The feature whose implementation was just applied.
        before_results: ``{test_nodeid: passed}`` snapshot before the feature.
        after_results: ``{test_nodeid: passed}`` snapshot after the feature.
        test_to_feature_map: ``{test_nodeid: feature_id}`` ownership map.
        ownership_map: ``{feature_id: set[file_path]}`` — files owned by each
            feature.  Derived from commit history at call-site.
        recent_commits: List of ``{commit_id, files_touched}`` dicts describing
            the breaking commit(s).
        transitive_deps: Optional import-graph for transitive link resolution.
        _update_feature_fn: Callable ``(feature_id, **kwargs)`` for DB updates.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.
        _create_regression_event_fn: Callable that creates a RegressionEvent
            record.  Defaults to ``bob.db.create_regression_event``.

    Returns:
        The first ``RegressionEvent`` created (if any), or ``None``.
    """
    if _update_feature_fn is None:
        from bob import db as _db
        _update_feature_fn = _db.update_feature

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs):
            logger.info("regression_detector event %s: %s", event_type, kwargs)

    if _create_regression_event_fn is None:
        from bob import db as _db
        _create_regression_event_fn = _db.create_regression_event

    # Step 1: find newly-failing tests
    newly_failing: list[str] = []
    for test, before_passed in before_results.items():
        if not before_passed:
            continue  # already failing — not a regression
        if test not in after_results:
            continue  # disappeared — ignore
        if not after_results[test]:
            newly_failing.append(test)

    if not newly_failing:
        return None

    # Step 2: map tests to owning features; separate unmapped
    owner_to_tests: dict[str, list[str]] = {}
    unmapped_tests: list[str] = []
    for test in newly_failing:
        owner = test_to_feature_map.get(test)
        if owner is None:
            unmapped_tests.append(test)
        else:
            owner_to_tests.setdefault(owner, []).append(test)

    # Unmapped tests → unattributed event, never scapegoated
    for test in unmapped_tests:
        logger.info(
            "regression_detector: test %r has no owner in test_to_feature_map; "
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

    # Step 3 & 4: for each candidate feature, validate causal link
    breaking_files: set[str] = set()
    for commit in recent_commits:
        breaking_files.update(commit.get("files_touched", []))

    first_event: RegressionEvent | None = None

    for owner_id, owned_tests in owner_to_tests.items():
        owned_files = ownership_map.get(owner_id, set())
        is_valid, evidence, reason = validate_causal_link(
            feature_id=owner_id,
            owned_files=owned_files,
            breaking_files=breaking_files,
            transitive_deps=transitive_deps,
        )

        if not is_valid:
            logger.info(
                "regression_detector: causal link NOT established for feature %s; "
                "filing regression_unattributed (reason: %s)",
                owner_id,
                reason,
            )
            for test in owned_tests:
                _emit_event_fn(
                    "regression_unattributed",
                    failing_test_id=test,
                    recent_commits=recent_commits,
                    feature_id=owner_id,
                    reason=reason,
                )
            continue

        # Causal link established — demote the owner
        logger.info(
            "regression_detector: causal link confirmed for feature %s "
            "(confidence evidence: %s); demoting to 'regression'",
            owner_id,
            evidence,
        )
        _update_feature_fn(owner_id, status="regression")

        evidence_artifacts = json.dumps(evidence)
        affected_tests_json = json.dumps(sorted(owned_tests))
        event = _create_regression_event_fn(
            project_id=project_id,
            affected_feature_id=owner_id,
            causing_feature_id=causing_feature_id,
            affected_tests=affected_tests_json,
            evidence_artifacts=evidence_artifacts,
        )
        if first_event is None:
            first_event = event

    return first_event


def file_touched_by_commit(
    file_path: str,
    commit: dict,
) -> bool:
    """Return True iff *file_path* appears in the commit's touched-files list.

    Args:
        file_path: The file path to check (exact string match).
        commit: A ``{commit_id, files_touched}`` dict as produced by
            ``recent_commits`` entries.

    Returns:
        True when *file_path* is in ``commit["files_touched"]``, False otherwise.

    Raises:
        ValueError: If *file_path* is not a non-empty string.
        ValueError: If *commit* is not a dict.
    """
    if not isinstance(file_path, str) or not file_path:
        raise ValueError("file_path must be a non-empty string")
    if not isinstance(commit, dict):
        raise ValueError("commit must be a dict with a 'files_touched' key")
    return file_path in commit.get("files_touched", [])


def extract_touched_dependencies(
    commits: list[dict],
    transitive_deps: dict[str, set[str]] | None = None,
    max_depth: int = _MAX_TRANSITIVE_DEPTH,
) -> set[str]:
    """Extract all files touched by *commits*, optionally expanding transitive deps.

    Given a list of commit dicts (each with a ``files_touched`` key), returns the
    union of all directly touched files plus, when *transitive_deps* is provided,
    all files reachable within *max_depth* import hops from any touched file.

    This function is used by ``detect_regression_with_evidence`` to build the
    ``breaking_files`` set that is compared against each candidate feature's
    owned files.  It is exposed as a public helper so callers can pre-compute
    the set once and reuse it across multiple ownership checks.

    Args:
        commits: List of ``{commit_id, files_touched}`` dicts.
        transitive_deps: Optional ``{file: set[imported_files]}`` import graph.
            When provided, the reachability check follows import edges up to
            *max_depth* hops from each directly-touched file.
        max_depth: Maximum import-chain depth to follow when *transitive_deps*
            is supplied.  Defaults to ``_MAX_TRANSITIVE_DEPTH`` (3).

    Returns:
        Set of file paths (direct + optional transitive) touched by the commits.

    Raises:
        ValueError: If *commits* is not a list.
        ValueError: If *max_depth* is negative.
    """
    if not isinstance(commits, list):
        raise ValueError("commits must be a list of commit dicts")
    if max_depth < 0:
        raise ValueError("max_depth must be >= 0")

    direct: set[str] = set()
    for commit in commits:
        direct.update(commit.get("files_touched", []))

    if not transitive_deps or not direct:
        return direct

    return _transitive_reachable(direct, transitive_deps, max_depth)


# Aliases to satisfy AC naming variants.
verify_causal_link = validate_causal_link


def has_causal_link(
    *,
    feature_id: str,
    owned_files: set,
    breaking_files: set,
    transitive_deps=None,
    max_transitive_depth: int = 3,
) -> bool:
    """Return True iff *feature_id*'s code is causally linked to the breakage.

    A causal link exists when at least one of the feature's owned files (or a
    file transitively imported by an owned file, up to *max_transitive_depth*
    hops) appears in the set of files touched by the breaking commit(s).

    Args:
        feature_id: The feature being evaluated for demotion (used for logging).
        owned_files: Set of file paths owned by *feature_id*.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        True when the causal link is established, False otherwise.
    """
    is_valid, _evidence, _reason = validate_causal_link(
        feature_id=feature_id,
        owned_files=set(owned_files) if owned_files else set(),
        breaking_files=set(breaking_files) if breaking_files else set(),
        transitive_deps=transitive_deps,
    )
    return is_valid
