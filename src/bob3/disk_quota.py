"""Per-sub-agent disk quota and session-log pruning (F-R6-303).

Round 5 saw free disk drop from ~25GB to 18MB in a few hours because
sub-agent session logs in ``~/.claude/sessions/`` grow unbounded. The
spawn watchdog correctly halts on the 5GB threshold, but the root cause
is uncontrolled growth.

This module provides:

* :func:`enforce_session_quota` — measure total bytes used by a session
  directory and prune the oldest files first until the directory is back
  under the configured quota.
* :func:`check_pre_spawn` — verify there is enough free disk before
  launching a new sub-agent; returns ``(allowed, reason)`` so callers can
  abort the spawn cleanly.
* :func:`disk_pressure_warning` — return a human-readable warning when
  free disk on a path drops below 20 % of the total, or ``None``
  otherwise.

The functions are intentionally narrow: they take ``pathlib.Path``
arguments and return plain dicts/strings so they can be invoked from any
caller (the sub-agent runner, the CLI, a periodic janitor task, etc.)
without dragging in additional dependencies.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Default per-sub-agent quota: 2 GiB. Round 5 saw individual session
# directories balloon to multiple GiB; 2 GiB is a generous-but-bounded
# ceiling that still leaves headroom for the watchdog's 5 GiB free-disk
# floor on a 25 GiB working volume.
DEFAULT_QUOTA_BYTES: int = 2 * 1024**3


def _iter_files(session_dir: Path):
    """Yield ``(path, size, mtime)`` for every regular file under
    ``session_dir``.

    ``PermissionError`` and ``FileNotFoundError`` from ``rglob`` /
    ``stat`` are swallowed: this helper is invoked from a finally block
    and must never raise.
    """

    try:
        iterator = session_dir.rglob("*")
    except (PermissionError, OSError):
        return
    for entry in iterator:
        try:
            if not entry.is_file() or entry.is_symlink():
                continue
            st = entry.stat()
        except (PermissionError, FileNotFoundError, OSError):
            continue
        yield entry, st.st_size, st.st_mtime


def _measure(session_dir: Path) -> int:
    """Return the total size in bytes of every regular file under
    ``session_dir``. Returns ``0`` if the directory does not exist."""

    if not session_dir.exists():
        return 0
    return sum(size for _, size, _ in _iter_files(session_dir))


def enforce_session_quota(
    session_dir: Path,
    quota_bytes: int = DEFAULT_QUOTA_BYTES,
) -> dict:
    """Enforce a byte quota on ``session_dir`` by deleting oldest files first.

    Walks ``session_dir`` recursively, measures the total size of regular
    files, and — if the total exceeds ``quota_bytes`` — deletes files
    starting with the oldest (smallest ``mtime``) until the remaining
    total is at or below the quota.

    Missing directories are treated as empty: the function returns a
    zeroed result rather than raising.

    Args:
        session_dir: Directory holding session/log files for a single
            sub-agent. Must be safe to delete from.
        quota_bytes: Maximum allowed total size in bytes. Defaults to
            :data:`DEFAULT_QUOTA_BYTES` (2 GiB).

    Returns:
        Dict with keys ``before`` (total bytes before pruning),
        ``after`` (total bytes after pruning), ``pruned`` (number of
        files deleted), and ``quota`` (the quota that was applied).
    """

    quota_bytes = max(0, int(quota_bytes))

    if not session_dir.exists():
        return {"before": 0, "after": 0, "pruned": 0, "quota": quota_bytes}

    entries = list(_iter_files(session_dir))
    before = sum(size for _, size, _ in entries)

    if before <= quota_bytes:
        return {
            "before": before,
            "after": before,
            "pruned": 0,
            "quota": quota_bytes,
        }

    # Oldest first. Sorting by mtime ascending puts the oldest entries at
    # the head of the list; we pop from the front until we're back under
    # the quota.
    entries.sort(key=lambda item: item[2])

    pruned = 0
    current = before
    for path, size, _ in entries:
        if current <= quota_bytes:
            break
        try:
            path.unlink()
        except (PermissionError, FileNotFoundError, OSError) as exc:
            logger.warning(
                "disk_quota: failed to prune %s: %s", path, exc,
            )
            continue
        current -= size
        pruned += 1

    after = _measure(session_dir)
    logger.info(
        "disk_quota: pruned %d files from %s (%d -> %d bytes, quota=%d)",
        pruned,
        session_dir,
        before,
        after,
        quota_bytes,
    )
    return {
        "before": before,
        "after": after,
        "pruned": pruned,
        "quota": quota_bytes,
    }


def check_pre_spawn(
    sessions_root: Path,
    quota_bytes: int = DEFAULT_QUOTA_BYTES,
    min_free_disk_bytes: Optional[int] = None,
) -> tuple[bool, str]:
    """Verify there is enough free disk to safely spawn a sub-agent.

    The default minimum free-disk requirement is ``2 * quota_bytes`` —
    one quota's worth for the new sub-agent's session logs plus a
    matching reserve so that watchdog/cleanup work has headroom.

    Args:
        sessions_root: Root directory holding all sub-agent session
            directories. ``shutil.disk_usage`` is called on the closest
            existing ancestor of this path so that the check works even
            before the directory has been created.
        quota_bytes: Per-sub-agent quota in bytes (used only to derive
            the default ``min_free_disk_bytes``).
        min_free_disk_bytes: Override for the minimum free-disk
            requirement. ``None`` (default) means ``2 * quota_bytes``.

    Returns:
        ``(True, "ok")`` when the spawn may proceed; otherwise
        ``(False, <human-readable reason>)``.
    """

    if min_free_disk_bytes is None:
        min_free_disk_bytes = 2 * int(quota_bytes)

    # Walk up until we find an existing ancestor — disk_usage on a
    # not-yet-created sessions_root would raise FileNotFoundError.
    probe = sessions_root
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            break
        probe = parent

    try:
        usage = shutil.disk_usage(str(probe))
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return False, f"disk_usage failed for {probe}: {exc}"

    if usage.free < min_free_disk_bytes:
        return (
            False,
            (
                f"free disk {usage.free} bytes below required "
                f"{min_free_disk_bytes} bytes (quota={quota_bytes}) "
                f"on {probe}"
            ),
        )

    return True, "ok"


def reserve_session_disk(
    sessions_root: Path,
    estimated_bytes: int = DEFAULT_QUOTA_BYTES,
    halt_threshold_bytes: int = 5 * 1024**3,
) -> tuple[bool, str]:
    """Reserve estimated disk for a new sub-agent session, refusing if unsafe.

    Checks whether granting ``estimated_bytes`` to the new sub-agent session
    would push free disk below ``halt_threshold_bytes`` (the spawn-watchdog
    halt threshold, default 5 GiB). Returns ``(True, "ok")`` when the
    reservation is safe; otherwise ``(False, <reason>)`` so the caller can
    abort the spawn instead of triggering the hard halt mid-run.

    Unlike :func:`check_pre_spawn` (which checks free >= 2x quota), this
    function checks free - estimated_bytes >= halt_threshold_bytes, matching
    the description of "reserves an estimated working-set size and refuses to
    spawn if the reservation would push free disk below the halt threshold."

    Args:
        sessions_root: Path whose filesystem will be queried for free space.
            Walks up to the nearest existing ancestor when the path does not
            yet exist.
        estimated_bytes: Estimated working-set size the new sub-agent will
            consume. Defaults to :data:`DEFAULT_QUOTA_BYTES` (2 GiB).
        halt_threshold_bytes: Minimum free disk that must remain after the
            reservation. Defaults to 5 GiB (the watchdog halt threshold).

    Returns:
        ``(True, "ok")`` when the reservation is safe; otherwise
        ``(False, <human-readable reason>)``.
    """
    probe = sessions_root
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            break
        probe = parent

    try:
        usage = shutil.disk_usage(str(probe))
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return False, f"disk_usage failed for {probe}: {exc}"

    free_after = usage.free - estimated_bytes
    if free_after < halt_threshold_bytes:
        return (
            False,
            (
                f"reserving {estimated_bytes} bytes for new session would leave "
                f"{free_after} bytes free (below halt threshold "
                f"{halt_threshold_bytes} bytes) on {probe}"
            ),
        )

    return True, "ok"


def disk_pressure_warning(disk_path: Path = Path("/")) -> str | None:
    """Return a human-readable warning when ``disk_path`` is under 20 % free.

    Args:
        disk_path: Filesystem path to query with ``shutil.disk_usage``.
            Defaults to ``/``.

    Returns:
        ``None`` when free disk is at or above 20 % of total. Otherwise a
        single-line string suitable for logging or surfacing to an
        operator.
    """

    try:
        usage = shutil.disk_usage(str(disk_path))
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return f"disk_pressure_warning: disk_usage failed for {disk_path}: {exc}"

    if usage.total <= 0:
        return None

    ratio = usage.free / usage.total
    if ratio >= 0.20:
        return None

    return (
        f"DISK PRESSURE: {disk_path} has {usage.free} bytes free of "
        f"{usage.total} ({ratio * 100:.1f}% free; threshold 20%)."
    )


__all__ = [
    "DEFAULT_QUOTA_BYTES",
    "enforce_session_quota",
    "reserve_session_disk",
    "check_pre_spawn",
    "disk_pressure_warning",
]
