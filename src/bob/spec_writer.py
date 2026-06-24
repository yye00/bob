"""bob.spec_writer — atomic YAML writer for spec_findings.yaml and reviews/ state files.

Feature 6cafea74-a3f0-4600-836c-335bb156a72d

Root cause: a prior generation wrote spec_findings.yaml non-atomically; a mid-write
SIGKILL left a truncated key (``me: perf-orphan-69``) causing yaml.scanner.ScannerError
on every subsequent boot. Six watchdog relaunch attempts all hit the same error;
chain stalled for hours.

Fix: every write to spec_findings.yaml (or any persisted YAML state file under reviews/)
MUST use an atomic tmp+rename sequence. A mid-write SIGTERM/SIGKILL leaves only
<path>.tmp on disk; the target file is either absent or contains the previous valid
version. Concurrent writers cannot leave a malformed YAML on disk.

Reader side: on ScannerError at boot, quarantine the corrupt file to
<path>.corrupt.<unix_ts> and return an empty dict. Empty findings is recoverable;
boot-loop crash is not.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

__all__ = ["atomic_write", "quarantine_corrupt_yaml"]


def atomic_write(data: dict[str, Any], path: Path | str) -> None:
    """Write *data* to *path* as YAML using an atomic tmp+rename sequence.

    Steps:
    1. Serialize *data* to ``<path>.tmp``.
    2. ``os.fsync`` the tmp file handle to flush kernel buffers to disk.
    3. ``os.rename`` the tmp onto the target path (atomic on POSIX).

    A mid-write SIGTERM/SIGKILL leaves only ``<path>.tmp`` on disk. The target
    file is either absent (first write ever) or contains the previous valid version.
    Concurrent writers cannot leave a malformed YAML on disk.

    Raises:
        OSError: if os.rename fails (propagated so the caller knows the write did
                 not complete — prefer this over silently leaving stale data).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, indent=2, allow_unicode=True, width=88)
        fh.flush()
        os.fsync(fh.fileno())
    os.rename(tmp, p)


def quarantine_corrupt_yaml(path: Path | str) -> dict[str, Any]:
    """Move a corrupt YAML state file to a timestamped quarantine path and return {}.

    On yaml.scanner.ScannerError (or any yaml.YAMLError) detected at boot:
    - Renames the file to ``<path>.corrupt.<unix_ts>``.
    - Logs a structured ``spec_findings_corrupt`` event at ERROR level.
    - Returns {} so boot continues rather than crash-looping.

    If the file does not exist, returns {} immediately (missing is recoverable).

    Raises:
        ValueError: if *path* is None or not a str/Path.
    """
    if path is None:
        raise ValueError("path must not be None")
    p = Path(path)
    if not p.exists():
        return {}
    ts = int(time.time())
    quarantine_path = Path(f"{p}.corrupt.{ts}")
    try:
        os.rename(p, quarantine_path)
    except OSError:
        logger.exception(
            "spec_findings_corrupt: failed to rename %s to %s", p, quarantine_path
        )
        return {}
    logger.error(
        "spec_findings_corrupt",
        extra={
            "event": "spec_findings_corrupt",
            "original_path": str(p),
            "quarantine_path": str(quarantine_path),
            "unix_ts": ts,
        },
    )
    return {}
