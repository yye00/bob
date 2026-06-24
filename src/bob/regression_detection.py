"""Ownership-evidenced regression detection — no scapegoat without proof.

Feature dc8d200e-a2aa-4bfc-adf0-a224513d52f5

Problem solved
--------------
``detect_regression`` previously demoted arbitrary completed features to
``regression`` status when downstream breakage appeared, without establishing
a causal link.  Observed live in bob version 12 round 9: F-15f5b3b8
("Blame-the-cause regression cascade") was itself scapegoated.

This module provides two public entry points:

``has_causal_link`` — given a candidate feature's owned files and the set of
    files touched by the breaking commit(s), return True iff a causal link can
    be established.  A link exists when at least one owned file (or a file
    transitively imported by an owned file, up to *max_transitive_depth* hops)
    appears in the breaking diff.

``detect_regression_with_evidence`` — end-to-end pipeline that:
    1. Finds newly-failing tests (before vs after comparison).
    2. Maps each failing test to its owning feature via *test_to_feature_map*.
    3. For each candidate feature, calls ``has_causal_link`` using the
       feature's entry in *ownership_map* and the union of files touched across
       *recent_commits*.
    4. Only demotes features for which a causal link is validated.
    5. Files a ``regression_unattributed`` event for every failure that cannot
       be causally attributed to any specific feature.

Integration
-----------
Both functions are re-exported from ``bob.orchestrator`` (see the update to
``bob/orchestrator/__init__.py``).  Call-sites should prefer:

    from bob.orchestrator import detect_regression_with_evidence, has_causal_link
"""

from __future__ import annotations

import json
import logging
from typing import Any

from bob.models import RegressionEvent

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TRANSITIVE_DEPTH = 3


def validate_regression_ownership(
    *,
    feature_id: str,
    owned_files: set[str],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> tuple[bool, list[str]]:
    """Validate whether a feature has ownership evidence for a regression.

    A regression demotion is only valid when the feature's own code or tests
    were touched (directly or transitively depended upon) by the breaking
    commit.  Without that evidence, the demotion is rejected.

    Args:
        feature_id: The feature being evaluated.
        owned_files: Set of file paths owned by the feature.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional import-graph for transitive resolution.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        (has_evidence, evidence_list) where has_evidence is True when a causal
        link is established, and evidence_list contains human-readable strings
        describing the evidence.  evidence_list is empty when has_evidence is
        False.

    Raises:
        ValueError: If feature_id is empty or None.
        ValueError: If owned_files is not a set.
        ValueError: If breaking_files is not a set.
    """
    if not feature_id or (isinstance(feature_id, str) and not feature_id.strip()):
        raise ValueError("feature_id must be a non-empty string")
    if not isinstance(owned_files, (set, frozenset)):
        raise ValueError("owned_files must be a set")
    if not isinstance(breaking_files, (set, frozenset)):
        raise ValueError("breaking_files must be a set")

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
            "validate_regression_ownership: feature=%s direct evidence: %s",
            feature_id,
            direct_overlap,
        )
        return True, evidence

    # Transitive overlap
    if transitive_deps:
        reachable = _transitive_reachable(owned_files, transitive_deps, max_transitive_depth)
        transitive_touched = (reachable - owned_files) & breaking_files
        if transitive_touched:
            evidence = [
                f"owned file transitively imports {f!r} which was touched by the breaking commit"
                for f in sorted(transitive_touched)
            ]
            logger.debug(
                "validate_regression_ownership: feature=%s transitive evidence: %s",
                feature_id,
                transitive_touched,
            )
            return True, evidence

    return False, []


# Alias required by AC: "Function defined: bob.regression_detection.has_ownership_evidence"
has_ownership_evidence = validate_regression_ownership

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

def has_causal_link(
    *,
    feature_id: str,
    owned_files: set[str],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> bool:
    """Return True iff *feature_id*'s code is causally linked to the breakage.

    A causal link exists when at least one of the feature's owned files (or a
    file transitively imported by an owned file, up to *max_transitive_depth*
    hops) appears in the set of files touched by the breaking commit(s).

    Args:
        feature_id: The feature being evaluated for demotion (used for logging).
        owned_files: Set of file paths owned by *feature_id*.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.  When
            provided, the reachability check follows import edges up to
            *max_transitive_depth* hops.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        True when the causal link is established, False otherwise.
    """
    if not owned_files or not breaking_files:
        return False

    # Direct overlap check
    if owned_files & breaking_files:
        logger.debug(
            "has_causal_link: feature=%s direct overlap with breaking files",
            feature_id,
        )
        return True

    # Transitive overlap check
    if transitive_deps:
        reachable = _transitive_reachable(owned_files, transitive_deps, max_transitive_depth)
        if (reachable - owned_files) & breaking_files:
            logger.debug(
                "has_causal_link: feature=%s transitive link to breaking files",
                feature_id,
            )
            return True

    return False


# Alias required by the feature AC ("has_causal_evidence")
has_causal_evidence = has_causal_link


def requires_causal_evidence(
    *,
    feature_id: str,
    owned_files: set[str],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> bool:
    """Enforce the policy that regression demotion requires causal evidence.

    Returns True iff a causal link is established between *feature_id*'s
    owned files and the breaking commit's diff.  A regression demotion MUST
    NOT proceed unless this returns True; without evidence the feature is
    a scapegoat, not a genuine regression.

    This is a policy-enforcement wrapper around ``has_causal_link``.  The
    distinction from ``has_causal_link`` is semantic: this function carries
    the invariant "you must call this before demoting" rather than merely
    answering a question.

    Args:
        feature_id: The feature being evaluated for demotion.
        owned_files: Set of file paths owned by *feature_id*.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        True when causal evidence exists and demotion is permitted.
        False when no evidence exists and demotion must be rejected.

    Raises:
        ValueError: If feature_id is empty/None, or if owned_files/breaking_files
            are not sets/frozensets.
    """
    if not feature_id or (isinstance(feature_id, str) and not feature_id.strip()):
        raise ValueError("feature_id must be a non-empty string")
    if not isinstance(owned_files, (set, frozenset)):
        raise ValueError("owned_files must be a set")
    if not isinstance(breaking_files, (set, frozenset)):
        raise ValueError("breaking_files must be a set")

    return has_causal_link(
        feature_id=feature_id,
        owned_files=owned_files,
        breaking_files=breaking_files,
        transitive_deps=transitive_deps,
        max_transitive_depth=max_transitive_depth,
    )


def validate_feature_involvement(
    *,
    feature_id: str,
    owned_files: set[str],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> tuple[bool, list[str]]:
    """Validate that a feature is involved in a regression before demoting it.

    A feature is considered involved in a regression when at least one of its
    owned files (or a file transitively imported by an owned file, up to
    *max_transitive_depth* hops) appears in the set of files touched by the
    breaking commit(s).  Without this involvement, demotion to ``regression``
    is rejected — no scapegoat without proof.

    This is the canonical pre-demotion guard: callers MUST invoke this before
    demoting a feature to ``regression`` status.

    Args:
        feature_id: The feature being evaluated for demotion.
        owned_files: Set of file paths owned by *feature_id*.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.  When
            provided, the reachability check follows import edges up to
            *max_transitive_depth* hops.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        ``(is_involved, evidence_list)`` where *is_involved* is True when
        involvement is established and *evidence_list* contains human-readable
        strings describing the evidence.  *evidence_list* is empty when
        *is_involved* is False.

    Raises:
        ValueError: If feature_id is empty/None or not a non-whitespace string.
        ValueError: If owned_files is not a set or frozenset.
        ValueError: If breaking_files is not a set or frozenset.
    """
    if not feature_id or (isinstance(feature_id, str) and not feature_id.strip()):
        raise ValueError("feature_id must be a non-empty string")
    if not isinstance(owned_files, (set, frozenset)):
        raise ValueError("owned_files must be a set")
    if not isinstance(breaking_files, (set, frozenset)):
        raise ValueError("breaking_files must be a set")

    return validate_regression_ownership(
        feature_id=feature_id,
        owned_files=owned_files,
        breaking_files=breaking_files,
        transitive_deps=transitive_deps,
        max_transitive_depth=max_transitive_depth,
    )


def file_or_dependency_touched(
    *,
    file_path: str,
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> bool:
    """Return True iff *file_path* or any of its transitive dependencies was touched.

    This is the single-file variant of ``has_causal_link``: given one file
    (typically an owned source file) and the set of files touched by the
    breaking commit(s), determine whether the file is causally involved.

    A file is considered touched when:
    - It appears directly in *breaking_files*, OR
    - One of its transitive dependencies (up to *max_transitive_depth* hops
      in *transitive_deps*) appears in *breaking_files*.

    Args:
        file_path: The file to test for involvement.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        True when the file (or a transitive dependency) is in *breaking_files*.
        False otherwise.

    Raises:
        ValueError: If *file_path* is empty or not a string.
        ValueError: If *breaking_files* is not a set or frozenset.
    """
    if not file_path or not isinstance(file_path, str):
        raise ValueError("file_path must be a non-empty string")
    if not isinstance(breaking_files, (set, frozenset)):
        raise ValueError("breaking_files must be a set")

    if file_path in breaking_files:
        return True

    if transitive_deps and breaking_files:
        reachable = _transitive_reachable({file_path}, transitive_deps, max_transitive_depth)
        if (reachable - {file_path}) & breaking_files:
            return True

    return False


# ---------------------------------------------------------------------------
# AC-required aliases: is_regression_ownership_evidenced, check_causal_link
# ---------------------------------------------------------------------------

def is_regression_ownership_evidenced(
    *,
    feature_id: str,
    owned_files: set[str],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> bool:
    """Return True iff the feature has ownership evidence for a regression.

    Policy wrapper: a feature must NOT be demoted to ``regression`` unless
    this returns True.  Delegates to ``validate_regression_ownership`` and
    returns only the boolean verdict.

    Args:
        feature_id: The feature being evaluated for demotion.
        owned_files: Set of file paths owned by *feature_id*.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        True when ownership evidence exists (demotion is permitted).
        False when no evidence exists (demotion must be rejected).

    Raises:
        ValueError: If feature_id is empty/None or not a non-whitespace string.
        ValueError: If owned_files or breaking_files are not sets/frozensets.
    """
    has_evidence, _ = validate_regression_ownership(
        feature_id=feature_id,
        owned_files=owned_files,
        breaking_files=breaking_files,
        transitive_deps=transitive_deps,
        max_transitive_depth=max_transitive_depth,
    )
    return has_evidence


def check_causal_link(
    *,
    feature_id: str,
    owned_files: set[str],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> bool:
    """Check whether a causal link exists between *feature_id* and the regression.

    Alias of ``has_causal_link`` with an explicit name that signals intent:
    "check" conveys that this is a guard call before a potential demotion.
    Returns True iff the feature's owned files (directly or transitively) overlap
    with the set of files touched by the breaking commit(s).

    Args:
        feature_id: The feature being evaluated (used for logging).
        owned_files: Set of file paths owned by *feature_id*.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        True when the causal link is established.
        False otherwise.
    """
    return has_causal_link(
        feature_id=feature_id,
        owned_files=owned_files,
        breaking_files=breaking_files,
        transitive_deps=transitive_deps,
        max_transitive_depth=max_transitive_depth,
    )


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
       *test_to_feature_map*.  Tests with no mapping are emitted as
       ``regression_unattributed`` events; they are never scapegoated.
    3. For each candidate (owner) feature, call ``has_causal_link`` using the
       feature's entry in *ownership_map* and the union of files touched across
       *recent_commits*.
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
            the breaking commit(s).  The union of all ``files_touched`` values
            forms the full breaking-file set.
        transitive_deps: Optional import-graph for transitive link resolution.
        _update_feature_fn: Callable ``(feature_id, status)`` for DB updates.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.
        _create_regression_event_fn: Callable that creates a RegressionEvent
            record.  Defaults to ``bob.db.create_regression_event``.

    Returns:
        The first ``RegressionEvent`` created (if any), or ``None``.
    """
    if _update_feature_fn is None:
        from bob import db as _db
        _update_feature_fn = lambda fid, status: _db.update_feature(fid, status=status)

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs):
            logger.info("regression_detection event %s: %s", event_type, kwargs)

    if _create_regression_event_fn is None:
        from bob import db as _db
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
            "regression_detection: test %r has no owner in test_to_feature_map; "
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

    first_event: RegressionEvent | None = None

    # Steps 3 & 4: validate causal link; demote only if confirmed
    for owner_id, owned_tests in owner_to_tests.items():
        owned_files = ownership_map.get(owner_id, set())
        link_exists = has_causal_link(
            feature_id=owner_id,
            owned_files=owned_files,
            breaking_files=breaking_files,
            transitive_deps=transitive_deps,
        )

        if not link_exists:
            logger.info(
                "regression_detection: causal link NOT established for feature %s; "
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

        # Causal link confirmed — demote the owner
        logger.info(
            "regression_detection: causal link confirmed for feature %s; "
            "demoting to 'regression'",
            owner_id,
        )
        _update_feature_fn(owner_id, "regression")

        direct_evidence = sorted(owned_files & breaking_files)
        evidence: list[str] = [
            f"owned file {f!r} was touched by the breaking commit"
            for f in direct_evidence
        ]
        if not evidence and transitive_deps:
            reachable = _transitive_reachable(owned_files, transitive_deps, _DEFAULT_MAX_TRANSITIVE_DEPTH)
            transitive_touched = sorted((reachable - owned_files) & breaking_files)
            evidence = [
                f"owned file transitively imports {f!r} which was touched by the breaking commit"
                for f in transitive_touched
            ]

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
