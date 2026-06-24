"""Voyager-style persistent skill library for env workarounds and shims.

Implements the Voyager pattern (Wang et al. arXiv:2305.16291) for env
preflight: BEFORE spawning a research sub-agent, the persistent skill
library is searched by semantic similarity. If a skill with similarity
>= 0.75 is found, it is applied directly, skipping the research spawn.
On new discovery, the workaround is written back to the library so future
runs hit the library instead of re-spawning research agents.

The skill_library/ directory persists across bob generations via the
disk-state reconciler (same mechanism as specs/ and reviews/).

Public API
----------
voyager_style_persistent_skill_library_env_workarounds_shims(
    capability_query, workspace=None, context=None, new_skill_src=None,
    new_skill_description=None
) -> dict
"""

from __future__ import annotations

import pathlib
from typing import Any, Optional

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


def voyager_style_persistent_skill_library_env_workarounds_shims(
    capability_query: str,
    workspace: Optional[pathlib.Path] = None,
    context: Optional[dict] = None,
    new_skill_src: Optional[str] = None,
    new_skill_description: Optional[str] = None,
) -> dict[str, Any]:
    """Voyager-style preflight: search library, apply hit, or persist new skill.

    On env preflight this function is called BEFORE spawning a research
    sub-agent:
    1. Search the persistent skill library by similarity against the query.
    2. If a hit >= similarity_threshold() is found, apply the shim and
       return the result — no research spawn needed.
    3. If no hit is found AND new_skill_src is provided, persist the newly
       discovered workaround into the library for future runs.

    The library directory (skill_library/) survives across bob generations
    via the disk-state reconciler.

    Args:
        capability_query: Natural-language description of the needed capability
            (e.g. "hex dump a binary file when xxd is missing").
        workspace: Project root directory; defaults to current working directory.
        context: Optional dict passed to the shim's apply() function when a
            library hit is applied.
        new_skill_src: Python source of a newly discovered shim to persist
            into the library. Only used when there is no library hit.
        new_skill_description: Human-readable description of the new skill.
            Required when new_skill_src is provided.

    Returns:
        A dict with keys:
        - "hit": SkillHit or None — the library hit (if any).
        - "applied": bool — True if a shim was executed.
        - "apply_result": ApplyResult or None — output from applying the shim.
        - "persisted_skill_id": str or None — ID of the newly persisted skill.
        - "research_needed": bool — True when no library hit was found and no
          new_skill_src was given (caller should spawn a research sub-agent).
        - "library_persists_across_generations": bool — always True; documents
          that the disk-state reconciler preserves the library.
    """
    if context is None:
        context = {}

    # Step 1: Search the library
    hits = search_skills(
        query=capability_query,
        workspace=workspace,
        threshold=similarity_threshold(),
    )

    best_hit: Optional[SkillHit] = hits[0] if hits else None

    # Step 2: Apply if we have a hit
    apply_result: Optional[ApplyResult] = None
    if best_hit is not None:
        apply_result = apply_skill(best_hit, context=context)
        return {
            "hit": best_hit,
            "applied": True,
            "apply_result": apply_result,
            "persisted_skill_id": None,
            "research_needed": False,
            "library_persists_across_generations": survive_generation_spawn(),
        }

    # Step 3: No hit — persist new discovery if provided
    persisted_skill_id: Optional[str] = None
    if new_skill_src is not None and new_skill_description is not None:
        persisted_skill_id = persist_new_workaround(
            capability_description=new_skill_description,
            shim_module_src=new_skill_src,
            workspace=workspace,
        )

    return {
        "hit": None,
        "applied": False,
        "apply_result": None,
        "persisted_skill_id": persisted_skill_id,
        "research_needed": persisted_skill_id is None,
        "library_persists_across_generations": mirrored_via_disk_reconciler(),
    }


__all__ = ["voyager_style_persistent_skill_library_env_workarounds_shims"]
