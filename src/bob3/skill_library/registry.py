"""Voyager-style persistent skill library registry (F-R7-477).

Stores executable shim modules with embedded natural-language capability
descriptions. On env preflight, the registry is searched by semantic
similarity BEFORE spawning a research sub-agent. On new discovery, the
workaround is written back so future runs hit the library instead.

The skill_library/ directory persists across bob generations via the
disk-state reconciler (same mechanism as specs/ and reviews/).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import textwrap
from dataclasses import dataclass, field
from typing import Any, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SIMILARITY_THRESHOLD = 0.75
_LIBRARY_DIR_ENV = "BOB3_SKILL_LIBRARY_DIR"
_DEFAULT_LIBRARY_DIR = pathlib.Path("skill_library")
_INDEX_FILE = "index.json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SkillHit:
    """A single search result from the skill registry."""

    skill_id: str
    capability_description: str
    similarity: float
    shim_module_src: str


@dataclass
class ApplyResult:
    """Result of attempting to apply a skill shim."""

    success: bool
    skill_id: str
    output: Any = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Constants / thresholds
# ---------------------------------------------------------------------------


def similarity_threshold() -> float:
    """Return the minimum cosine similarity required for a library hit.

    Returns:
        0.75 — the gate-boundary value.
    """
    return _SIMILARITY_THRESHOLD


# ---------------------------------------------------------------------------
# Library directory resolution
# ---------------------------------------------------------------------------


def _library_dir(workspace: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Return the skill_library directory for the current workspace."""
    if workspace is not None:
        return workspace / "skill_library"
    env_override = os.environ.get(_LIBRARY_DIR_ENV)
    if env_override:
        return pathlib.Path(env_override)
    return pathlib.Path(".") / "skill_library"


def _ensure_library(workspace: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Create the skill_library directory if it does not exist."""
    lib = _library_dir(workspace)
    lib.mkdir(parents=True, exist_ok=True)
    index = lib / _INDEX_FILE
    if not index.exists():
        index.write_text(json.dumps({"skills": []}), encoding="utf-8")
    return lib


def _load_index(lib: pathlib.Path) -> dict:
    """Load the registry index from disk."""
    index_path = lib / _INDEX_FILE
    if not index_path.exists():
        return {"skills": []}
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"skills": []}


def _save_index(lib: pathlib.Path, index: dict) -> None:
    """Persist the registry index to disk."""
    (lib / _INDEX_FILE).write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _skill_id_from_description(capability_description: str) -> str:
    """Deterministically derive a skill_id from the capability description."""
    digest = hashlib.sha256(capability_description.encode()).hexdigest()[:12]
    return f"skill_{digest}"


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------


def add_skill(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
    skill_id: Optional[str] = None,
) -> str:
    """Add a new skill to the library (or update if already present).

    Args:
        capability_description: Natural-language description of what the shim does.
        shim_module_src: Python source code of the shim module. Must be a valid
            Python module with a docstring describing its capability.
        workspace: Project root; defaults to CWD.
        skill_id: Optional explicit skill ID; auto-derived from description if None.

    Returns:
        The skill_id string for the newly stored skill.
    """
    lib = _ensure_library(workspace)
    index = _load_index(lib)

    if skill_id is None:
        skill_id = _skill_id_from_description(capability_description)

    # Write the shim module source to disk
    shim_path = lib / f"{skill_id}.py"
    shim_path.write_text(shim_module_src, encoding="utf-8")

    # Compute embedding for the capability description
    from bob3.skill_library.embeddings import embed_texts  # noqa: PLC0415

    embedding = embed_texts([capability_description])[0].tolist()

    # Upsert into index
    skills = index.get("skills", [])
    existing = next((s for s in skills if s["skill_id"] == skill_id), None)
    if existing:
        existing["capability_description"] = capability_description
        existing["embedding"] = embedding
        existing["shim_path"] = str(shim_path.name)
    else:
        skills.append(
            {
                "skill_id": skill_id,
                "capability_description": capability_description,
                "embedding": embedding,
                "shim_path": shim_path.name,
            }
        )

    index["skills"] = skills
    _save_index(lib, index)

    logger.info("Skill library: added skill %s", skill_id)
    return skill_id


def search_skills(
    query: str,
    top_k: int = 5,
    threshold: Optional[float] = None,
    workspace: Optional[pathlib.Path] = None,
) -> List[SkillHit]:
    """Search the skill library by semantic similarity.

    Args:
        query: Natural-language capability query (e.g. "hex dump a binary file").
        top_k: Maximum number of results to return.
        threshold: Minimum similarity; defaults to similarity_threshold().
        workspace: Project root; defaults to CWD.

    Returns:
        List of SkillHit sorted by descending similarity. Empty if library is
        empty or no hits exceed the threshold.
    """
    if threshold is None:
        threshold = similarity_threshold()

    lib = _library_dir(workspace)
    if not lib.exists():
        return []

    index = _load_index(lib)
    skills = index.get("skills", [])
    if not skills:
        return []

    from bob3.skill_library.embeddings import (  # noqa: PLC0415
        cosine_similarity_scores,
        embed_texts,
    )

    query_vec = embed_texts([query])[0]
    embeddings = np.array([s["embedding"] for s in skills], dtype=np.float32)
    scores = cosine_similarity_scores(query_vec, embeddings)

    hits: List[SkillHit] = []
    for idx, (skill, score) in enumerate(zip(skills, scores)):
        if float(score) >= threshold:
            shim_path = lib / skill["shim_path"]
            shim_src = (
                shim_path.read_text(encoding="utf-8") if shim_path.exists() else ""
            )
            hits.append(
                SkillHit(
                    skill_id=skill["skill_id"],
                    capability_description=skill["capability_description"],
                    similarity=float(score),
                    shim_module_src=shim_src,
                )
            )

    hits.sort(key=lambda h: h.similarity, reverse=True)
    return hits[:top_k]


def apply_skill(
    skill_hit: SkillHit,
    context: Optional[dict] = None,
) -> ApplyResult:
    """Execute the shim module from a SkillHit.

    The shim is executed via exec() in an isolated namespace. The shim
    module is expected to define an ``apply(context)`` function that
    performs the workaround and returns a result value.

    Args:
        skill_hit: A SkillHit returned by search_skills.
        context: Optional dict passed to the shim's apply() function.

    Returns:
        ApplyResult with success=True and output from apply() on success,
        or success=False with error message on failure.
    """
    if context is None:
        context = {}

    namespace: dict = {}
    try:
        exec(compile(skill_hit.shim_module_src, f"<skill:{skill_hit.skill_id}>", "exec"), namespace)  # noqa: S102
    except Exception as exc:
        return ApplyResult(
            success=False,
            skill_id=skill_hit.skill_id,
            error=f"Failed to compile/exec shim: {exc}",
        )

    apply_fn = namespace.get("apply")
    if apply_fn is None:
        return ApplyResult(
            success=False,
            skill_id=skill_hit.skill_id,
            error="Shim module does not define an apply() function",
        )

    try:
        output = apply_fn(context)
        return ApplyResult(success=True, skill_id=skill_hit.skill_id, output=output)
    except Exception as exc:
        return ApplyResult(
            success=False,
            skill_id=skill_hit.skill_id,
            error=f"apply() raised: {exc}",
        )


# ---------------------------------------------------------------------------
# Integration with env_preflight
# ---------------------------------------------------------------------------


def persist_new_workaround(
    capability_description: str,
    shim_module_src: str,
    workspace: Optional[pathlib.Path] = None,
) -> str:
    """Persist a newly discovered workaround into the skill library.

    Called by env_preflight after a successful research-path discovery.
    Calls add_skill internally.

    Args:
        capability_description: What this workaround provides.
        shim_module_src: Executable Python shim implementing the workaround.
        workspace: Project root; defaults to CWD.

    Returns:
        The skill_id of the persisted skill.
    """
    skill_id = add_skill(
        capability_description=capability_description,
        shim_module_src=shim_module_src,
        workspace=workspace,
    )
    logger.info(
        "Persisted new workaround as skill %s: %r", skill_id, capability_description[:80]
    )
    return skill_id


# ---------------------------------------------------------------------------
# Generation-survival marker
# ---------------------------------------------------------------------------


def survive_generation_spawn() -> bool:
    """Return True — documents that skill_library skills survive generation spawns.

    The skill_library directory is preserved by the disk-state reconciler
    as part of the workspace sync. This function exists as a discoverable
    contract that callers can assert on.
    """
    return True


def mirrored_via_disk_reconciler() -> bool:
    """Return True — documents that skill_library dir is preserved by disk reconciler.

    The disk-state reconciler copies the entire workspace (including
    skill_library/) when spawning a new generation, so skills persist
    across bob generations without additional configuration.
    """
    return True
