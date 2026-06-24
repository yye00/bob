"""Sticky-completed gate — re-evaluation cannot un-complete persisted work.

If a feature was status='completed' in the parent generation's DB AND its
acceptance criteria still verify on disk, no evaluator FAIL or
regression-cascade vote may flip its status below 'ready'. Reset the stamp
only when a refinement attempt actually rewrites one of the AC-named source
files.

Public API:
    :func:`check_completion_sticky` — gate check integrating with bob3.evaluator
"""

from __future__ import annotations

import json
import logging
import pathlib
import re

logger = logging.getLogger(__name__)

# Statuses below 'ready' that the gate protects against.
_DEMOTING_STATUSES = frozenset({"failed", "needs_human", "pending"})


def check_completion_sticky(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True if a previously-completed feature must not be demoted.

    Integrates with bob3.evaluator to prevent evaluator FAIL or
    regression-cascade votes from flipping a completed feature's status below
    'ready' while its acceptance-criteria artifacts still verify on disk.

    The gate fires (returns True, meaning "block demotion") when ALL of:

    1. *parent_completed* is True — the feature was status='completed' in the
       parent generation's DB.
    2. *target_status* is a status below 'ready' (one of
       ``{'failed', 'needs_human', 'pending'}``).
    3. Every file-existence AC in *acceptance_criteria* still passes on disk.
       Non-file ACs are skipped; only verifiable disk checks are enforced.

    If any condition is False the gate does not fire and demotion may proceed.

    Args:
        parent_completed: Flag indicating the feature was completed by the
            parent generation.
        target_status: The status the caller wishes to assign.
        acceptance_criteria: Raw JSON string or Python list of AC strings.
            May be None or empty — treated as an empty list.
        workspace: Root directory for disk-based AC verification. Defaults
            to ``pathlib.Path.cwd()``.

    Returns:
        True  — the gate fires; demotion BLOCKED.
        False — the gate does not fire; demotion may proceed.

    Raises:
        ValueError: If *parent_completed* is not a bool, *target_status* is
            not a non-empty string, or *workspace* exists but is not a directory.
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

    if not parent_completed:
        return False

    if target_status not in _DEMOTING_STATUSES:
        return False

    ac_list = _parse_acceptance_criteria(acceptance_criteria)
    file_paths = _extract_file_paths(ac_list)

    if not file_paths:
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
# bob3.evaluator integration
# ---------------------------------------------------------------------------


def evaluator_guard(
    feature_id: str,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True (block demotion) when evaluator verdict would un-complete persisted work.

    Thin wrapper around :func:`check_completion_sticky` that resolves the
    ``parent_completed`` flag from the bob3 database.  Called by the
    bob3.evaluator before applying a FAIL or cascade-rollback verdict so that
    completed work cannot be un-completed by a re-evaluation.

    Falls back to False (allow demotion) if the bob3 DB is unavailable.

    Args:
        feature_id: The feature UUID to look up.
        target_status: The status the evaluator wants to assign.
        acceptance_criteria: The feature's ACs (JSON string or list).
        workspace: Workspace root for disk verification.

    Returns:
        True if the evaluator's demotion should be blocked, False otherwise.
    """
    try:
        from bob3 import db as _db
        feature_row = _db.get_feature(feature_id)
        parent_completed = bool(getattr(feature_row, "parent_completed", False))
    except Exception:
        logger.debug(
            "evaluator_guard: could not resolve parent_completed for %s; allowing demotion",
            feature_id[:8] if feature_id else "?",
        )
        return False

    return check_completion_sticky(
        parent_completed=parent_completed,
        target_status=target_status,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )


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
