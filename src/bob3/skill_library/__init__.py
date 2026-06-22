"""Voyager-style persistent skill library for env workarounds and shims (F-R7-477).

On env preflight, BEFORE spawning a research sub-agent, the library is
searched by semantic similarity. If a skill with similarity >= 0.75 is
found, it is applied directly. New discoveries are written back so future
runs hit the library instead of spawning research agents.

The skill_library/ directory persists across bob generations via the
disk-state reconciler.

Public API (AC-required names)
-------------------------------
load_skill_by_similarity(query, workspace=None, threshold=None, context=None)
    AC alias for search_by_similarity — search and apply best hit or return None.
persist_skill(capability_description, shim_module_src, workspace=None)
    AC alias for write_discovery — persist a newly discovered workaround.
search_library(query, workspace=None, threshold=None, context=None)
    AC alias for search_by_similarity — search and apply best hit or return None.
write_skill(capability_description, shim_module_src, workspace=None)
    AC alias for write_discovery — persist a newly discovered workaround.
search_by_similarity(query, workspace=None, threshold=None, context=None)
    Search the library and return the best SkillHit + ApplyResult, or None.
apply_shim(skill_hit, context=None)
    Execute a SkillHit shim and return an ApplyResult.
write_discovery(capability_description, shim_module_src, workspace=None)
    Persist a newly discovered workaround into the library.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

from bob3.skill_library.registry import (
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
from bob3.skill_library.embeddings import default_backend, load_from_env
from bob3.skill_library.shim_manager import register_skill


# ---------------------------------------------------------------------------
# AC-required top-level functions
# ---------------------------------------------------------------------------


def search_by_similarity(
    query: str,
    workspace: Optional[pathlib.Path] = None,
    threshold: Optional[float] = None,
    context: Optional[dict] = None,
    top_k: int = 5,
) -> Optional[Dict[str, Any]]:
    """Search the persistent skill library for an existing workaround shim.

    Called on env preflight BEFORE spawning a research sub-agent. If a
    skill with similarity >= threshold is found, the shim is applied and a
    result dict is returned. Returns None when no hit is found.

    Args:
        query: Natural-language description of the needed capability.
        workspace: Project root directory; defaults to CWD.
        threshold: Minimum cosine similarity for a hit; defaults to
            similarity_threshold() (0.75).
        context: Optional dict passed to the shim's apply() function.
        top_k: Maximum number of candidate hits to consider.

    Returns:
        Dict with keys "hit" (SkillHit), "apply_result" (ApplyResult), and
        "research_needed" (False); or None when no library hit was found.

    Raises:
        ValueError: If query is not a non-empty string.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError(f"query must be a non-empty string, got {query!r}")

    if threshold is None:
        threshold = similarity_threshold()
    if context is None:
        context = {}

    hits: List[SkillHit] = search_skills(
        query=query, top_k=top_k, threshold=threshold, workspace=workspace
    )
    if not hits:
        return None

    best = hits[0]
    apply_result: ApplyResult = apply_skill(best, context=context)
    return {
        "hit": best,
        "apply_result": apply_result,
        "research_needed": False,
    }


def apply_shim(
    skill_hit: SkillHit,
    context: Optional[dict] = None,
) -> ApplyResult:
    """Execute a skill shim from a SkillHit.

    Thin public alias for bob3.skill_library.registry.apply_skill that
    satisfies the AC "Function defined: bob3.skill_library.apply_shim".

    Args:
        skill_hit: A SkillHit returned by search_by_similarity / search_skills.
        context: Optional dict passed to the shim's apply() function.

    Returns:
        ApplyResult with success=True and shim output on success, or
        success=False with error message on failure.
    """
    return apply_skill(skill_hit, context=context)


def search_library(
    query: str,
    workspace: Optional[pathlib.Path] = None,
    threshold: Optional[float] = None,
    context: Optional[dict] = None,
    top_k: int = 5,
) -> Optional[Dict[str, Any]]:
    """AC-required alias for search_by_similarity.

    Search the persistent skill library for an existing workaround shim.
    Called on env preflight BEFORE spawning a research sub-agent.

    Args:
        query: Natural-language description of the needed capability.
        workspace: Project root directory; defaults to CWD.
        threshold: Minimum cosine similarity for a hit; defaults to 0.75.
        context: Optional dict passed to the shim's apply() function.
        top_k: Maximum number of candidate hits to consider.

    Returns:
        Dict with keys "hit", "apply_result", "research_needed"; or None.

    Raises:
        ValueError: If query is not a non-empty string.
    """
    return search_by_similarity(
        query=query,
        workspace=workspace,
        threshold=threshold,
        context=context,
        top_k=top_k,
    )


def write_skill(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
    skill_id: Optional[str] = None,
) -> str:
    """AC-required alias for write_discovery.

    Persist a newly discovered workaround into the persistent skill library.

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
    return write_discovery(
        capability_description=capability_description,
        shim_module_src=shim_module_src,
        workspace=workspace,
        skill_id=skill_id,
    )


def load_skill_by_similarity(
    query: str,
    workspace: Optional[pathlib.Path] = None,
    threshold: Optional[float] = None,
    context: Optional[dict] = None,
    top_k: int = 5,
) -> Optional[Dict[str, Any]]:
    """AC alias for search_by_similarity.

    Search the persistent skill library for an existing workaround shim.
    Called on env preflight BEFORE spawning a research sub-agent. If a
    skill with similarity >= threshold is found, the shim is applied and a
    result dict is returned. Returns None when no hit is found.

    Args:
        query: Natural-language description of the needed capability.
        workspace: Project root directory; defaults to CWD.
        threshold: Minimum cosine similarity for a hit; defaults to 0.75.
        context: Optional dict passed to the shim's apply() function.
        top_k: Maximum number of candidate hits to consider.

    Returns:
        Dict with keys "hit", "apply_result", "research_needed"; or None.

    Raises:
        ValueError: If query is not a non-empty string.
    """
    return search_by_similarity(
        query=query,
        workspace=workspace,
        threshold=threshold,
        context=context,
        top_k=top_k,
    )


def persist_skill(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
    skill_id: Optional[str] = None,
) -> str:
    """AC alias for write_discovery.

    Persist a newly discovered workaround into the persistent skill library.

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
    return write_discovery(
        capability_description=capability_description,
        shim_module_src=shim_module_src,
        workspace=workspace,
        skill_id=skill_id,
    )


def write_discovery(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
    skill_id: Optional[str] = None,
) -> str:
    """Persist a newly discovered workaround into the persistent skill library.

    Called after a successful research-path discovery to write the shim
    back so future preflight calls can skip research.

    This is a public alias for add_skill that satisfies the AC
    "Function defined: bob3.skill_library.write_discovery".

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
    if not capability_description or not capability_description.strip():
        raise ValueError("capability_description must be a non-empty string")
    if not shim_module_src or not shim_module_src.strip():
        raise ValueError("shim_module_src must be a non-empty string")

    return add_skill(
        capability_description=capability_description,
        shim_module_src=shim_module_src,
        workspace=workspace,
        skill_id=skill_id,
    )


def search_skill_by_similarity(
    query: str,
    workspace: Optional[pathlib.Path] = None,
    threshold: Optional[float] = None,
    context: Optional[dict] = None,
    top_k: int = 5,
) -> Optional[Dict[str, Any]]:
    """Alias for search_by_similarity — used by environment_capability.py."""
    return search_by_similarity(
        query=query, workspace=workspace, threshold=threshold, context=context, top_k=top_k
    )


def write_skill_to_library(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
    skill_id: Optional[str] = None,
) -> str:
    """Alias for write_discovery — used by environment_capability.py."""
    return write_discovery(
        capability_description=capability_description,
        shim_module_src=shim_module_src,
        workspace=workspace,
        skill_id=skill_id,
    )


def search_similar_workarounds(
    query: str,
    workspace=None,
    threshold=None,
    top_k: int = 5,
) -> list:
    """Search the persistent skill library by semantic similarity.

    AC-required function: bob3.skill_library.search_similar_workarounds.
    Called on env preflight BEFORE spawning a research sub-agent. Returns a
    list of matching SkillHit objects sorted by descending similarity.

    Args:
        query: Natural-language description of the needed capability.
        workspace: Project root directory; defaults to CWD.
        threshold: Minimum cosine similarity; defaults to similarity_threshold().
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
    workspace=None,
    skill_id=None,
) -> str:
    """Persist a newly discovered workaround shim into the persistent skill library.

    AC-required function: bob3.skill_library.register_workaround.
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


__all__ = [
    # AC-required names (this feature — bb74fbcc)
    "search_similar_workarounds",
    "register_workaround",
    # AC-required names (F-R7-473)
    "load_skill_by_similarity",
    "persist_skill",
    # AC-required names (prior features)
    "search_library",
    "write_skill",
    # Prior AC-required names
    "search_by_similarity",
    "search_skill_by_similarity",
    "write_skill_to_library",
    "apply_shim",
    "write_discovery",
    # Registry re-exports
    "SkillHit",
    "ApplyResult",
    "add_skill",
    "search_skills",
    "apply_skill",
    "similarity_threshold",
    "persist_new_workaround",
    "survive_generation_spawn",
    "mirrored_via_disk_reconciler",
    # Embedding utilities
    "default_backend",
    "load_from_env",
]
