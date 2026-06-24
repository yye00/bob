"""bob77 skill library — Voyager-style persistent skill library facade.

Exposes ``retrieve_by_similarity`` and ``persist_skill`` as the canonical
bob77-generation API for the Voyager-style persistent skill library
(Wang et al. "Voyager: An Open-Ended Embodied Agent with Large Language Models",
arXiv:2305.16291).

These functions wrap ``bob.skill_library.registry`` and delegate to the same
on-disk storage used by bob73. The skill_library/ directory persists across
bob generations via the disk-state reconciler.

On env preflight:
1. Call ``retrieve_by_similarity`` BEFORE spawning a research sub-agent.
2. If a hit is returned, apply it directly — skip research.
3. On new discovery, call ``persist_skill`` to write the shim back.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

from bob.skill_library.registry import (
    ApplyResult,
    SkillHit,
    add_skill,
    apply_skill,
    search_skills,
    similarity_threshold,
)

__all__ = [
    "retrieve_by_similarity",
    "persist_skill",
    "ApplyResult",
    "SkillHit",
]


def retrieve_by_similarity(
    capability_query: str,
    workspace: Optional[pathlib.Path] = None,
    context: Optional[dict] = None,
    threshold: Optional[float] = None,
    top_k: int = 5,
) -> Optional[Dict[str, Any]]:
    """Retrieve a skill from the persistent library by semantic similarity.

    Searches the skill library BEFORE spawning a research sub-agent. If a
    skill with similarity >= threshold is found, the shim is applied and a
    result dict is returned so the caller can skip research.

    Args:
        capability_query: Natural-language description of the needed capability
            (e.g. "hex dump a binary file when xxd is missing").
        workspace: Project root directory; skill_library/ is resolved under it.
            Defaults to the current working directory.
        context: Optional dict passed to the shim's ``apply()`` function.
        threshold: Minimum cosine similarity for a hit. Defaults to
            ``similarity_threshold()`` (0.75).
        top_k: Maximum number of candidate hits to rank before returning the
            best one.

    Returns:
        A dict with keys:
        - ``"hit"``: :class:`SkillHit` — the library match.
        - ``"apply_result"``: :class:`ApplyResult` — shim execution result.
        - ``"research_needed"``: ``False``.
        ``None`` when no hit above threshold is found (research should be
        spawned).

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

    hits: List[SkillHit] = search_skills(
        query=capability_query,
        top_k=top_k,
        threshold=threshold,
        workspace=workspace,
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


def persist_skill(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
    skill_id: Optional[str] = None,
) -> str:
    """Persist a newly discovered workaround into the skill library.

    Called after a successful research-path discovery to write the shim back
    so future preflight calls can skip research and apply the shim directly.

    Args:
        capability_description: Natural-language description of the workaround.
            Used for embedding and similarity search.
        shim_module_src: Python source of the shim module. Must define an
            ``apply(context: dict) -> Any`` function and a module-level docstring.
        workspace: Project root directory. Defaults to the current working directory.
        skill_id: Optional explicit skill ID. Auto-derived from
            ``capability_description`` via SHA-256 if ``None``.

    Returns:
        The ``skill_id`` string for the stored skill.

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
