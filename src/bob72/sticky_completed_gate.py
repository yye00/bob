"""Sticky-completed gate for bob72 — re-evaluation cannot un-complete persisted work.

If a feature was status='completed' in the parent generation's DB AND its
acceptance criteria still verify on disk, no evaluator FAIL or
regression-cascade vote may flip its status below 'ready'. Reset the stamp
only when a refinement attempt actually rewrites one of the AC-named source
files.

Public API: :func:`should_persist_completed_status`
"""

from __future__ import annotations

import json
import logging
import pathlib
import re

logger = logging.getLogger(__name__)

# Statuses that count as "demoting below ready".
_DEMOTING_STATUSES = frozenset({"failed", "needs_human", "pending"})


def should_persist_completed_status(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True if a previously-completed feature should remain at least 'ready'.

    The gate fires (returns True, meaning "persist completed — block demotion")
    when ALL of the following hold:

    1. *parent_completed* is True — the feature was status='completed' in the
       parent generation's DB.
    2. *target_status* is a status below 'ready' (i.e. one of
       ``{'failed', 'needs_human', 'pending'}``).
    3. Every file-existence AC in *acceptance_criteria* still passes on disk.
       (Non-file ACs are skipped; only verifiable disk checks are enforced.)

    If any condition is False the gate does not fire and the caller may
    proceed with the demotion.

    Args:
        parent_completed: Flag indicating the feature was completed by the
            parent generation.
        target_status: The status the caller wishes to assign.
        acceptance_criteria: Raw JSON string or Python list of AC strings.
            May be None or empty — treated as an empty list.
        workspace: Root directory for disk-based AC verification.  Defaults
            to ``pathlib.Path.cwd()``.

    Returns:
        True  — the gate fires; demotion BLOCKED.
        False — the gate does not fire; demotion may proceed.

    Raises:
        ValueError: If *parent_completed* is not a bool, *target_status* is
            not a non-empty string, or *workspace* exists but is not a
            directory.
    """
    if not isinstance(parent_completed, bool):
        raise ValueError(
            f"parent_completed must be a bool, got {type(parent_completed).__name__!r}"
        )
    if not isinstance(target_status, str) or not target_status.strip():
        raise ValueError(
            f"target_status must be a non-empty string, got {target_status!r}"
        )

    ws = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()
    if not ws.exists():
        raise ValueError(f"workspace does not exist: {ws}")
    if not ws.is_dir():
        raise ValueError(f"workspace is not a directory: {ws}")

    # Condition 1: stamp must be set.
    if not parent_completed:
        return False

    # Condition 2: target must be a demoting status.
    if target_status not in _DEMOTING_STATUSES:
        return False

    # Condition 3: AC file-existence artifacts must still verify on disk.
    ac_list = _parse_acceptance_criteria(acceptance_criteria)
    file_paths = _extract_file_paths(ac_list)

    if not file_paths:
        # No file-existence ACs — nothing to protect; do not block.
        logger.debug(
            "sticky gate: no verifiable file-existence ACs; not blocking demotion to %r",
            target_status,
        )
        return False

    for rel_path in file_paths:
        abs_path = ws / rel_path
        if not abs_path.exists():
            logger.info(
                "sticky gate: AC file %s missing; allowing demotion to %r",
                rel_path,
                target_status,
            )
            return False

    logger.warning(
        "sticky gate: blocking demotion to %r — parent_completed=True and "
        "%d AC file(s) still verify on disk",
        target_status,
        len(file_paths),
    )
    return True


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_acceptance_criteria(
    acceptance_criteria: str | list[str] | None,
) -> list[str]:
    """Return a flat list of AC strings from various input forms."""
    if acceptance_criteria is None:
        return []
    if isinstance(acceptance_criteria, list):
        return [str(a) for a in acceptance_criteria]
    if isinstance(acceptance_criteria, str):
        stripped = acceptance_criteria.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(a) for a in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
        # Newline-separated fallback.
        return [line for line in stripped.splitlines() if line.strip()]
    return []


def _extract_file_paths(ac_list: list[str]) -> list[pathlib.Path]:
    """Return workspace-relative paths from ``File exists: <path>`` ACs."""
    paths: list[pathlib.Path] = []
    for criterion in ac_list:
        m = re.match(r"(?i)file\s+exists:\s*(.+)", criterion.strip())
        if m:
            paths.append(pathlib.Path(m.group(1).strip()))
    return paths
