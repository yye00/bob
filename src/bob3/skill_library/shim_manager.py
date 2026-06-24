"""Voyager-style persistent skill library — shim manager (F-R7-473/477).

On env preflight BEFORE spawning a research sub-agent, ``search_skill_library``
is called to find an existing workaround by semantic similarity. If a skill
with similarity >= 0.75 is found, it is applied directly, skipping research.
On new discovery, ``register_skill`` writes the workaround back so future
preflight calls hit the library instead of re-spawning research agents.

The skill_library/ directory persists across bob generations via the
disk-state reconciler (same mechanism as specs/ and reviews/).

Source: Wang et al. "Voyager: An Open-Ended Embodied Agent with Large
Language Models" (arXiv 2305.16291).
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, Optional

from bob3.skill_library.registry import (
    ApplyResult,
    SkillHit,
    add_skill,
    apply_skill,
    search_skills,
    similarity_threshold,
)

__all__ = [
    "search_skill_library",
    "register_skill",
]


def search_skill_library(
    capability_query: str,
    workspace: Optional[pathlib.Path] = None,
    context: Optional[dict] = None,
    threshold: Optional[float] = None,
    top_k: int = 5,
) -> Optional[Dict[str, Any]]:
    """Search the persistent skill library for an existing workaround shim.

    Called on env preflight BEFORE spawning a research sub-agent. If a skill
    with similarity >= threshold is found, the shim is applied and a result
    dict is returned. The caller should skip research when the return value is
    not None.

    Args:
        capability_query: Natural-language description of the needed capability
            (e.g. "hex dump a binary file when xxd is missing").
        workspace: Project root directory; skill_library/ is resolved under it.
            Defaults to current working directory.
        context: Optional dict passed to the shim's apply() function.
        threshold: Minimum cosine similarity for a hit. Defaults to
            similarity_threshold() (0.75).
        top_k: Maximum number of candidate hits to rank before returning best.

    Returns:
        A dict with keys:
        - ``"hit"``: :class:`SkillHit` — the library match.
        - ``"apply_result"``: :class:`ApplyResult` — result of executing the shim.
        - ``"research_needed"``: ``False`` — caller should NOT spawn research.
        Returns ``None`` when no hit above threshold is found (research needed).

    Raises:
        ValueError: If ``capability_query`` is not a non-empty string.
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
        top_k=top_k,
        threshold=threshold,
        workspace=workspace,
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


def register_skill(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
    skill_id: Optional[str] = None,
) -> str:
    """Register a newly discovered workaround shim into the persistent skill library.

    Called after a successful research-path discovery to persist the shim so
    future preflight calls can skip research. Uses upsert semantics: if a skill
    with the same derived ID already exists it is updated.

    The on-disk storage lives in skill_library/ at the workspace root and is
    preserved across bob generations by the disk-state reconciler.

    Args:
        capability_description: Natural-language description of what the shim
            does (e.g. "hex dump bytes using Python stdlib when xxd is missing").
            Used to build the embedding for similarity search.
        shim_module_src: Python source code of the shim module. Must define an
            ``apply(context: dict) -> Any`` function.
        workspace: Project root directory; skill_library/ is created under it.
            Defaults to current working directory.
        skill_id: Optional explicit skill ID; auto-derived from
            capability_description via SHA-256 if None.

    Returns:
        The skill_id string for the stored skill.

    Raises:
        ValueError: If ``capability_description`` or ``shim_module_src`` is
            empty or whitespace-only.
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
