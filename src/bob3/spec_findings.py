"""bob3.spec_findings — atomic write and quarantine for spec_findings.yaml.

Feature b37d0f34-5d02-4fdc-be9b-b205e2839fcb

Problem (bob3 version 13 r10, 2026-05-29 00:37 UTC): a partial write left a
truncated key ``me: perf-orphan-69`` in spec_findings.yaml at line 1238, causing
yaml.scanner.ScannerError on every boot attempt.  Six watchdog relaunch attempts
all hit the same error; the chain stalled for hours.

Fix:
- Writer side: every write to spec_findings.yaml (or any persisted YAML under
  reviews/) MUST use atomic tmp+rename (write → fsync → os.rename).  Mid-write
  SIGTERM/SIGKILL leaves only <path>.tmp on disk; the target file is either
  absent or contains the previous valid version.
- Reader side: on ScannerError at boot, quarantine the corrupt file to
  <path>.corrupt.<unix_ts> and return an empty dict.  Empty findings is
  recoverable; boot-loop crash is not.

Public API
----------
atomic_write(data, path)
    Write *data* to *path* as YAML via atomic tmp+rename+fsync.

quarantine_corrupted(path)
    Move a corrupt findings file to a timestamped quarantine path and return {}.

load_safe(path)
    Safe boot-path loader: quarantine and return {} on any yaml.YAMLError.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

__all__ = [
    "atomic_write",
    "write_atomic",
    "quarantine_corrupted",
    "quarantine_corrupt_file",
    "load_safe",
    "load_with_corruption_recovery",
]


def atomic_write(data: dict[str, Any], path: Path | str) -> None:
    """Write *data* to *path* as YAML using an atomic tmp+rename sequence.

    Steps:
    1. Serialize *data* to ``<path>.tmp``.
    2. Call ``os.fsync`` on the open tmp file handle to flush kernel buffers.
    3. ``os.rename`` the tmp onto the target path (atomic on POSIX).

    A mid-write SIGKILL leaves only ``<path>.tmp`` on disk; the target file is
    either absent (first write) or contains the previous valid version.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, indent=2, allow_unicode=True, width=88)
        fh.flush()
        os.fsync(fh.fileno())
    os.rename(tmp, p)


def quarantine_corrupted(path: Path | str) -> dict[str, Any]:
    """Move a corrupt spec_findings file to a timestamped quarantine path.

    On yaml.scanner.ScannerError (or any yaml.YAMLError):
    - Renames the file to ``<path>.corrupt.<unix_ts>``.
    - Logs a structured ``spec_findings_corrupt`` event at ERROR level.
    - Returns {} so boot continues rather than crash-looping.

    If the file does not exist, returns {} immediately.

    Raises ValueError if *path* is None or not a str/Path.
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


def quarantine_corrupt_file(path: Path | str) -> dict[str, Any]:
    """Alias for :func:`quarantine_corrupted` — canonical AC-facing name."""
    return quarantine_corrupted(path)


def write_atomic(data: dict[str, Any], path: Path | str) -> None:
    """AC-facing alias for :func:`atomic_write` (AC: bob3.spec_findings.write_atomic)."""
    atomic_write(data, path)


def load_with_corruption_recovery(path: Path | str) -> dict[str, Any]:
    """AC-facing alias for :func:`load_safe` (AC: bob3.spec_findings.load_with_corruption_recovery)."""
    return load_safe(path)


def load_safe(path: Path | str) -> dict[str, Any]:
    """Load spec_findings YAML; quarantine and return {} if corrupt.

    Safe boot-path loader.  Catches yaml.YAMLError (including
    yaml.scanner.ScannerError), invokes :func:`quarantine_corrupted`, logs the
    structured event, and returns an empty dict rather than propagating the
    exception.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if data is None:
            return {}
        if not isinstance(data, dict):
            return {}
        return data
    except yaml.YAMLError:
        logger.error(
            "spec_findings_corrupt: ScannerError while loading %s — quarantining", p
        )
        quarantine_corrupted(p)
        return {}
