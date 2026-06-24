"""spec_findings.yaml atomic write and corrupt-file quarantine.

Feature 6289ef74-92c9-4dbd-9305-31e3b1b43283

Problem (bob version 13 r10, 2026-05-29 00:37 UTC): a partial write left
a truncated key ``me: perf-orphan-69`` in spec_findings.yaml at line 1238,
causing yaml.scanner.ScannerError on every boot attempt. Six watchdog
relaunch attempts all hit the same error; the chain stalled for hours.

Fix:
- Writer side: every write to spec_findings.yaml (or any persisted YAML
  under reviews/) MUST use atomic tmp+rename (write → fsync → os.rename).
  Mid-write SIGTERM/SIGKILL leaves only <path>.tmp on disk; the target
  file is either absent or contains the previous valid version.
- Reader side: on ScannerError at boot, quarantine the corrupt file to
  <path>.corrupt.<unix_ts> and return an empty dict. Empty findings is
  recoverable; boot-loop crash is not.
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
    "spec_findings_yaml_writer_must_use_atomic_tmp_rename_partial",
    "atomic_write_yaml",
    "quarantine_corrupt_findings",
    "load_spec_findings_safe",
]


def atomic_write_yaml(data: dict[str, Any], path: Path | str) -> None:
    """Write *data* to *path* as YAML using an atomic tmp+rename sequence.

    Steps:
    1. Serialize *data* to ``<path>.tmp``.
    2. fsync the tmp file to flush kernel buffers.
    3. os.rename the tmp onto the target (atomic on POSIX).

    A mid-write SIGKILL leaves only ``<path>.tmp``; the target is either
    absent (first write) or contains the previous valid version.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, indent=2, allow_unicode=True, width=88)
        fh.flush()
        os.fsync(fh.fileno())
    os.rename(tmp, p)


def quarantine_corrupt_findings(path: Path | str) -> dict[str, Any]:
    """Move a corrupt spec_findings file to a timestamped quarantine path.

    - Renames it to ``<path>.corrupt.<unix_ts>``.
    - Logs a structured ``spec_findings_corrupt`` event at ERROR level.
    - Returns {} so boot continues rather than crash-looping.

    Returns {} immediately when the file does not exist.
    """
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


def load_spec_findings_safe(path: Path | str) -> dict[str, Any]:
    """Load spec_findings YAML; quarantine and return {} if corrupt.

    Catches yaml.YAMLError (including yaml.scanner.ScannerError), quarantines
    the corrupt file, logs the structured event, and returns an empty dict
    rather than propagating the exception.
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
        quarantine_corrupt_findings(p)
        return {}


def spec_findings_yaml_writer_must_use_atomic_tmp_rename_partial(
    data: dict[str, Any] | None,
    path: Path | str,
    *,
    quarantine_if_corrupt: bool = False,
) -> dict[str, Any]:
    """Atomic-write *data* to *path*, or quarantine a corrupt existing file.

    Parameters
    ----------
    data:
        Findings dict to write. Ignored when *quarantine_if_corrupt* is True.
    path:
        Target path (e.g. reviews/spec_findings.yaml).
    quarantine_if_corrupt:
        When True, attempt to load *path*; if it raises yaml.YAMLError,
        quarantine the corrupt file and return ``{"quarantined": True}``.
        When False (default), perform an atomic write of *data* to *path*.

    Returns
    -------
    dict with one of:
    - ``{"success": True, "path": str(path)}`` on successful write
    - ``{"quarantined": True}`` when a corrupt file is quarantined
    """
    p = Path(path)

    if quarantine_if_corrupt and p.exists():
        try:
            with open(p, encoding="utf-8") as fh:
                result = yaml.safe_load(fh)
            if result is None or isinstance(result, dict):
                pass
            else:
                quarantine_corrupt_findings(p)
                return {"quarantined": True}
        except yaml.YAMLError:
            quarantine_corrupt_findings(p)
            return {"quarantined": True}

    if data is None:
        data = {}
    atomic_write_yaml(data, p)
    return {"success": True, "path": str(p)}
