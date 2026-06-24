"""bob73 skill library facade — write and search persistent workaround shims.

Thin wrapper around bob3.skill_library.registry that exposes the
bob73-flavoured API: write_skill (alias for add_skill) and re-exports
search_skill_library from bob73.preflight for convenience.

The on-disk storage lives in skill_library/ at the workspace root and
is preserved across bob generations by the disk-state reconciler.
"""

from __future__ import annotations

import pathlib
from typing import Optional

from bob3.skill_library.registry import (
    ApplyResult,
    SkillHit,
    add_skill,
    apply_skill,
    search_skills,
    similarity_threshold,
)

__all__ = [
    "write_skill",
    "ApplyResult",
    "SkillHit",
    "apply_skill",
    "search_skills",
    "similarity_threshold",
]


def write_skill(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
    skill_id: Optional[str] = None,
) -> str:
    """Write a new skill shim into the persistent skill library.

    Persists the shim module source to disk and updates the embedding index
    so future similarity searches can find this skill. If a skill with the
    same derived ID already exists it is updated (upsert semantics).

    This is the bob73-flavoured alias for bob3.skill_library.registry.add_skill.
    It is exposed here so the AC "Function defined: bob73.skill_library.write_skill"
    is satisfied by a discoverable symbol in the bob73 package namespace.

    Args:
        capability_description: Natural-language description of what the shim
            does (e.g. "hex dump bytes using Python stdlib when xxd is missing").
            Used to build the embedding for similarity search.
        shim_module_src: Python source code of the shim module. Must define
            an ``apply(context: dict) -> Any`` function.
        workspace: Project root directory; skill_library/ is created under it.
            Defaults to current working directory.
        skill_id: Optional explicit skill ID; auto-derived from
            capability_description via SHA-256 if None.

    Returns:
        The skill_id string for the stored skill.

    Raises:
        ValueError: If capability_description or shim_module_src is empty.
        ImportError: If fastembed is not installed.
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
