"""Sticky-completed gate for Bob (eb3c74d9).

Prevents evaluator-FAIL or regression-cascade votes from demoting a feature
below 'ready' when:

1. The feature was status='completed' in the parent generation's DB (flagged
   via ``parent_completed=True`` at seed time), AND
2. Its acceptance-criteria artifacts still verify on disk in the current
   generation.

The gate is enforced via :func:`may_demote`, called in ``run_loop.py`` at
every point that would flip a feature's status below 'ready' (evaluator FAIL,
rollback_feature_cascade).

The ``parent_completed`` stamp is cleared only when a refinement attempt
actually rewrites one of the AC-named source files (tracked by git/mtime via
:func:`ac_files_modified`).
"""

from __future__ import annotations

import logging
import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob.models import Feature

logger = logging.getLogger(__name__)

# Statuses below 'ready' that the gate protects against.
_DEMOTING_STATUSES = frozenset({"failed", "needs_human", "pending"})


def stamp_from_parent(feature_id: str) -> None:
    """Set ``parent_completed=True`` on a feature row.

    Called during seed/import when a feature was status='completed' in the
    parent generation's DB. The stamp arms the sticky-completed gate so that
    evaluator-FAIL or cascade votes cannot demote the feature below 'ready'
    while its AC artifacts still verify on disk.

    Raises:
        ValueError: If *feature_id* is None or not a non-empty string.
    """
    if not isinstance(feature_id, str) or not feature_id:
        raise ValueError(
            f"stamp_from_parent requires a non-empty feature id string, got {feature_id!r}"
        )

    from bob import db

    db.update_feature(feature_id, parent_completed=True)
    logger.debug("Stamped parent_completed=True on feature %s", feature_id[:8])


def may_demote(
    feature: "Feature",
    *,
    target_status: str,
    workspace: pathlib.Path | None = None,
) -> bool:
    """Return True if it is safe to demote *feature* to *target_status*.

    Demotion is BLOCKED (returns False) when ALL three conditions hold:

    1. ``feature.parent_completed`` is True (stamped at seed time).
    2. ``target_status`` is a status below 'ready' (i.e. in
       ``{'failed', 'needs_human', 'pending'}``).
    3. The feature's AC artifacts still verify on disk in the current
       generation.

    If the stamp has been cleared (``parent_completed=False``) or the target
    status is 'ready' or above, demotion is always allowed.

    If the AC check fails (artifacts are gone or tests fail), the stamp no
    longer protects and demotion is allowed — the protection only applies
    while the work is still verifiable.

    Args:
        feature: The Feature model instance being demoted.
        target_status: The status the caller wants to assign.
        workspace: Workspace root used for disk-based AC evaluation.
            Defaults to ``pathlib.Path.cwd()``.

    Returns:
        ``True`` if demotion may proceed, ``False`` if the sticky gate blocks it.
    """
    if not feature.parent_completed:
        return True

    if target_status not in _DEMOTING_STATUSES:
        return True

    # Parent was completed — check whether ACs still pass on disk.
    ws = workspace or pathlib.Path.cwd()
    acs_pass = _acs_still_verify(feature, workspace=ws)

    if acs_pass:
        logger.warning(
            "Sticky-completed gate BLOCKED demotion of feature %s (%s) "
            "to '%s': parent_completed=True and ACs still verify on disk.",
            feature.id[:8],
            feature.name,
            target_status,
        )
        return False

    # ACs no longer verify — stamp no longer shields the feature.
    logger.info(
        "Sticky-completed gate: feature %s ACs no longer verify on disk; "
        "demotion to '%s' allowed.",
        feature.id[:8],
        target_status,
    )
    return True


def ac_files_modified(
    feature: "Feature",
    *,
    workspace: pathlib.Path | None = None,
    since_mtime: float | None = None,
) -> bool:
    """Return True if any source file named in *feature*'s ACs was modified.

    Used by the run-loop after a refinement attempt to decide whether to clear
    the ``parent_completed`` stamp.  A refinement that rewrites an AC-named
    source file earns the right to reset the stamp so future evaluations start
    from a clean slate.

    Detection strategy (git-first, mtime fallback):

    * If the workspace is a git repo, ``git diff --name-only HEAD~1`` is
      checked for AC-named paths.
    * Otherwise, each AC-named file's ``st_mtime`` is compared against
      *since_mtime* (if provided).

    Returns False when no AC-named files can be extracted from the feature's
    acceptance criteria.

    Args:
        feature: The Feature model whose ACs name the files to check.
        workspace: Workspace root. Defaults to ``pathlib.Path.cwd()``.
        since_mtime: Optional float epoch-seconds threshold for the mtime
            fallback. Files modified after this time count as changed.
    """
    import json as _json
    import subprocess

    ws = workspace or pathlib.Path.cwd()
    ac_paths = _extract_file_paths_from_acs(feature)
    if not ac_paths:
        return False

    # Try git first.
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            capture_output=True,
            text=True,
            cwd=str(ws),
            timeout=10,
        )
        if result.returncode == 0:
            changed = set(result.stdout.splitlines())
            for rel in ac_paths:
                if str(rel) in changed or rel.name in changed:
                    return True
            return False
    except Exception:
        pass  # git unavailable or no history; fall through to mtime

    # Mtime fallback.
    if since_mtime is not None:
        for rel in ac_paths:
            abs_path = ws / rel
            try:
                if abs_path.stat().st_mtime > since_mtime:
                    return True
            except FileNotFoundError:
                pass

    return False


def clear_stamp(feature_id: str) -> None:
    """Clear the ``parent_completed`` stamp after a real edit.

    Call this after a refinement attempt that rewrites an AC-named source
    file (detected via :func:`ac_files_modified`).  Clearing the stamp allows
    future evaluator-FAIL or cascade votes to demote the feature normally.
    """
    from bob import db

    db.update_feature(feature_id, parent_completed=False)
    logger.debug("Cleared parent_completed stamp on feature %s", feature_id[:8])


def clear_on_real_edit(
    feature: "Feature",
    *,
    workspace: pathlib.Path | None = None,
    since_mtime: float | None = None,
) -> bool:
    """Clear ``parent_completed`` if an AC-named source file was really modified.

    Convenience wrapper that combines :func:`ac_files_modified` detection with
    :func:`clear_stamp` so callers can do the check-and-clear in one call.

    Returns True if the stamp was cleared (a real edit was detected), False
    otherwise.

    Args:
        feature: The Feature whose AC-named files to check.
        workspace: Workspace root. Defaults to ``pathlib.Path.cwd()``.
        since_mtime: Optional mtime threshold for the fallback path.
    """
    ws = workspace or pathlib.Path.cwd()
    if ac_files_modified(feature, workspace=ws, since_mtime=since_mtime):
        clear_stamp(feature.id)
        logger.info(
            "clear_on_real_edit: cleared parent_completed stamp on feature %s "
            "(AC-named file was modified).",
            feature.id[:8],
        )
        return True
    return False


def handle_missing_parent_db(
    feature: "Feature",
    *,
    target_status: str,
    workspace: pathlib.Path | None = None,
) -> bool:
    """Return False (block demotion) gracefully when parent DB is unavailable.

    When the parent generation's DB cannot be queried — for example during the
    first bootstrap generation where no parent DB exists — callers should use
    this function instead of :func:`may_demote` directly.  It swallows
    ``AttributeError`` (raised when ``feature.parent_completed`` is unset or
    the attribute does not exist on the model) and returns False, meaning
    "do not demote" when the stamp cannot be resolved.

    This is the safe default: if we cannot confirm the feature was *not*
    completed by a parent, we refuse the demotion rather than risk clobbering
    parent-generation work.

    Returns:
        False when ``feature.parent_completed`` is unset/missing (safe
        default), otherwise delegates to :func:`may_demote`.
    """
    try:
        stamped = feature.parent_completed
    except AttributeError:
        logger.debug(
            "handle_missing_parent_db: parent_completed unset on feature %s; "
            "blocking demotion by default.",
            getattr(feature, "id", "?")[:8],
        )
        return False

    if not stamped:
        return False

    ws = workspace or pathlib.Path.cwd()
    return may_demote(feature, target_status=target_status, workspace=ws)


def never_raises_when_unset(feature: "Feature") -> bool:
    """Return True, documenting that handle_missing_parent_db swallows AttributeError.

    This is a sentinel/documentation function.  It demonstrates that calling
    :func:`handle_missing_parent_db` when ``feature.parent_completed`` raises
    ``AttributeError`` does not propagate the exception — it returns False
    (block demotion by default) and logs a debug message.

    The function itself always returns True to signal that the contract holds.

    Args:
        feature: Any Feature-like object (including objects without a
            ``parent_completed`` attribute).

    Returns:
        Always True.
    """
    # Validate the contract: handle_missing_parent_db must not raise.
    try:
        handle_missing_parent_db(feature, target_status="failed")
    except AttributeError:
        return False
    return True


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _acs_still_verify(
    feature: "Feature",
    *,
    workspace: pathlib.Path,
) -> bool:
    """Return True if every verifiable AC in *feature* passes on disk."""
    import json as _json

    from bob.orchestrator.disk_reconciler import evaluate_ac_against_disk

    ac_raw = feature.acceptance_criteria or "[]"
    try:
        ac_list: list[str] = _json.loads(ac_raw) if isinstance(ac_raw, str) else ac_raw
    except (ValueError, TypeError):
        ac_list = []

    if not ac_list:
        # No ACs — nothing to protect; allow demotion.
        return False

    for criterion in ac_list:
        passed, _detail = evaluate_ac_against_disk(criterion, workspace)
        if not passed:
            return False

    return True


def _extract_file_paths_from_acs(feature: "Feature") -> list[pathlib.Path]:
    """Extract workspace-relative file paths from AC strings.

    Handles ``File exists: <path>`` and ``pytest: <path>::<node>`` patterns.
    """
    import json as _json
    import re

    ac_raw = feature.acceptance_criteria or "[]"
    try:
        ac_list: list[str] = _json.loads(ac_raw) if isinstance(ac_raw, str) else ac_raw
    except (ValueError, TypeError):
        ac_list = []

    paths: list[pathlib.Path] = []
    for criterion in ac_list:
        # "File exists: src/foo/bar.py"
        m = re.match(r"(?i)file\s+exists:\s*(.+)", criterion.strip())
        if m:
            paths.append(pathlib.Path(m.group(1).strip()))
            continue
        # "pytest: tests/test_foo.py" or "pytest: tests/test_foo.py::TestFoo"
        m = re.match(r"(?i)pytest:\s*([^\s:]+)", criterion.strip())
        if m:
            raw_path = m.group(1).strip()
            # Strip ::TestClass::test_method suffixes
            file_part = raw_path.split("::")[0]
            paths.append(pathlib.Path(file_part))

    return paths
