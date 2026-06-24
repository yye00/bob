"""Voyager-style persistent skill library for env workarounds and shims.

Implements the Voyager pattern (Wang et al. arXiv:2305.16291) for env preflight:
BEFORE spawning a research sub-agent, search the persistent skill library by
semantic similarity. If a skill with similarity >= 0.75 is found, apply it
directly and skip the research spawn. On new discovery, write back the
workaround so future runs hit the library instead of re-spawning research agents.

The skill_library/ directory persists across bob generations via the disk-state
reconciler (same mechanism as specs/ and reviews/).

AC-required functions
---------------------
search_library(query, workspace=None, threshold=None, context=None) -> dict|None
    Search the persistent skill library by semantic similarity. Returns a hit
    dict with "hit", "apply_result", and "research_needed" keys, or None when
    no skill above the threshold is found.

register_skill(capability_description, shim_module_src, workspace=None) -> str
    Persist a newly discovered workaround shim into the library. Returns the
    skill_id string for the stored skill.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, Optional

from bob.skill_library.shim_manager import (
    register_skill,
    search_skill_library,
)
from bob.skill_library.registry import (
    ApplyResult,
    SkillHit,
    add_skill,
    apply_skill,
    mirrored_via_disk_reconciler,
    persist_new_workaround,
    search_skills,
    similarity_threshold,
    survive_generation_spawn,
)


def search_skill_by_similarity(
    query: str,
    workspace: Optional[pathlib.Path] = None,
    threshold: Optional[float] = None,
    top_k: int = 5,
) -> list:
    """Search the persistent skill library by semantic similarity.

    AC-required name alias for search_skills / search_skill_library.
    Called on env preflight BEFORE spawning a research sub-agent.

    Args:
        query: Natural-language description of the needed capability.
        workspace: Project root directory; defaults to CWD.
        threshold: Minimum cosine similarity for a hit; defaults to 0.75.
        top_k: Maximum number of candidate hits to return.

    Returns:
        List of SkillHit sorted by descending similarity. Empty list if no hits.

    Raises:
        ValueError: If query is not a non-empty string.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    return search_skills(query=query, top_k=top_k, threshold=threshold, workspace=workspace)


def write_skill_to_library(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
    skill_id: Optional[str] = None,
) -> str:
    """Persist a newly discovered workaround shim into the library.

    AC-required name alias for write_skill / add_skill.
    Called after a successful research-path discovery to write back the
    workaround so future runs hit the library instead of re-spawning research.

    Args:
        capability_description: Natural-language description of what the shim does.
        shim_module_src: Python source code of the shim module.
        workspace: Project root; defaults to CWD.
        skill_id: Optional explicit skill ID; auto-derived if None.

    Returns:
        The skill_id string for the stored skill.

    Raises:
        ValueError: If capability_description or shim_module_src is empty.
    """
    if not isinstance(capability_description, str) or not capability_description.strip():
        raise ValueError("capability_description must be a non-empty string")
    if not isinstance(shim_module_src, str) or not shim_module_src.strip():
        raise ValueError("shim_module_src must be a non-empty string")
    return add_skill(
        capability_description=capability_description,
        shim_module_src=shim_module_src,
        workspace=workspace,
        skill_id=skill_id,
    )


def search_similar_workarounds(
    query: str,
    workspace: Optional[pathlib.Path] = None,
    threshold: Optional[float] = None,
    top_k: int = 5,
) -> list:
    """Search the persistent skill library by semantic similarity.

    AC-required function: bob.skill_library.search_similar_workarounds.
    Called on env preflight BEFORE spawning a research sub-agent. If a skill
    with similarity >= threshold is found, it can be applied directly.

    Args:
        query: Natural-language description of the needed capability.
        workspace: Project root directory; defaults to CWD.
        threshold: Minimum cosine similarity for a hit; defaults to 0.75.
        top_k: Maximum number of candidate hits to return.

    Returns:
        List of SkillHit sorted by descending similarity. Empty list if no hits.

    Raises:
        ValueError: If query is not a non-empty string.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError(f"query must be a non-empty string, got {query!r}")
    return search_skills(query=query, top_k=top_k, threshold=threshold, workspace=workspace)


def register_workaround(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
    skill_id: Optional[str] = None,
) -> str:
    """Persist a newly discovered workaround shim into the persistent skill library.

    AC-required function: bob.skill_library.register_workaround.
    Called after a successful research-path discovery to write back the
    workaround so future preflight calls hit the library instead of
    re-spawning research agents.

    Args:
        capability_description: Natural-language description of the workaround.
        shim_module_src: Python source of the shim module (must define apply()).
        workspace: Project root directory; defaults to CWD.
        skill_id: Optional explicit skill ID; auto-derived if None.

    Returns:
        The skill_id string for the stored skill.

    Raises:
        ValueError: If capability_description or shim_module_src is empty.
    """
    if not isinstance(capability_description, str) or not capability_description.strip():
        raise ValueError("capability_description must be a non-empty string")
    if not isinstance(shim_module_src, str) or not shim_module_src.strip():
        raise ValueError("shim_module_src must be a non-empty string")
    return add_skill(
        capability_description=capability_description,
        shim_module_src=shim_module_src,
        workspace=workspace,
        skill_id=skill_id,
    )


def search_library(
    query: str,
    workspace: Optional[pathlib.Path] = None,
    threshold: Optional[float] = None,
    context: Optional[dict] = None,
    top_k: int = 5,
) -> Optional[Dict[str, Any]]:
    """Search the persistent skill library for an existing workaround shim.

    Called on env preflight BEFORE spawning a research sub-agent. If a skill
    with similarity >= threshold is found, the shim is applied and a result
    dict is returned. Returns None when no library hit is found.

    Args:
        query: Natural-language description of the needed capability.
        workspace: Project root directory; defaults to CWD.
        threshold: Minimum cosine similarity for a hit; defaults to 0.75.
        context: Optional dict passed to the shim's apply() function.
        top_k: Maximum number of candidate hits to rank.

    Returns:
        Dict with keys "hit", "apply_result", "research_needed"; or None.

    Raises:
        ValueError: If query is not a non-empty string.
    """
    return search_skill_library(
        capability_query=query,
        workspace=workspace,
        threshold=threshold,
        context=context,
        top_k=top_k,
    )


__all__ = [
    # AC-required names (this feature — bb74fbcc)
    "search_similar_workarounds",
    "register_workaround",
    # AC-required names (prior features)
    "search_library",
    "search_skill_by_similarity",
    "apply_skill",
    "write_skill_to_library",
    "register_skill",
    "search_skill_library",
    "ApplyResult",
    "SkillHit",
    "add_skill",
    "search_skills",
    "similarity_threshold",
    "persist_new_workaround",
    "survive_generation_spawn",
    "mirrored_via_disk_reconciler",
]
