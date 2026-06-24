"""Voyager-style SkillLibraryManager — high-level API for the workspace skill library.

This module provides ``SkillLibraryManager``, an object-oriented facade over
``bob.skill_library.registry`` that is importable directly from the workspace
``skill_library`` package (i.e. ``from skill_library.manager import
SkillLibraryManager``).

The manager exposes the two operations required on env preflight:
- ``search_by_similarity`` — find an existing shim before spawning research.
- ``persist_skill`` — write a newly discovered workaround back to the library.

Skills persist across bob generations because the skill_library/ directory is
preserved by the disk-state reconciler (same mechanism as specs/ and reviews/).

See also:
    skill_library/shim_template.py — template for new shim modules.
    src/bob/skill_library/registry.py — low-level storage implementation.
    src/bob73/preflight.py — preflight integration hook.
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
    similarity_threshold as _default_threshold,
)

__all__ = ["SkillLibraryManager"]


class SkillLibraryManager:
    """Object-oriented façade for the Voyager-style persistent skill library.

    Each instance is bound to a workspace directory (defaulting to the current
    working directory) and delegates storage operations to
    ``bob.skill_library.registry``.

    Typical usage on env preflight::

        mgr = SkillLibraryManager()
        hit = mgr.search_by_similarity("hex dump a binary file")
        if hit:
            result = hit["apply_result"]
        else:
            # spawn research, then persist the discovered shim
            mgr.persist_skill(
                capability_description="hex dump a binary file",
                shim_module_src=discovered_src,
            )
    """

    def __init__(
        self,
        workspace: Optional[pathlib.Path] = None,
        default_threshold: Optional[float] = None,
    ) -> None:
        """Initialise the manager.

        Args:
            workspace: Project root directory. ``skill_library/`` is resolved
                under it. Defaults to the current working directory.
            default_threshold: Minimum cosine similarity for a hit. Defaults to
                ``similarity_threshold()`` (0.75).
        """
        self.workspace = workspace
        self.default_threshold = (
            default_threshold if default_threshold is not None else _default_threshold()
        )

    # ------------------------------------------------------------------
    # AC-required methods
    # ------------------------------------------------------------------

    def search_by_similarity(
        self,
        capability_query: str,
        context: Optional[dict] = None,
        threshold: Optional[float] = None,
        top_k: int = 5,
    ) -> Optional[Dict[str, Any]]:
        """Search the skill library for an existing workaround shim.

        Called on env preflight BEFORE spawning a research sub-agent. If a
        skill with similarity >= threshold is found, the shim is applied and
        a result dict is returned. The caller should skip research when the
        return value is not None.

        Args:
            capability_query: Natural-language description of the needed
                capability (e.g. "hex dump a binary file when xxd is missing").
            context: Optional dict passed to the shim's ``apply()`` function.
            threshold: Minimum cosine similarity for a hit. Defaults to
                ``self.default_threshold``.
            top_k: Maximum number of candidate hits to rank before returning
                the best one.

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

        eff_threshold = threshold if threshold is not None else self.default_threshold
        if context is None:
            context = {}

        hits: List[SkillHit] = search_skills(
            query=capability_query,
            top_k=top_k,
            threshold=eff_threshold,
            workspace=self.workspace,
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
        self,
        capability_description: str,
        shim_module_src: str,
        skill_id: Optional[str] = None,
    ) -> str:
        """Persist a newly discovered workaround into the skill library.

        Called after a successful research-path discovery to write the shim
        back so future preflight calls can skip research.

        Args:
            capability_description: Natural-language description of the
                workaround (used for embedding and similarity search).
            shim_module_src: Python source of the shim module. Must define an
                ``apply(context: dict) -> Any`` function.
            skill_id: Optional explicit skill ID. Auto-derived from
                ``capability_description`` via SHA-256 if None.

        Returns:
            The ``skill_id`` string for the stored skill.

        Raises:
            ValueError: If ``capability_description`` or ``shim_module_src``
                is empty or whitespace-only.
        """
        if not capability_description or not capability_description.strip():
            raise ValueError("capability_description must be a non-empty string")
        if not shim_module_src or not shim_module_src.strip():
            raise ValueError("shim_module_src must be a non-empty string")

        return add_skill(
            capability_description=capability_description,
            shim_module_src=shim_module_src,
            workspace=self.workspace,
            skill_id=skill_id,
        )

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def list_skills(self) -> List[Dict[str, Any]]:
        """Return a list of all skills in the library index.

        Returns:
            List of dicts, each with keys ``skill_id`` and
            ``capability_description``.  Empty list if the library is empty.
        """
        import json, os  # noqa: E401

        lib = (
            self.workspace / "skill_library"
            if self.workspace is not None
            else pathlib.Path(".") / "skill_library"
        )
        index_path = lib / "index.json"
        if not index_path.exists():
            return []
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return [
            {
                "skill_id": s["skill_id"],
                "capability_description": s["capability_description"],
            }
            for s in index.get("skills", [])
        ]
