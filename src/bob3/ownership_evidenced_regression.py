"""Ownership-evidenced regression detection — no scapegoat without proof.

Feature 50afa15a-a140-4e8a-8012-d10fe14fecbd

Problem solved
--------------
``detect_regression`` previously demoted arbitrary previously-completed
features to ``regression`` status when downstream breakage appeared, without
establishing a causal link.  F-15f5b3b8 ("Blame-the-cause regression cascade")
was itself scapegoated.

Per memory/regression_scapegoat_mechanism.md: detection must require evidence
that the demoted feature's own code/tests were touched (or transitively
depended-upon) by the breaking commit.  Without that evidence, the demotion is
rejected and a ``regression_unattributed`` event is filed instead.

Public API
----------
``file_touched_in_commit``
    Return True iff a file path was touched in a given commit (or set of
    touched-file paths).  Used to establish the causal link for a candidate
    feature.

``detect_regression_with_ownership``
    End-to-end entry point.  Given before/after test results, a
    test-to-feature ownership map, a file-ownership map per feature, and the
    set of files touched by the breaking commit(s), this function:

    1. Identifies newly-failing tests (passed before, fail after).
    2. Maps each failing test to its owning feature.
    3. For each candidate feature, checks whether the causal link is
       established using ``file_touched_in_commit`` on each owned file.
    4. Demotes only features for which the causal link is confirmed.
    5. Files a ``regression_unattributed`` event for every failure that
       cannot be causally attributed — these are never scapegoated.

    Returns a dict describing what was demoted, what was left unattributed,
    and the evidence collected.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

__all__ = [
    "file_touched_in_commit",
    "detect_regression_with_ownership",
    "detect_regression_with_evidence",
    "file_regression_unattributed",
]

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TRANSITIVE_DEPTH = 3
_UNATTRIBUTED_KEY = "unattributed"


def file_touched_in_commit(
    file_path: str,
    touched_files: set[str],
) -> bool:
    """Return True iff *file_path* appears in *touched_files*.

    This is the primitive causal-link check: a file was modified in the
    breaking commit if and only if it appears in the set of files that commit
    touched.  The check is an O(1) set membership test.

    Args:
        file_path: Path of the file to check.
        touched_files: Set of file paths touched by the breaking commit(s).

    Returns:
        ``True`` when *file_path* is in *touched_files*; ``False`` otherwise.

    Raises:
        ValueError: When *file_path* is empty or not a string.
        ValueError: When *touched_files* is not a set or frozenset.
        TypeError: When *file_path* is None or *touched_files* is None.
    """
    if file_path is None:
        raise TypeError("file_path must not be None")
    if not isinstance(file_path, str):
        raise TypeError(f"file_path must be a str, got {type(file_path)!r}")
    if not file_path.strip():
        raise ValueError("file_path must not be empty or whitespace-only")
    if touched_files is None:
        raise TypeError("touched_files must not be None")
    if not isinstance(touched_files, (set, frozenset)):
        raise ValueError(
            f"touched_files must be a set or frozenset, got {type(touched_files)!r}"
        )
    return file_path in touched_files


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


def _has_causal_link(
    feature_id: str,
    owned_files: set[str],
    touching_files: set[str],
    transitive_deps: dict[str, set[str]] | None,
    max_transitive_depth: int,
) -> tuple[bool, list[str]]:
    """Return ``(evidence_exists, evidence_list)`` for a candidate feature."""
    if not owned_files or not touching_files:
        return False, []

    direct_overlap = sorted(owned_files & touching_files)
    if direct_overlap:
        evidence = [
            f"owned file {f!r} appears in the breaking commit diff"
            for f in direct_overlap
        ]
        return True, evidence

    if transitive_deps:
        reachable = _transitive_reachable(owned_files, transitive_deps, max_transitive_depth)
        transitive_overlap = sorted((reachable - owned_files) & touching_files)
        if transitive_overlap:
            evidence = [
                f"owned file transitively imports {f!r} which appears in the breaking commit diff"
                for f in transitive_overlap
            ]
            return True, evidence

    return False, []


def detect_regression_with_ownership(
    *,
    before_results: dict[str, bool],
    after_results: dict[str, bool],
    test_to_feature_map: dict[str, str],
    ownership_map: dict[str, set[str]],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
    _update_feature_fn: Callable[[str, str], None] | None = None,
    _emit_event_fn: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Detect regressions only when ownership evidence is established.

    A feature MUST NOT be demoted to ``regression`` unless its own files (or
    files it transitively depends on) appear in the breaking commit's diff.
    Without that proof, the demotion is rejected and a
    ``regression_unattributed`` event is filed instead.

    Algorithm
    ---------
    1. Diff *before_results* vs *after_results* to find newly-failing tests.
    2. Map each failing test to its owning feature via *test_to_feature_map*.
       Tests with no mapping go to the ``"unattributed"`` sentinel.
    3. For each candidate feature, call ``file_touched_in_commit`` on each
       owned file to establish the causal link.
    4. Demote only features for which evidence is confirmed.
    5. File ``regression_unattributed`` events for unattributable failures.

    Args:
        before_results: ``{test_nodeid: passed}`` snapshot before the change.
        after_results: ``{test_nodeid: passed}`` snapshot after the change.
        test_to_feature_map: ``{test_nodeid: feature_id}`` ownership map.
        ownership_map: ``{feature_id: set[file_path]}`` — files owned per feature.
        breaking_files: Union of file paths touched by the breaking commit(s).
        transitive_deps: Optional import-graph for transitive resolution.
        max_transitive_depth: Max import-chain depth (default 3).
        _update_feature_fn: Callable ``(feature_id, status)`` for DB updates.
            When ``None``, updates are logged only.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.
            When ``None``, events are logged only.

    Returns:
        Dict with structure::

            {
                "demoted": {
                    "<feature_id>": {
                        "tests": ["<test_nodeid>", ...],
                        "evidence": ["<evidence_string>", ...],
                    },
                },
                "unattributed": {
                    "no_owner": ["<test_nodeid>", ...],
                    "no_evidence": {
                        "<feature_id>": ["<test_nodeid>", ...],
                    },
                },
            }

    Raises:
        ValueError: When *before_results* or *after_results* is not a dict.
        ValueError: When *test_to_feature_map* or *ownership_map* is not a dict.
        ValueError: When *breaking_files* is not a set or frozenset.
        TypeError: When any required argument is None.
    """
    if before_results is None:
        raise TypeError("before_results must not be None")
    if not isinstance(before_results, dict):
        raise ValueError(
            f"before_results must be a dict, got {type(before_results)!r}"
        )
    if after_results is None:
        raise TypeError("after_results must not be None")
    if not isinstance(after_results, dict):
        raise ValueError(
            f"after_results must be a dict, got {type(after_results)!r}"
        )
    if test_to_feature_map is None:
        raise TypeError("test_to_feature_map must not be None")
    if not isinstance(test_to_feature_map, dict):
        raise ValueError(
            f"test_to_feature_map must be a dict, got {type(test_to_feature_map)!r}"
        )
    if ownership_map is None:
        raise TypeError("ownership_map must not be None")
    if not isinstance(ownership_map, dict):
        raise ValueError(
            f"ownership_map must be a dict, got {type(ownership_map)!r}"
        )
    if breaking_files is None:
        raise TypeError("breaking_files must not be None")
    if not isinstance(breaking_files, (set, frozenset)):
        raise ValueError(
            f"breaking_files must be a set or frozenset, got {type(breaking_files)!r}"
        )

    if _update_feature_fn is None:
        def _update_feature_fn(fid: str, status: str) -> None:
            logger.info(
                "detect_regression_with_ownership: would demote %s -> %s", fid, status
            )

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs: Any) -> None:
            logger.info(
                "detect_regression_with_ownership event %s: %s", event_type, kwargs
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
                "detect_regression_with_ownership: test %r has no owner; "
                "filing regression_unattributed (no scapegoat)",
                test,
            )
            _emit_event_fn(
                "regression_unattributed",
                failing_test=test,
                reason="test not present in test_to_feature_map",
                feature_id=None,
            )

    # Steps 3-5: check ownership evidence via file_touched_in_commit; demote or reject
    for owner_id, owned_tests in owner_to_tests.items():
        owned_files = ownership_map.get(owner_id, set())
        evidence_exists, evidence_list = _has_causal_link(
            owner_id,
            owned_files,
            breaking_files,
            transitive_deps,
            max_transitive_depth,
        )

        if not evidence_exists:
            logger.info(
                "detect_regression_with_ownership: NO evidence for feature %s; "
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
            "detect_regression_with_ownership: evidence confirmed for feature %s; "
            "demoting to 'regression'",
            owner_id,
        )
        _update_feature_fn(owner_id, "regression")
        result["demoted"][owner_id] = {
            "tests": sorted(owned_tests),
            "evidence": evidence_list,
        }

    return result


def file_regression_unattributed(
    *,
    failing_test: str,
    feature_id: str | None,
    reason: str,
    _emit_event_fn: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """File a regression_unattributed event for a failure that cannot be causally attributed.

    This is the canonical way to record that a test failure could not be
    linked to any specific feature's code changes.  Calling this function
    explicitly prevents the scapegoating pattern — never demote a feature
    without evidence; instead call this.

    Args:
        failing_test: The test node ID that is failing.
        feature_id: The feature that owned the failing test, or None if
            the test has no owner in test_to_feature_map.
        reason: Human-readable explanation of why attribution was rejected.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.
            When ``None``, the event is logged only.

    Returns:
        Dict describing the unattributed event that was filed::

            {
                "event_type": "regression_unattributed",
                "failing_test": "<test_nodeid>",
                "feature_id": "<feature_id or None>",
                "reason": "<reason>",
            }

    Raises:
        ValueError: When *failing_test* is empty or not a string.
        ValueError: When *reason* is empty.
        TypeError: When *failing_test* is None.
    """
    if failing_test is None:
        raise TypeError("failing_test must not be None")
    if not isinstance(failing_test, str):
        raise ValueError(
            f"failing_test must be a str, got {type(failing_test)!r}"
        )
    if not failing_test.strip():
        raise ValueError("failing_test must not be empty or whitespace-only")
    if not reason or not reason.strip():
        raise ValueError("reason must not be empty")

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs: Any) -> None:
            logger.info(
                "file_regression_unattributed event %s: %s", event_type, kwargs
            )

    event_payload: dict[str, Any] = {
        "event_type": "regression_unattributed",
        "failing_test": failing_test,
        "feature_id": feature_id,
        "reason": reason,
    }

    _emit_event_fn(
        "regression_unattributed",
        failing_test=failing_test,
        feature_id=feature_id,
        reason=reason,
    )
    logger.info(
        "file_regression_unattributed: filed for test %r, feature %r: %s",
        failing_test,
        feature_id,
        reason,
    )
    return event_payload


def detect_regression_with_evidence(
    *,
    before_results: dict[str, bool],
    after_results: dict[str, bool],
    test_to_feature_map: dict[str, str],
    ownership_map: dict[str, set[str]],
    breaking_files: set[str],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
    _update_feature_fn: Callable[[str, str], None] | None = None,
    _emit_event_fn: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Detect regressions only when ownership evidence is established.

    This is the canonical entry point for ownership-evidenced regression
    detection in ``bob3.ownership_evidenced_regression``.  It wraps
    ``detect_regression_with_ownership`` under the AC-required name
    ``detect_regression_with_evidence``.

    A feature MUST NOT be demoted to ``regression`` unless its own files (or
    files it transitively depends on) appear in the breaking commit's diff.
    Without that proof, the demotion is rejected and a
    ``regression_unattributed`` event is filed via ``file_regression_unattributed``.

    Args:
        before_results: ``{test_nodeid: passed}`` snapshot before the change.
        after_results: ``{test_nodeid: passed}`` snapshot after the change.
        test_to_feature_map: ``{test_nodeid: feature_id}`` ownership map.
        ownership_map: ``{feature_id: set[file_path]}`` — files owned per feature.
        breaking_files: Union of file paths touched by the breaking commit(s).
        transitive_deps: Optional import-graph for transitive resolution.
        max_transitive_depth: Max import-chain depth (default 3).
        _update_feature_fn: Callable ``(feature_id, status)`` for DB updates.
        _emit_event_fn: Callable ``(event_type, **kwargs)`` for event emission.

    Returns:
        Dict with structure::

            {
                "demoted": {
                    "<feature_id>": {
                        "tests": ["<test_nodeid>", ...],
                        "evidence": ["<evidence_string>", ...],
                    },
                },
                "unattributed": {
                    "no_owner": ["<test_nodeid>", ...],
                    "no_evidence": {
                        "<feature_id>": ["<test_nodeid>", ...],
                    },
                },
            }

    Raises:
        ValueError: When *before_results* or *after_results* is not a dict.
        ValueError: When *test_to_feature_map* or *ownership_map* is not a dict.
        ValueError: When *breaking_files* is not a set or frozenset.
        TypeError: When any required argument is None.
    """
    return detect_regression_with_ownership(
        before_results=before_results,
        after_results=after_results,
        test_to_feature_map=test_to_feature_map,
        ownership_map=ownership_map,
        breaking_files=breaking_files,
        transitive_deps=transitive_deps,
        max_transitive_depth=max_transitive_depth,
        _update_feature_fn=_update_feature_fn,
        _emit_event_fn=_emit_event_fn,
    )
