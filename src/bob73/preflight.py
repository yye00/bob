"""Environment-capability preflight for bob73 with Voyager-style skill library.

Extends bob72.preflight by searching the persistent skill library BEFORE
spawning a research sub-agent. If a shim with similarity >= 0.75 is found
it is applied directly; only on a miss does research get spawned.

This integrates F-R7-473 (research-driven workaround discovery) with the
Voyager pattern (Wang et al. arXiv:2305.16291) from F-R7-477.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

from bob72.preflight import (
    MissingDependencyError,
    discover_workaround,
    probe_dependencies,
    run_preflight as _run_preflight_base,
)
from bob3.skill_library.registry import (
    ApplyResult,
    SkillHit,
    apply_skill,
    search_skills,
    similarity_threshold,
)

__all__ = [
    "MissingDependencyError",
    "probe_dependencies",
    "discover_workaround",
    "search_skill_library",
    "run_preflight",
]


def search_skill_library(
    capability_query: str,
    workspace: Optional[pathlib.Path] = None,
    context: Optional[dict] = None,
    threshold: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Search the persistent skill library for an existing workaround shim.

    Called during env preflight BEFORE spawning a research sub-agent.
    If a skill with similarity >= threshold is found, the shim is applied
    and the result is returned so the caller can skip research.

    Args:
        capability_query: Natural-language description of the needed capability
            (e.g. "hex dump a binary file when xxd is missing").
        workspace: Project root directory; defaults to current working directory.
        context: Optional dict passed to the shim's apply() function.
        threshold: Minimum cosine similarity for a hit; defaults to
            similarity_threshold() (0.75).

    Returns:
        A dict with keys:
        - "hit": SkillHit — the library match.
        - "apply_result": ApplyResult — result of executing the shim.
        - "research_needed": False — caller should NOT spawn research.
        Returns None when no hit above threshold is found (caller should
        spawn research).

    Raises:
        ValueError: If capability_query is not a non-empty string.
    """
    if not isinstance(capability_query, str) or not capability_query.strip():
        raise ValueError(
            f"capability_query must be a non-empty string, got {capability_query!r}"
        )

    if threshold is None:
        threshold = similarity_threshold()

    if context is None:
        context = {}

    hits = search_skills(
        query=capability_query,
        workspace=workspace,
        threshold=threshold,
    )

    if not hits:
        return None

    best_hit = hits[0]
    apply_result = apply_skill(best_hit, context=context)

    return {
        "hit": best_hit,
        "apply_result": apply_result,
        "research_needed": False,
    }


def run_preflight(
    ac_list: List[str],
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full preflight pipeline with skill-library integration.

    Delegates to bob72.preflight.run_preflight for core dependency probing
    and workaround discovery. The skill library search hook is exposed via
    search_skill_library for callers that run preflight step-by-step.

    Args:
        ac_list: List of acceptance criteria strings. May be empty.
        workspace: Optional project root path.

    Returns:
        A summary dict with keys total_deps, missing, applied_workarounds, halted.

    Raises:
        ValueError: If ac_list is not a list.
        MissingDependencyError: If a high-risk dep cannot be resolved.
    """
    return _run_preflight_base(ac_list, workspace=workspace)
