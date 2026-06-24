"""Multi-candidate dispatch module — AC-required entry points (Feature fd2397de).

This module exposes the multi-candidate patch + LLM-judge vote functions
under the bob.brownfield.multi_candidate namespace, as required by
acceptance criteria for feature fd2397de-6e5d-4cb6-9099-47ac06071392.

All implementation lives in multi_candidate_patch.py; this module provides
the AC-required names as thin re-exports / wrappers.
"""

from __future__ import annotations

from typing import Any, Optional
from pathlib import Path

from bob.brownfield.multi_candidate_patch import (
    CandidatePatch,
    MultiCandidateResult,
    CANDIDATE_COUNT,
    is_hard_feature,
    judge_candidates,
    run_multi_candidate,
    maybe_run_multi_candidate,
    spawn_worker_candidates as _spawn_worker_candidates,
    filter_regressions as _filter_regressions,
)


def spawn_worker_candidates(
    feature: dict[str, Any],
    *,
    workspace: Optional[Path] = None,
    candidate_count: int = CANDIDATE_COUNT,
    patch_generator: Optional[Any] = None,
    test_files: Optional[list[str]] = None,
) -> list[CandidatePatch]:
    """Spawn N worker candidates and return all CandidatePatch objects.

    AC-required entry point: 'Function defined:
    bob.brownfield.multi_candidate.spawn_worker_candidates'.

    Spawn N=3 worker candidates in parallel worktrees per the spec.
    Each produces a patch + test result.

    Args:
        feature: Feature dict with 'id', 'description', 'acceptance_criteria',
                 'difficulty', and 'refinement_attempts' fields.
        workspace: Repository root. Defaults to cwd.
        candidate_count: Number of parallel candidates (default 3).
        patch_generator: Optional callable(worktree_path, feature) -> str.
        test_files: Optional test files for regression detection.

    Returns:
        List of CandidatePatch objects, one per candidate worker.

    Raises:
        ValueError: If feature is not a dict.
    """
    if not isinstance(feature, dict):
        raise ValueError(f"feature must be a dict, got {type(feature)!r}")
    return _spawn_worker_candidates(
        feature,
        workspace=workspace,
        candidate_count=candidate_count,
        patch_generator=patch_generator,
        test_files=test_files,
    )


def filter_regression_breaking(
    candidates: list[CandidatePatch],
) -> list[CandidatePatch]:
    """Filter out candidates that break existing regression tests.

    AC-required entry point: 'Function defined:
    bob.brownfield.multi_candidate.filter_regression_breaking'.

    Per the spec: "Filter: drop any patch that breaks visible existing
    regression tests."

    Returns the subset of candidates whose broke_regression flag is False.
    If all candidates broke regressions, returns the one with fewest failures
    as a fallback (not an empty list).

    Args:
        candidates: List of CandidatePatch objects to filter.

    Returns:
        List of surviving CandidatePatch objects (broke_regression=False),
        or a single-element fallback list if all broke regressions.

    Raises:
        ValueError: If candidates is not a list.
    """
    if not isinstance(candidates, list):
        raise ValueError(f"candidates must be a list, got {type(candidates)!r}")
    return _filter_regressions(candidates)


def rank_by_judge_vote(
    candidates: list[CandidatePatch],
    *,
    feature_description: str = "",
    acceptance_criteria: Optional[list[str]] = None,
) -> list[CandidatePatch]:
    """Rank surviving candidates by LLM-judge vote.

    AC-required entry point: 'Function defined:
    bob.brownfield.multi_candidate.rank_by_judge_vote'.

    Per the spec: "Survivors: LLM-judge sub-agent ranks by patch quality
    (test-pass count, code-style adherence, minimal-diff, spec-AC coverage)."

    Scores candidates on a composite of:
      - test_pass_count (normalized): 40%
      - minimal diff (fewer lines changed): 30%
      - spec-AC coverage (keyword presence in diff): 30%

    Args:
        candidates: List of CandidatePatch objects to rank.
        feature_description: Free-text feature description for AC coverage.
        acceptance_criteria: List of AC strings to check coverage for.

    Returns:
        Candidates sorted descending by composite quality score, with
        .score and .judge_reason populated.

    Raises:
        ValueError: If candidates is not a list.
    """
    if not isinstance(candidates, list):
        raise ValueError(f"candidates must be a list, got {type(candidates)!r}")
    return judge_candidates(
        candidates,
        feature_description=feature_description,
        acceptance_criteria=acceptance_criteria,
    )


__all__ = [
    "CandidatePatch",
    "MultiCandidateResult",
    "is_hard_feature",
    "spawn_worker_candidates",
    "filter_regression_breaking",
    "rank_by_judge_vote",
    "run_multi_candidate",
    "maybe_run_multi_candidate",
]
