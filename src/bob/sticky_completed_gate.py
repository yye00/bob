"""Sticky-completed gate — re-evaluation cannot un-complete persisted work.

If a feature was status='completed' in the parent generation's DB AND its
acceptance criteria still verify on disk, no evaluator FAIL or
regression-cascade vote may flip its status below 'ready'. Reset the stamp
only when a refinement attempt actually rewrites one of the AC-named source
files.

Integration: bob.evaluator
    Call :func:`check_sticky_completed` before any evaluator-FAIL or
    regression-cascade vote that would demote a feature's status.  If the
    function returns True, the flip is blocked and the feature remains at
    'ready'.

Public API
----------
check_sticky_completed(parent_completed, target_status, acceptance_criteria,
                       workspace) -> bool
    Returns True when the status flip IS blocked (gate fires), False when
    demotion is allowed.

should_accept_status_flip(parent_completed, target_status, acceptance_criteria,
                          workspace) -> bool
    Returns True when the status flip IS allowed, False when it is blocked by
    the sticky-completed gate.  (Inverse of check_sticky_completed.)

is_sticky_completed(feature_id, db_path=None) -> bool
    Returns True if the feature has the parent_completed stamp set in the DB.

reset_completion_stamp(feature_id, db_path=None) -> None
    Clears the parent_completed stamp so future evaluations start fresh.

reset_sticky_completed_stamp(feature_id, db_path=None) -> None
    Alias for reset_completion_stamp.

enforce_sticky_completed_status(parent_completed, target_status,
                                acceptance_criteria, workspace) -> bool
    Returns True when the status flip IS blocked (gate fires), False when
    demotion is allowed.  Alias for check_sticky_completed.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re

logger = logging.getLogger(__name__)

# Statuses below 'ready' that the gate protects against.
_DEMOTING_STATUSES = frozenset({"failed", "needs_human", "pending"})


def check_sticky_completed(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True if a previously-completed feature must not be demoted.

    The gate fires (returns True, meaning "block demotion") when ALL of
    the following hold:

    1. *parent_completed* is True — the feature was status='completed' in the
       parent generation's DB.
    2. *target_status* is a status below 'ready' (one of
       ``{'failed', 'needs_human', 'pending'}``).
    3. Every file-existence AC in *acceptance_criteria* still passes on disk.
       Non-file ACs are skipped; only verifiable disk checks are enforced.

    If any condition is False the gate does not fire and the caller may
    proceed with the demotion (returns False).

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


def should_accept_status_flip(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True if the requested status flip is allowed to proceed.

    The sticky-completed gate blocks (returns False) a flip when ALL of:

    1. *parent_completed* is True — the feature was status='completed' in the
       parent generation's DB.
    2. *target_status* is a demoting status (one of
       ``{'failed', 'needs_human', 'pending'}``).
    3. Every file-existence AC in *acceptance_criteria* still passes on disk.
       Non-file ACs are skipped; only verifiable disk checks are enforced.

    If any condition is False the gate does not fire and the flip is allowed
    (returns True).

    Args:
        parent_completed: Flag indicating the feature was completed by the
            parent generation.
        target_status: The status the caller wishes to assign.
        acceptance_criteria: Raw JSON string or Python list of AC strings.
            May be None or empty — treated as an empty list.
        workspace: Root directory for disk-based AC verification. Defaults
            to ``pathlib.Path.cwd()``.

    Returns:
        True  — the flip is allowed (gate does not fire).
        False — the flip is blocked (gate fires, feature stays at 'ready').

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
        return True

    if target_status not in _DEMOTING_STATUSES:
        return True

    ac_list = _parse_acceptance_criteria(acceptance_criteria)
    file_paths = _extract_file_paths(ac_list)

    if not file_paths:
        logger.debug(
            "sticky gate: no verifiable file-existence ACs; allowing flip to %r",
            target_status,
        )
        return True

    for rel_path in file_paths:
        abs_path = ws / rel_path
        if not abs_path.exists():
            logger.info(
                "sticky gate: AC file %s missing; allowing flip to %r",
                rel_path,
                target_status,
            )
            return True

    logger.warning(
        "sticky gate: BLOCKING flip to %r — parent_completed=True and "
        "%d AC file(s) still verify on disk",
        target_status,
        len(file_paths),
    )
    return False


def is_sticky_completed(
    feature_id: str,
    db_path: pathlib.Path | str | None = None,
) -> bool:
    """Return True if *feature_id* has the parent_completed stamp set in the DB.

    This is the read-side of the sticky-completed gate: it checks whether the
    feature was marked status='completed' in the parent generation's DB and the
    stamp has not yet been cleared by a real refinement edit.

    Args:
        feature_id: The feature UUID to look up.
        db_path: Optional explicit path to the SQLite database. When None, the
            bob default db path is used (resolved from environment or cwd).

    Returns:
        True if parent_completed=1 in the DB row; False otherwise (including
        when the feature row does not exist).

    Raises:
        ValueError: If *feature_id* is not a non-empty string.
    """
    if not isinstance(feature_id, str) or not feature_id.strip():
        raise ValueError(
            f"feature_id must be a non-empty string, got {feature_id!r}"
        )

    import sqlite3

    db = pathlib.Path(db_path) if db_path is not None else _resolve_db_path()
    if not db.exists():
        logger.debug(
            "is_sticky_completed: DB not found at %s; returning False", db
        )
        return False

    try:
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute(
                "SELECT parent_completed FROM features WHERE id = ?",
                (feature_id,),
            ).fetchone()
    except sqlite3.OperationalError:
        # Table or column may not exist in older schemas.
        logger.debug(
            "is_sticky_completed: DB query failed for feature %s; returning False",
            feature_id[:8],
        )
        return False

    if row is None:
        return False
    return bool(row[0])


def reset_sticky_completed_stamp(
    feature_id: str,
    db_path: pathlib.Path | str | None = None,
) -> None:
    """Clear the parent_completed stamp for *feature_id* in the DB.

    Call this after a refinement attempt that has verifiably rewritten one or
    more of the AC-named source files.  Clearing the stamp allows future
    evaluator-FAIL or regression-cascade votes to demote the feature normally
    instead of being blocked by the sticky-completed gate.

    Args:
        feature_id: The feature UUID to update.
        db_path: Optional explicit path to the SQLite database. When None, the
            bob default db path is used.

    Raises:
        ValueError: If *feature_id* is not a non-empty string.
    """
    if not isinstance(feature_id, str) or not feature_id.strip():
        raise ValueError(
            f"feature_id must be a non-empty string, got {feature_id!r}"
        )

    import sqlite3

    db = pathlib.Path(db_path) if db_path is not None else _resolve_db_path()
    if not db.exists():
        logger.warning(
            "reset_sticky_completed_stamp: DB not found at %s; nothing to reset", db
        )
        return

    try:
        with sqlite3.connect(str(db)) as conn:
            conn.execute(
                "UPDATE features SET parent_completed = 0 WHERE id = ?",
                (feature_id,),
            )
            conn.commit()
        logger.debug(
            "reset_sticky_completed_stamp: cleared parent_completed for feature %s",
            feature_id[:8],
        )
    except sqlite3.OperationalError as exc:
        logger.warning(
            "reset_sticky_completed_stamp: DB update failed for feature %s: %s",
            feature_id[:8],
            exc,
        )


def reset_completion_stamp(
    feature_id: str,
    db_path: pathlib.Path | str | None = None,
) -> None:
    """Clear the parent_completed stamp for *feature_id* in the DB.

    Call this after a refinement attempt that has verifiably rewritten one or
    more of the AC-named source files.  Clearing the stamp allows future
    evaluator-FAIL or regression-cascade votes to demote the feature normally
    instead of being blocked by the sticky-completed gate.

    Args:
        feature_id: The feature UUID whose stamp should be cleared.
        db_path: Optional explicit path to the SQLite database. When None, the
            bob default db path is used.

    Raises:
        ValueError: If *feature_id* is not a non-empty string.
    """
    reset_sticky_completed_stamp(feature_id, db_path=db_path)


def reset_sticky_stamp(
    feature_id: str,
    db_path: pathlib.Path | str | None = None,
) -> None:
    """Clear the parent_completed stamp for *feature_id* in the DB.

    Alias for :func:`reset_sticky_completed_stamp` and
    :func:`reset_completion_stamp`. Call this after a refinement attempt that
    has verifiably rewritten one or more of the AC-named source files.

    Args:
        feature_id: The feature UUID whose stamp should be cleared.
        db_path: Optional explicit path to the SQLite database. When None, the
            bob default db path is used.

    Raises:
        ValueError: If *feature_id* is not a non-empty string.
    """
    reset_sticky_completed_stamp(feature_id, db_path=db_path)


def enforce_sticky_completion(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True if a previously-completed feature must not be demoted.

    This is the primary enforcement function for the sticky-completed gate.
    The gate fires (returns True, meaning "block demotion") when ALL of:

    1. *parent_completed* is True — the feature was status='completed' in the
       parent generation's DB.
    2. *target_status* is a status below 'ready' (one of
       ``{'failed', 'needs_human', 'pending'}``).
    3. Every file-existence AC in *acceptance_criteria* still passes on disk.

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
    return check_sticky_completed(
        parent_completed=parent_completed,
        target_status=target_status,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )


def verify_sticky_completion(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True if a previously-completed feature must not be demoted.

    Primary entry-point for the sticky-completed gate.  The gate fires
    (returns True, meaning "block demotion") when ALL of the following hold:

    1. *parent_completed* is True — the feature was status='completed' in the
       parent generation's DB.
    2. *target_status* is a status below 'ready' (one of
       ``{'failed', 'needs_human', 'pending'}``).
    3. Every file-existence AC in *acceptance_criteria* still passes on disk.

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
    return check_sticky_completed(
        parent_completed=parent_completed,
        target_status=target_status,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )


def enforce_sticky_completed_status(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True if a previously-completed feature must not be demoted.

    This is an alias for :func:`check_sticky_completed`.  The gate fires
    (returns True, meaning "block demotion") when ALL of the following hold:

    1. *parent_completed* is True — the feature was status='completed' in the
       parent generation's DB.
    2. *target_status* is a status below 'ready' (one of
       ``{'failed', 'needs_human', 'pending'}``).
    3. Every file-existence AC in *acceptance_criteria* still passes on disk.

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
    return check_sticky_completed(
        parent_completed=parent_completed,
        target_status=target_status,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )


def is_completion_persisted(
    feature_id: str,
    db_path: pathlib.Path | str | None = None,
) -> bool:
    """Return True if *feature_id* has a persisted completion stamp in the DB.

    Checks whether the feature was marked status='completed' in the parent
    generation's DB and the stamp has not been cleared by a real refinement
    edit.  This is the canonical read-side of the sticky-completed gate.

    Args:
        feature_id: The feature UUID to look up.
        db_path: Optional explicit path to the SQLite database. When None, the
            bob default db path is used (resolved from environment or cwd).

    Returns:
        True if parent_completed=1 in the DB row; False otherwise (including
        when the feature row does not exist).

    Raises:
        ValueError: If *feature_id* is not a non-empty string.
    """
    return is_sticky_completed(feature_id, db_path=db_path)


def prevent_status_downgrade(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True if a previously-completed feature must not be demoted.

    This is the primary enforcement entry-point for the sticky-completed gate.
    The gate fires (returns True, meaning "block demotion") when ALL of:

    1. *parent_completed* is True — the feature was status='completed' in the
       parent generation's DB.
    2. *target_status* is a status below 'ready' (one of
       ``{'failed', 'needs_human', 'pending'}``).
    3. Every file-existence AC in *acceptance_criteria* still passes on disk.

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
    return check_sticky_completed(
        parent_completed=parent_completed,
        target_status=target_status,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )


def _resolve_db_path() -> pathlib.Path:
    """Return the default bob DB path from environment or cwd convention."""
    import os

    env_path = os.environ.get("BOB_DB_PATH")
    if env_path:
        return pathlib.Path(env_path)
    return pathlib.Path.cwd() / "bob.db"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def should_protect_from_regression(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True if a previously-completed feature must not be demoted.

    Alias for :func:`check_sticky_completed`. The gate fires (returns True,
    meaning "block demotion") when ALL of the following hold:

    1. *parent_completed* is True — the feature was status='completed' in the
       parent generation's DB.
    2. *target_status* is a status below 'ready' (one of
       ``{'failed', 'needs_human', 'pending'}``).
    3. Every file-existence AC in *acceptance_criteria* still passes on disk.

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
    return check_sticky_completed(
        parent_completed=parent_completed,
        target_status=target_status,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )


def prevent_status_regression(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Return True if a previously-completed feature must not be demoted.

    Alias for :func:`check_sticky_completed`. The gate fires (returns True,
    meaning "block demotion") when ALL of the following hold:

    1. *parent_completed* is True — the feature was status='completed' in the
       parent generation's DB.
    2. *target_status* is a status below 'ready' (one of
       ``{'failed', 'needs_human', 'pending'}``).
    3. Every file-existence AC in *acceptance_criteria* still passes on disk.

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
    return check_sticky_completed(
        parent_completed=parent_completed,
        target_status=target_status,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )


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
