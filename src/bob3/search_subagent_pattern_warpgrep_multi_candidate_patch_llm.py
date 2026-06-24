"""Search-subagent pattern (WarpGrep) + multi-candidate patch + LLM-judge vote.

Facade module for Feature 8296b3a0-88ba-4e20-8a44-6fbe5e31ccbf.

Integrates two leaderboard-validated multi-agent patterns:

(A) WarpGrep search sub-agent
    Spawns a dedicated 'locator' sub-agent whose entire job is grep → return
    3-5 (file, span) candidates. Bypasses the localizer (F-R7-600) when it
    returns >20 candidate symbols.

(B) Multi-candidate patch + LLM-judge
    For hard features (difficulty >= 'hard' or prior_attempts >= 1):
    spawns N=3 worker candidates, filters regression-breaking patches, and
    ranks survivors via an LLM-judge scoring heuristic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from bob3.brownfield.multi_candidate_patch import maybe_run_multi_candidate
from bob3.brownfield.search_subagent import spawn_search_subagent


def search_subagent_pattern_warpgrep_multi_candidate_patch_llm(
    intent: dict[str, Any],
    *,
    workspace: Optional[Path] = None,
    run_multi_candidate: bool = True,
    patch_generator: Optional[Any] = None,
    test_files: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Run WarpGrep search sub-agent and optionally multi-candidate patch dispatch.

    Boundary conditions:
      - Empty dict → returns result with empty candidates list without crashing.
      - None / non-dict intent → raises TypeError.
      - Invalid non-dict types (str, int, list) → raises ValueError or TypeError.

    Args:
        intent: Feature intent dict with optional 'capability', 'keywords',
                'target_subsystem', 'id', 'difficulty', 'refinement_attempts'
                fields. Must be a dict.
        workspace: Repository root. Defaults to cwd.
        run_multi_candidate: If False, skip multi-candidate dispatch (useful
                              when caller already decided it's not hard).
        patch_generator: Optional callable passed to maybe_run_multi_candidate.
        test_files: Optional test files for regression detection.

    Returns:
        Dict with keys:
          - 'search_candidates': list of candidate dicts (path, start_line,
            end_line, confidence, rationale_snippet).
          - 'multi_candidate': MultiCandidateResult or None.

    Raises:
        TypeError: If intent is not a dict.
        ValueError: If intent is a non-dict type that cannot be used.
    """
    if not isinstance(intent, dict):
        if intent is None:
            raise TypeError("intent must be a dict, got None")
        raise TypeError(f"intent must be a dict, got {type(intent).__name__!r}")

    # --- (A) WarpGrep search sub-agent ---
    search_results = spawn_search_subagent(intent, workspace=workspace)
    candidates = [r.to_dict() for r in search_results]

    # --- (B) Multi-candidate patch + LLM-judge ---
    multi_result = None
    if run_multi_candidate:
        multi_result = maybe_run_multi_candidate(
            intent,
            workspace=workspace,
            patch_generator=patch_generator,
            test_files=test_files,
        )

    return {
        "search_candidates": candidates,
        "multi_candidate": multi_result,
    }
