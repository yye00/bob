"""Persistence utilities for the Voyager-style persistent skill library (F-R7-473).

Provides helper functions for reading and writing skill shim modules to the
skill_library/ directory on disk. The library directory persists across bob
generations via the disk-state reconciler (same mechanism as specs/ and reviews/).

Public API
----------
load_shim_source(skill_id, workspace=None) -> str | None
    Load the source of a stored shim module by skill_id.
list_skill_ids(workspace=None) -> list[str]
    Return all skill_id values currently stored in the library.
delete_shim(skill_id, workspace=None) -> bool
    Remove a shim module and its index entry. Returns True if deleted.
library_dir(workspace=None) -> pathlib.Path
    Return the resolved skill_library/ directory path.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import List, Optional

logger = logging.getLogger(__name__)

_LIBRARY_DIR_NAME = "skill_library"
_INDEX_FILE = "index.json"


def library_dir(workspace: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Return the skill_library/ directory path for the given workspace.

    Args:
        workspace: Project root directory; defaults to current working directory.

    Returns:
        pathlib.Path pointing to the skill_library/ directory (may not exist yet).
    """
    root = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()
    return root / _LIBRARY_DIR_NAME


def load_shim_source(
    skill_id: str,
    workspace: Optional[pathlib.Path] = None,
) -> Optional[str]:
    """Load the Python source of a stored shim module.

    Args:
        skill_id: The skill identifier (filename without .py).
        workspace: Project root directory; defaults to CWD.

    Returns:
        The source code string, or None if the shim does not exist.

    Raises:
        ValueError: If skill_id is not a non-empty string.
    """
    if not isinstance(skill_id, str) or not skill_id.strip():
        raise ValueError(f"skill_id must be a non-empty string, got {skill_id!r}")

    lib = library_dir(workspace)
    shim_path = lib / f"{skill_id}.py"
    if not shim_path.exists():
        return None
    return shim_path.read_text(encoding="utf-8")


def list_skill_ids(workspace: Optional[pathlib.Path] = None) -> List[str]:
    """Return the skill_ids of all skills currently in the library.

    Args:
        workspace: Project root directory; defaults to CWD.

    Returns:
        List of skill_id strings sorted alphabetically. Empty list when the
        library does not exist or is empty.
    """
    lib = library_dir(workspace)
    index_path = lib / _INDEX_FILE
    if not index_path.exists():
        return []
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        return sorted(s["skill_id"] for s in index.get("skills", []))
    except (json.JSONDecodeError, KeyError):
        logger.warning("skill_library index is malformed; returning empty list")
        return []


def delete_shim(
    skill_id: str,
    workspace: Optional[pathlib.Path] = None,
) -> bool:
    """Remove a shim module and its index entry from the skill library.

    Args:
        skill_id: The skill identifier to remove.
        workspace: Project root directory; defaults to CWD.

    Returns:
        True if the skill was found and removed, False if not present.

    Raises:
        ValueError: If skill_id is not a non-empty string.
    """
    if not isinstance(skill_id, str) or not skill_id.strip():
        raise ValueError(f"skill_id must be a non-empty string, got {skill_id!r}")

    lib = library_dir(workspace)
    shim_path = lib / f"{skill_id}.py"
    index_path = lib / _INDEX_FILE

    removed = False

    if shim_path.exists():
        shim_path.unlink()
        removed = True

    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            skills = index.get("skills", [])
            new_skills = [s for s in skills if s["skill_id"] != skill_id]
            if len(new_skills) < len(skills):
                index["skills"] = new_skills
                index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
                removed = True
        except (json.JSONDecodeError, KeyError):
            logger.warning("skill_library index is malformed; skipping index update")

    return removed
