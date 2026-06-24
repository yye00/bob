"""Ownership-evidenced regression detection — no scapegoat without proof.

Feature a395f8d5-01c0-49d5-83bd-76c235667e20

Problem solved
--------------
``detect_regression`` previously demoted arbitrary previously-completed
features to ``regression`` status when downstream breakage appeared, without
establishing a causal link.  Observed live in bob version 12 round 9:
F-15f5b3b8 ("Blame-the-cause regression cascade") was itself scapegoated.

Per memory/regression_scapegoat_mechanism.md: detection must require evidence
that the demoted feature's own code/tests were touched (or transitively
depended-upon) by the breaking commit.  Without that evidence, the demotion
is rejected and a ``regression_unattributed`` event is filed instead.

Public API
----------
``ownership_evidenced_regression_detection_no_scapegoat_without_proof``
    End-to-end entry point.  Given before/after test results, a
    test-to-feature ownership map, a file-ownership map per feature, and the
    set of files touched by the breaking commit(s), this function:

    1. Identifies newly-failing tests (passed before, fail after).
    2. Maps each failing test to its owning feature.
    3. For each candidate feature, checks whether the causal link is
       established: at least one of its owned files (or a transitively
       imported file) must appear in the breaking diff.
    4. Demotes only features for which the causal link is confirmed.
    5. Files a ``regression_unattributed`` event for every failure that
       cannot be causally attributed — these are never scapegoated.

    Returns a ``RegressionAttributionResult`` describing what was demoted,
    what was left unattributed, and the evidence collected.
"""

from __future__ import annotations

import json
import logging
from typing import Any

__all__ = [
    "ownership_evidenced_regression_detection_no_scapegoat_without_proof",
    "has_ownership_evidence",
    "RegressionAttributionResult",
]

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TRANSITIVE_DEPTH = 3

# Sentinel key for tests that cannot be attributed to any feature.
UNATTRIBUTED_KEY = "unattributed"

# Type alias for structured result.
RegressionAttributionResult = dict[str, Any]


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
        feature_id: Feature being evaluated (used for logging).
        owned_files: File paths owned by *feature_id*.
        breaking_files: File paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.  When
            provided, the reachability check follows import edges up to
            *max_transitive_depth* hops.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        ``(True, evidence_list)`` when a causal link is established.
        ``(False, [])`` when no link can be found.
    """
    if not owned_files or not breaking_files:
        return False, []

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

    if transitive_deps:
        reachable = _transitive_reachable(owned_files, transitive_deps, max_transitive_depth)
        transitive_overlap = sorted((reachable - owned_files) & breaking_files)
        if transitive_overlap:
            evidence = [
                f"owned file transitively imports {f!r} which appears in the breaking commit diff"
                for f in transitive_overlap
            ]
            logger.debug(
                "has_ownership_evidence: feature=%s transitive overlap=%s",
                feature_id,
                transitive_overlap,
            )
            return True, evidence

    return False, []


def ownership_evidenced_regression_detection_no_scapegoat_without_proof(
    *,
    before_results: dict[str, bool],
    after_results: dict[str, bool],
    test_to_feature_map: dict[str, str],
    ownership_map: dict[str, set[str]],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> RegressionAttributionResult:
    """Detect regressions only when ownership evidence is established.

    This is the canonical guard against the scapegoat anti-pattern: a feature
    MUST NOT be demoted to ``regression`` unless its own files (or files it
    transitively depends upon) appear in the breaking commit's diff.

    Algorithm
    ---------
    1. Diff *before_results* vs *after_results* to find newly-failing tests.
    2. Map each failing test to its owning feature via *test_to_feature_map*.
       Tests with no mapping go to the ``"unattributed"`` sentinel — never
       scapegoated onto another feature.
    3. For each candidate (owner) feature, call ``has_ownership_evidence``
       using *ownership_map[feature_id]* and *breaking_files*.
    4. Demote only features for which evidence is confirmed.
    5. File a ``regression_unattributed`` event for every unowned or
       non-evidenced failure.

    Args:
        before_results: ``{test_nodeid: passed}`` snapshot before the change.
        after_results: ``{test_nodeid: passed}`` snapshot after the change.
        test_to_feature_map: ``{test_nodeid: feature_id}`` ownership map.
        ownership_map: ``{feature_id: set[file_path]}`` — files owned by each
            feature.
        breaking_files: Union of all file paths touched by the breaking
            commit(s).
        transitive_deps: Optional import-graph for transitive link resolution.
        max_transitive_depth: Max import-chain depth (default 3).
        _update_feature_fn: Callable ``(feature_id, status)`` for DB updates.
            When ``None``, updates are no-ops (logged only).
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.
            When ``None``, events are logged only.

    Returns:
        ``RegressionAttributionResult`` — a dict with the following structure::

            {
                "demoted": {
                    "<feature_id>": {
                        "tests": ["<test_nodeid>", ...],
                        "evidence": ["<evidence_string>", ...],
                    },
                    ...
                },
                "unattributed": {
                    "no_owner": ["<test_nodeid>", ...],   # tests not in ownership map
                    "no_evidence": {
                        "<feature_id>": ["<test_nodeid>", ...],  # owned but no file link
                    },
                },
            }

        Only features with confirmed evidence appear under ``"demoted"``.
    """
    if _update_feature_fn is None:
        def _update_feature_fn(fid: str, status: str) -> None:
            logger.info(
                "ownership_evidenced_regression_detection: would demote %s -> %s",
                fid,
                status,
            )

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs: Any) -> None:
            logger.info(
                "ownership_evidenced_regression_detection event %s: %s",
                event_type,
                kwargs,
            )

    # Step 1: find newly-failing tests
    newly_failing: list[str] = [
        test
        for test, before_passed in before_results.items()
        if before_passed and test in after_results and not after_results[test]
    ]

    result: RegressionAttributionResult = {
        "demoted": {},
        "unattributed": {
            "no_owner": [],
            "no_evidence": {},
        },
    }

    if not newly_failing:
        return result

    # Step 2: partition tests by owner
    owner_to_tests: dict[str, list[str]] = {}
    no_owner_tests: list[str] = []

    for test in newly_failing:
        owner = test_to_feature_map.get(test)
        if owner is None:
            no_owner_tests.append(test)
        else:
            owner_to_tests.setdefault(owner, []).append(test)

    # Unowned tests → unattributed; never scapegoated
    if no_owner_tests:
        result["unattributed"]["no_owner"] = sorted(no_owner_tests)
        for test in no_owner_tests:
            logger.info(
                "ownership_evidenced_regression_detection: test %r has no owner; "
                "filing regression_unattributed (no scapegoat)",
                test,
            )
            _emit_event_fn(
                "regression_unattributed",
                failing_test=test,
                reason="test not present in test_to_feature_map",
                feature_id=None,
            )

    # Steps 3-5: check ownership evidence; demote or reject
    for owner_id, owned_tests in owner_to_tests.items():
        owned_files = ownership_map.get(owner_id, set())
        evidence_exists, evidence_list = has_ownership_evidence(
            feature_id=owner_id,
            owned_files=owned_files,
            breaking_files=breaking_files,
            transitive_deps=transitive_deps,
            max_transitive_depth=max_transitive_depth,
        )

        if not evidence_exists:
            # Reject demotion — no proof of causal link
            logger.info(
                "ownership_evidenced_regression_detection: NO evidence for feature %s; "
                "demotion REJECTED to prevent scapegoating; filing regression_unattributed",
                owner_id,
            )
            result["unattributed"]["no_evidence"][owner_id] = sorted(owned_tests)
            for test in owned_tests:
                _emit_event_fn(
                    "regression_unattributed",
                    failing_test=test,
                    feature_id=owner_id,
                    reason=(
                        "no owned file (direct or transitive) appears in the breaking "
                        "commit diff; demotion rejected to avoid scapegoating"
                    ),
                )
            continue

        # Evidence confirmed — demote feature
        logger.info(
            "ownership_evidenced_regression_detection: evidence confirmed for feature %s; "
            "demoting to 'regression'",
            owner_id,
        )
        _update_feature_fn(owner_id, "regression")
        result["demoted"][owner_id] = {
            "tests": sorted(owned_tests),
            "evidence": evidence_list,
        }

    return result
