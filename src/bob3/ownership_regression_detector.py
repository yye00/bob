"""Ownership-evidenced regression detection — no scapegoat without proof.

Feature 7b27b498-5cbb-4d96-be2f-2f612894adbc

Problem solved
--------------
``detect_regression`` previously demoted arbitrary previously-completed
features to ``regression`` status when downstream breakage appeared, without
establishing a causal link.  A prior generation: F-15f5b3b8
("Blame-the-cause regression cascade") was itself scapegoated.

Per memory/regression_scapegoat_mechanism.md: detection must require evidence
that the demoted feature's own code/tests were touched (or transitively
depended-upon) by the breaking commit.  Without that evidence, the demotion is
rejected and a ``regression_unattributed`` event is filed instead.

Public API
----------
``verify_causal_link``
    Verify whether a causal link exists between a candidate feature's owned
    files and the set of files touched by the breaking commit(s).  Returns
    ``(evidence_exists, evidence_list)``.  No link → returns ``(False, [])``.

``detect_regression_with_evidence``
    End-to-end ownership-evidenced regression detection pipeline.
    Only demotes features with a confirmed causal link to the breaking commit.
    Files ``regression_unattributed`` events for tests that cannot be causally
    attributed — these are never scapegoated.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TRANSITIVE_DEPTH = 3

__all__ = [
    "verify_causal_link",
    "detect_regression_with_evidence",
]


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

def verify_causal_link(
    *,
    feature_id: str,
    owned_files: set[str],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> tuple[bool, list[str]]:
    """Verify whether a causal link exists between *feature_id* and the regression.

    A causal link is established when at least one of the feature's owned files
    (or a file transitively imported by an owned file, up to
    *max_transitive_depth* hops) appears in the set of files touched by the
    breaking commit(s).

    Without this evidence, demotion to ``regression`` is rejected — this is the
    core no-scapegoat-without-proof invariant.

    Args:
        feature_id: Non-empty, non-whitespace string identifying the candidate
            feature.
        owned_files: Set of file paths owned by *feature_id*.
        breaking_files: Set of file paths touched by the breaking commit(s).
        transitive_deps: Optional ``{file: set[imported_files]}``.  When
            provided, the reachability check follows import edges up to
            *max_transitive_depth* hops.
        max_transitive_depth: Maximum import-chain depth to follow (default 3).

    Returns:
        ``(True, evidence_list)`` when a causal link is established, where
        *evidence_list* contains human-readable strings describing the evidence.
        ``(False, [])`` when no link can be found.

    Raises:
        ValueError: When *feature_id* is empty, None, or whitespace-only.
        ValueError: When *owned_files* is not a set or frozenset.
        ValueError: When *breaking_files* is not a set or frozenset.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a non-empty string, got {feature_id!r}"
        )
    if not feature_id.strip():
        raise ValueError(
            f"feature_id must be a non-empty, non-whitespace string, got {feature_id!r}"
        )
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

    direct_overlap = sorted(owned_files & breaking_files)
    if direct_overlap:
        evidence = [
            f"owned file {f!r} appears in the breaking commit diff"
            for f in direct_overlap
        ]
        logger.debug(
            "verify_causal_link: feature=%s direct overlap=%s",
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
                "verify_causal_link: feature=%s transitive overlap=%s",
                feature_id,
                transitive_overlap,
            )
            return True, evidence

    return False, []


def detect_regression_with_evidence(
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
) -> dict[str, Any]:
    """Detect regressions only when ownership evidence is established.

    This replaces the bare ``detect_regression`` heuristic that demoted an
    arbitrary completed feature whenever downstream breakage appeared.  A feature
    MUST NOT be demoted to ``regression`` unless its own files (or files it
    transitively depends upon) appear in the breaking commit's diff.  Without
    that evidence, a ``regression_unattributed`` event is filed instead.

    Algorithm
    ---------
    1. Diff *before_results* vs *after_results* to find newly-failing tests.
    2. Map each failing test to its owning feature via *test_to_feature_map*.
       Tests with no mapping go to the ``"unattributed"`` sentinel — never
       scapegoated onto another feature.
    3. For each candidate (owner) feature, call ``verify_causal_link`` using
       *ownership_map[feature_id]* and *breaking_files*.
    4. Demote only features for which the causal link is confirmed.
    5. File a ``regression_unattributed`` event for every unowned or
       non-evidenced failure.

    Args:
        before_results: ``{test_nodeid: passed}`` snapshot before the change.
        after_results: ``{test_nodeid: passed}`` snapshot after the change.
        test_to_feature_map: ``{test_nodeid: feature_id}`` ownership map.
        ownership_map: ``{feature_id: set[file_path]}`` — files owned by each
            feature.
        breaking_files: Set of all file paths touched by the breaking commit(s).
        transitive_deps: Optional import-graph for transitive link resolution.
        max_transitive_depth: Max import-chain depth (default 3).
        _update_feature_fn: Callable ``(feature_id, status)`` for DB updates.
            When ``None``, updates are logged only.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.
            When ``None``, events are logged only.

    Returns:
        A dict with the following structure::

            {
                "demoted": {
                    "<feature_id>": {
                        "tests": ["<test_nodeid>", ...],
                        "evidence": ["<evidence_string>", ...],
                    },
                    ...
                },
                "unattributed": {
                    "no_owner": ["<test_nodeid>", ...],
                    "no_evidence": {
                        "<feature_id>": ["<test_nodeid>", ...],
                    },
                },
            }

        Only features with confirmed evidence appear under ``"demoted"``.

    Raises:
        TypeError: When *before_results* or *after_results* is not a dict.
        TypeError: When *test_to_feature_map* or *ownership_map* is not a dict.
        TypeError: When *breaking_files* is not a set or frozenset.
    """
    if not isinstance(before_results, dict):
        raise TypeError(
            f"before_results must be a dict, got {type(before_results)!r}"
        )
    if not isinstance(after_results, dict):
        raise TypeError(
            f"after_results must be a dict, got {type(after_results)!r}"
        )
    if not isinstance(test_to_feature_map, dict):
        raise TypeError(
            f"test_to_feature_map must be a dict, got {type(test_to_feature_map)!r}"
        )
    if not isinstance(ownership_map, dict):
        raise TypeError(
            f"ownership_map must be a dict, got {type(ownership_map)!r}"
        )
    if not isinstance(breaking_files, (set, frozenset)):
        raise TypeError(
            f"breaking_files must be a set or frozenset, got {type(breaking_files)!r}"
        )

    if _update_feature_fn is None:
        def _update_feature_fn(fid: str, status: str) -> None:
            logger.info(
                "detect_regression_with_evidence: would demote %s -> %s (no-op)",
                fid,
                status,
            )

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs: Any) -> None:
            logger.info(
                "detect_regression_with_evidence event %s: %s",
                event_type,
                kwargs,
            )

    # Step 1: find newly-failing tests
    newly_failing: list[str] = [
        test
        for test, before_passed in before_results.items()
        if before_passed and test in after_results and not after_results[test]
    ]

    result: dict[str, Any] = {
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
                "detect_regression_with_evidence: test %r has no owner; "
                "filing regression_unattributed (no scapegoat)",
                test,
            )
            _emit_event_fn(
                "regression_unattributed",
                failing_test=test,
                reason="test not present in test_to_feature_map",
                feature_id=None,
            )

    # Steps 3-5: check causal link; demote or reject
    for owner_id, owned_tests in owner_to_tests.items():
        owned_files = ownership_map.get(owner_id, set())
        evidence_exists, evidence_list = verify_causal_link(
            feature_id=owner_id,
            owned_files=owned_files,
            breaking_files=breaking_files,
            transitive_deps=transitive_deps,
            max_transitive_depth=max_transitive_depth,
        )

        if not evidence_exists:
            # Reject demotion — no proof of causal link
            logger.info(
                "detect_regression_with_evidence: NO causal link for feature %s; "
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

        # Causal link confirmed — demote feature
        logger.info(
            "detect_regression_with_evidence: causal link confirmed for feature %s; "
            "demoting to 'regression'",
            owner_id,
        )
        _update_feature_fn(owner_id, "regression")
        result["demoted"][owner_id] = {
            "tests": sorted(owned_tests),
            "evidence": evidence_list,
        }

    return result
