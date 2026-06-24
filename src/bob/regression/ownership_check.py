"""Ownership-evidenced regression detection helpers.

Feature 270d01f1-1208-4968-adb3-f0af1d7c1a40

Provides two public functions for the ownership-evidenced regression detection
pipeline:

``check_regression_ownership``
    High-level check: given a feature's owned files and a list of commits,
    determine whether the feature has causal ownership evidence by looking for
    overlap between its files (direct or transitive) and the union of files
    touched by the commits.  Returns ``(has_evidence, evidence_list)``.

    Raises ``ValueError`` on invalid inputs — never silently succeeds.

``find_touching_commits``
    Given a feature's owned files and a list of commit records, return only
    those commits that touched at least one file owned by (or transitively
    reachable from) the feature.  An empty list means no commit can be causally
    linked; the feature must not be scapegoated.

    Raises ``ValueError`` on invalid inputs.
"""

from __future__ import annotations

import logging
from typing import Any

from bob.regression.ownership_detector import has_ownership_evidence

logger = logging.getLogger(__name__)

__all__ = [
    "check_regression_ownership",
    "find_touching_commits",
]

_DEFAULT_MAX_TRANSITIVE_DEPTH = 3


def check_regression_ownership(
    *,
    feature_id: str,
    owned_files: set[str],
    recent_commits: list[dict[str, Any]],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> tuple[bool, list[str]]:
    """Check whether a feature has causal ownership evidence for a regression.

    This is the authoritative gate before any ``regression`` demotion.  A
    feature MUST NOT be demoted unless this function returns ``(True, ...)``.

    The breaking-file set is derived as the union of all ``files_touched``
    values across *recent_commits*.  The causal link is established when at
    least one of the feature's owned files (or a file transitively imported by
    an owned file, up to *max_transitive_depth* hops) appears in that set.

    Args:
        feature_id: Non-empty string identifying the candidate feature.
        owned_files: Set (or frozenset) of file paths owned by the feature.
        recent_commits: List of ``{commit_id, files_touched}`` dicts describing
            the breaking commit(s).  Each entry's ``files_touched`` value must
            be an iterable of file-path strings.
        transitive_deps: Optional import-graph ``{file: set[imported_files]}``.
            When provided, the reachability check follows import edges up to
            *max_transitive_depth* hops.
        max_transitive_depth: Maximum import-chain depth (default 3).

    Returns:
        ``(has_evidence, evidence_list)`` — has_evidence is True when a causal
        link is established; evidence_list contains human-readable strings.

    Raises:
        ValueError: If *feature_id* is empty, None, or whitespace-only.
        ValueError: If *owned_files* is not a set or frozenset.
        ValueError: If *recent_commits* is not a list.
    """
    if not feature_id or (isinstance(feature_id, str) and not feature_id.strip()):
        raise ValueError("feature_id must be a non-empty, non-whitespace string")
    if not isinstance(owned_files, (set, frozenset)):
        raise ValueError(
            f"owned_files must be a set or frozenset, got {type(owned_files)!r}"
        )
    if not isinstance(recent_commits, list):
        raise ValueError(
            f"recent_commits must be a list, got {type(recent_commits)!r}"
        )

    # Derive breaking-file set from all commits
    breaking_files: set[str] = set()
    for commit in recent_commits:
        breaking_files.update(commit.get("files_touched", []))

    return has_ownership_evidence(
        feature_id=feature_id,
        owned_files=owned_files,
        breaking_files=breaking_files,
        transitive_deps=transitive_deps,
        max_transitive_depth=max_transitive_depth,
    )


def find_touching_commits(
    *,
    feature_id: str,
    owned_files: set[str],
    commits: list[dict[str, Any]],
    transitive_deps: dict[str, set[str]] | None = None,
    max_transitive_depth: int = _DEFAULT_MAX_TRANSITIVE_DEPTH,
) -> list[dict[str, Any]]:
    """Return only those commits that touched files owned by (or reachable from) the feature.

    An empty return value means no commit can be causally linked to this feature;
    the feature MUST NOT be demoted to ``regression`` status.

    Args:
        feature_id: Non-empty string identifying the candidate feature.
        owned_files: Set (or frozenset) of file paths owned by the feature.
        commits: List of ``{commit_id, files_touched}`` dicts to filter.
        transitive_deps: Optional import-graph for transitive resolution.
        max_transitive_depth: Maximum import-chain depth (default 3).

    Returns:
        Filtered list of commit dicts — only those with overlap to owned files.

    Raises:
        ValueError: If *feature_id* is empty, None, or whitespace-only.
        ValueError: If *owned_files* is not a set or frozenset.
        ValueError: If *commits* is not a list.
    """
    if not feature_id or (isinstance(feature_id, str) and not feature_id.strip()):
        raise ValueError("feature_id must be a non-empty, non-whitespace string")
    if not isinstance(owned_files, (set, frozenset)):
        raise ValueError(
            f"owned_files must be a set or frozenset, got {type(owned_files)!r}"
        )
    if not isinstance(commits, list):
        raise ValueError(
            f"commits must be a list, got {type(commits)!r}"
        )

    if not owned_files or not commits:
        return []

    touching: list[dict[str, Any]] = []
    for commit in commits:
        commit_files: set[str] = set(commit.get("files_touched", []))
        if not commit_files:
            continue
        has_ev, _ = has_ownership_evidence(
            feature_id=feature_id,
            owned_files=owned_files,
            breaking_files=commit_files,
            transitive_deps=transitive_deps,
            max_transitive_depth=max_transitive_depth,
        )
        if has_ev:
            touching.append(commit)

    logger.debug(
        "find_touching_commits: feature=%s owned=%s found %d/%d touching commits",
        feature_id,
        len(owned_files),
        len(touching),
        len(commits),
    )
    return touching
