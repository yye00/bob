"""Brownfield orchestrator — integration of BF-4 Hierarchical Localizer.

AC: integration: bob.brownfield.orchestrator

This module wires the BF-4 hierarchical localizer into the brownfield
orchestration pipeline. It provides coordinator-facing helpers that:

  1. Run localization before dispatching code-write subagents.
  2. Persist localization results to feature.localization.
  3. Enforce disjoint write surfaces across concurrently dispatched features.

Usage from coordinator:
    from bob.brownfield.orchestrator import localize_feature, check_disjoint_features
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from bob.brownfield.localizer import (
    check_disjoint,
    hierarchical_localize,
    localize_and_persist,
)
from bob.brownfield.search_subagent import (
    LOCALIZER_OVERFLOW_THRESHOLD,
    SearchResult,
    should_use_search_subagent,
    spawn_search_subagent,
)
from bob.brownfield.multi_candidate_patch import (
    is_hard_feature,
    maybe_run_multi_candidate,
    rank_candidates_with_judge,
    MultiCandidateResult,
)

logger = logging.getLogger(__name__)


def localize_feature(
    feature_id: str,
    intent: dict[str, Any],
    *,
    survey_db: Optional[Path] = None,
    top_k_files: int = 15,
    top_k_symbols: int = 5,
) -> dict[str, Any]:
    """Run hierarchical localization for a feature and persist the result.

    Coordinator entry point for BF-4 localization. Runs:
      Stage A — BM25 file shortlist.
      Stage B — pagerank*cosine symbol ranking.
      Stage C — edit-site extraction.

    Persists the result to feature.localization (best-effort; DB errors are
    logged and silenced so localization output is still returned).

    Args:
        feature_id:    Feature UUID string.
        intent:        Intent dict with capability, target_subsystem, keywords.
        survey_db:     Path to survey.db. None → returns empty result.
        top_k_files:   Stage A budget (default 15).
        top_k_symbols: Stage B budget (default 5).

    Returns:
        Dict with keys: files, symbols, edit_sites.
    """
    logger.debug(
        "BF-4 localize_feature: feature_id=%s intent_keys=%s survey_db=%s",
        feature_id,
        list(intent.keys()) if intent else [],
        survey_db,
    )

    result = localize_and_persist(
        feature_id,
        intent,
        survey_db=survey_db,
        top_k_files=top_k_files,
        top_k_symbols=top_k_symbols,
    )

    logger.debug(
        "BF-4 localize_feature done: files=%d symbols=%d edit_sites=%d",
        len(result.get("files", [])),
        len(result.get("symbols", [])),
        len(result.get("edit_sites", [])),
    )

    return result


def check_disjoint_features(
    loc_a: dict[str, Any],
    loc_b: dict[str, Any],
) -> bool:
    """Check whether two feature localizations overlap on (path, scope).

    Returns True if the features overlap (not safe to dispatch concurrently).
    Returns False if they are disjoint (safe to dispatch concurrently).

    Args:
        loc_a: localize_feature() result for feature A.
        loc_b: localize_feature() result for feature B.

    Returns:
        True  — overlap detected, serialize these features.
        False — disjoint, safe to dispatch concurrently.
    """
    return check_disjoint(loc_a, loc_b)


def run_localization_pipeline(
    intent: dict[str, Any],
    *,
    survey_db: Optional[Path] = None,
    top_k_files: int = 15,
    top_k_symbols: int = 5,
) -> dict[str, Any]:
    """Run the full BF-4 hierarchical localization pipeline without persistence.

    Thin wrapper around hierarchical_localize for orchestrator callers that
    want the full pipeline result without a feature_id (e.g. during dry-run
    planning).

    Args:
        intent:        Intent dict with capability, target_subsystem, keywords.
        survey_db:     Path to survey.db.
        top_k_files:   Stage A budget.
        top_k_symbols: Stage B budget.

    Returns:
        Dict with keys: files, symbols, edit_sites.
    """
    return hierarchical_localize(
        intent,
        survey_db=survey_db,
        top_k_files=top_k_files,
        top_k_symbols=top_k_symbols,
    )


def localize_with_search_fallback(
    feature_id: str,
    intent: dict[str, Any],
    *,
    survey_db: Optional[Path] = None,
    top_k_files: int = 15,
    top_k_symbols: int = 5,
    workspace: Optional[Path] = None,
) -> dict[str, Any]:
    """Run localization; fall back to search sub-agent when localizer overflows.

    Implements the WarpGrep v2 bypass rule: "Bypasses the localizer
    (F-R7-600) when the localizer returns >20 candidate symbols."

    Pipeline:
      1. Run hierarchical localization.
      2. If symbols > LOCALIZER_OVERFLOW_THRESHOLD, run search sub-agent.
      3. Merge search results into the localization dict as edit_sites.

    Args:
        feature_id:    Feature UUID string.
        intent:        Intent dict with capability, target_subsystem, keywords.
        survey_db:     Path to survey.db. None → empty localization result.
        top_k_files:   Stage A budget (default 15).
        top_k_symbols: Stage B budget (default 5).
        workspace:     Workspace root for search sub-agent. Defaults to cwd.

    Returns:
        Dict with keys: files, symbols, edit_sites, search_used.
    """
    loc = localize_and_persist(
        feature_id,
        intent,
        survey_db=survey_db,
        top_k_files=top_k_files,
        top_k_symbols=top_k_symbols,
    )

    symbols = loc.get("symbols", [])
    if should_use_search_subagent(symbols):
        logger.info(
            "localize_with_search_fallback: %d symbols > threshold %d; "
            "running search sub-agent for feature %s",
            len(symbols),
            LOCALIZER_OVERFLOW_THRESHOLD,
            feature_id,
        )
        ws = Path(workspace) if workspace is not None else Path.cwd()
        search_results: list[SearchResult] = spawn_search_subagent(intent, workspace=ws)
        search_edit_sites = [r.to_dict() for r in search_results]
        loc = dict(loc)
        loc["edit_sites"] = search_edit_sites
        loc["search_used"] = True
    else:
        loc = dict(loc)
        loc["search_used"] = False

    return loc


def dispatch_hard_feature(
    feature: dict[str, Any],
    *,
    workspace: Optional[Path] = None,
    patch_generator: Optional[Any] = None,
    test_files: Optional[list[str]] = None,
) -> Optional[MultiCandidateResult]:
    """Dispatch a feature using multi-candidate if it qualifies as 'hard'.

    Integration hook for the orchestrator main loop. Checks is_hard_feature()
    and calls maybe_run_multi_candidate() when the gate condition is met.

    Args:
        feature:         Feature dict with id, description, acceptance_criteria,
                         refinement_attempts, difficulty fields.
        workspace:       Repository root. Defaults to cwd.
        patch_generator: Optional callable(worktree_path, feature) -> str.
        test_files:      Optional list of test file paths for regression check.

    Returns:
        MultiCandidateResult if multi-candidate dispatch ran, None otherwise.
    """
    return maybe_run_multi_candidate(
        feature,
        workspace=workspace,
        patch_generator=patch_generator,
        test_files=test_files,
    )


__all__ = [
    "localize_feature",
    "check_disjoint_features",
    "run_localization_pipeline",
    "localize_with_search_fallback",
    "dispatch_hard_feature",
    "is_hard_feature",
    "rank_candidates_with_judge",
    "spawn_search_subagent",
]
