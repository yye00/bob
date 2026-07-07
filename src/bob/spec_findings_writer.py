"""bob.spec_findings_writer — atomic write and corruption recovery for spec_findings.yaml.

Feature c24eba26-1ea6-47f8-9a07-384f277e7bd4

Problem: partial writes to spec_findings.yaml (from SIGTERM/SIGKILL mid-write or
concurrent writers) leave a malformed YAML that kills bob boot with
yaml.scanner.ScannerError.  The chain stalls; watchdog relaunch attempts all hit
the same error.

Fix:
- Writer side: write_atomic() serializes to <path>.tmp, fsyncs, then os.rename()s
  onto the target.  A mid-write kill leaves only <path>.tmp; the target stays valid.
- Reader side: load_with_corruption_recovery() catches yaml.YAMLError, quarantines
  the corrupt file to <path>.corrupt.<unix_ts>, logs a structured event, and returns
  {} so bob boot can continue.  Empty findings is recoverable; boot-loop crash is not.
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
    "write_atomic",
    "atomic_write_findings",
    "load_findings_or_quarantine",
    "write_atomic_yaml",
    "write_spec_findings_atomic",
    "write_findings_atomically",
    "handle_scanner_error",
    "handle_corrupted_findings",
    "quarantine_corrupt_findings",
    "quarantine_corrupted_findings",
    "quarantine_corrupted",
    "load_with_corruption_recovery",
    "load_with_corruption_handler",
    "load_spec_findings_safe",
]


def write_atomic(data: dict[str, Any], path: Path | str) -> None:
    """Write *data* to *path* as YAML using an atomic tmp+rename sequence.

    Algorithm:
    1. Serialize *data* to ``<path>.tmp``.
    2. fsync the tmp file descriptor to flush kernel buffers to disk.
    3. os.rename() the tmp onto the target path (atomic on POSIX).

    A mid-write SIGKILL leaves only ``<path>.tmp`` on disk.  The target is either
    absent (first write) or contains the previous valid version — never a partial
    write that would corrupt YAML parsing.

    Args:
        data: Dictionary to serialize as YAML.
        path: Destination file path (created if absent; parent dirs created).

    Raises:
        OSError: if the rename or write fails.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, indent=2, allow_unicode=True, width=88)
        fh.flush()
        os.fsync(fh.fileno())
    os.rename(tmp, p)


def atomic_write_findings(data: dict[str, Any], path: Path | str) -> None:
    """AC-required entry point: bob.spec_findings_writer.atomic_write_findings.

    Write *data* to *path* as YAML using the atomic tmp+fsync+rename sequence.
    A mid-write SIGTERM/SIGKILL leaves only ``<path>.tmp`` — the target is never
    a partial write that would corrupt YAML parsing.  Delegates to write_atomic.
    """
    write_atomic(data, path)


def load_findings_or_quarantine(path: Path | str) -> dict[str, Any]:
    """AC-required entry point: bob.spec_findings_writer.load_findings_or_quarantine.

    Load spec_findings YAML, recovering from corruption.  On yaml.YAMLError
    (including ScannerError from a partial write), the corrupt file is quarantined
    to ``<path>.corrupt.<unix_ts>``, a structured ``spec_findings_corrupt`` event
    is logged, and {} is returned so bob boot continues instead of crash-looping.
    Delegates to load_with_corruption_recovery.
    """
    return load_with_corruption_recovery(path)


def write_atomic_yaml(data: dict[str, Any], path: Path | str) -> None:
    """AC-required alias: bob.spec_findings_writer.write_atomic_yaml.

    Writes *data* to *path* as YAML using the atomic tmp+fsync+rename sequence.
    Delegates to write_atomic — same POSIX atomicity guarantees.
    """
    write_atomic(data, path)


def write_spec_findings_atomic(data: dict[str, Any], path: Path | str) -> None:
    """Alias for write_atomic — required by AC (bob.spec_findings_writer.write_spec_findings_atomic)."""
    write_atomic(data, path)


def write_findings_atomically(data: dict[str, Any], path: Path | str) -> None:
    """Write spec findings to *path* atomically via tmp+rename+fsync.

    AC-required name: bob.spec_findings_writer.write_findings_atomically.
    Delegates to write_atomic — same POSIX atomicity guarantees.
    """
    write_atomic(data, path)


def _quarantine(p: Path) -> None:
    """Move *p* to a timestamped quarantine path and log a structured event."""
    ts = int(time.time())
    quarantine_path = Path(f"{p}.corrupt.{ts}")
    try:
        os.rename(p, quarantine_path)
    except OSError:
        logger.exception(
            "spec_findings_corrupt: failed to quarantine %s to %s", p, quarantine_path
        )
        return
    logger.error(
        "spec_findings_corrupt",
        extra={
            "event": "spec_findings_corrupt",
            "original_path": str(p),
            "quarantine_path": str(quarantine_path),
            "unix_ts": ts,
        },
    )


def quarantine_corrupt_findings(path: Path | str) -> dict[str, Any]:
    """Quarantine a corrupt spec_findings file and return {}.

    Moves the file at *path* to ``<path>.corrupt.<unix_ts>`` and logs a
    structured ``spec_findings_corrupt`` event.  Returns {} so the caller can
    continue rather than crash-looping.

    If the file does not exist, returns {} immediately.

    Raises:
        ValueError: if *path* is None.
    """
    if path is None:
        raise ValueError("path must not be None")
    p = Path(path)
    if not p.exists():
        return {}
    _quarantine(p)
    return {}


def load_with_corruption_recovery(path: Path | str) -> dict[str, Any]:
    """Load spec_findings YAML with automatic corruption recovery.

    Safe boot-path loader.  On yaml.YAMLError (including ScannerError from partial
    writes), the corrupt file is quarantined to ``<path>.corrupt.<unix_ts>`` and an
    empty dict is returned.  This lets bob boot proceed rather than crash-looping.

    Args:
        path: Path to the spec_findings YAML file.

    Returns:
        Parsed dict, or {} if the file is missing, empty, not a dict, or corrupt.
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
            "spec_findings_corrupt: ScannerError loading %s — quarantining", p
        )
        _quarantine(p)
        return {}


def handle_scanner_error(path: Path | str) -> dict[str, Any]:
    """Handle a yaml.scanner.ScannerError on spec_findings load.

    Logs a structured ``spec_findings_corrupt`` event, quarantines the corrupt
    file to ``<path>.corrupt.<unix_ts>``, and returns {} so bob can continue
    booting.  This is the explicit named handler required by AC.

    Args:
        path: Path to the corrupt spec_findings YAML file.

    Returns:
        {} always (empty findings is recoverable; boot-loop crash is not).
    """
    p = Path(path)
    logger.error(
        "spec_findings_corrupt: ScannerError on %s — quarantining", p,
        extra={
            "event": "spec_findings_corrupt",
            "original_path": str(p),
        },
    )
    return quarantine_corrupt_findings(path)


def load_with_corruption_handler(path: Path | str) -> dict[str, Any]:
    """AC-required alias: bob.spec_findings_writer.load_with_corruption_handler.

    Delegates to load_with_corruption_recovery — same quarantine-on-ScannerError behaviour.
    """
    return load_with_corruption_recovery(path)


def load_spec_findings_safe(path: Path | str) -> dict[str, Any]:
    """Alias for load_with_corruption_recovery — required by AC."""
    return load_with_corruption_recovery(path)


def quarantine_corrupted(path: Path | str) -> dict[str, Any]:
    """AC-required alias for quarantine_corrupt_findings.

    AC: bob.spec_findings_writer.quarantine_corrupted
    """
    return quarantine_corrupt_findings(path)


def quarantine_corrupted_findings(path: Path | str) -> dict[str, Any]:
    """AC-required alias for quarantine_corrupt_findings.

    AC: bob.spec_findings_writer.quarantine_corrupted_findings
    """
    return quarantine_corrupt_findings(path)


def handle_corrupted_findings(path: Path | str) -> dict[str, Any]:
    """AC-required handler: bob.spec_findings_writer.handle_corrupted_findings.

    Logs a structured spec_findings_corrupt event, quarantines the corrupt file
    to <path>.corrupt.<unix_ts>, and returns {} so bob boot continues.
    This is the AC-named entry point for corruption recovery.

    Args:
        path: Path to the corrupt spec_findings YAML file.

    Returns:
        {} always (empty findings is recoverable; boot-loop crash is not).
    """
    p = Path(path)
    logger.error(
        "spec_findings_corrupt: corrupted findings at %s — quarantining", p,
        extra={
            "event": "spec_findings_corrupt",
            "original_path": str(p),
        },
    )
    return quarantine_corrupt_findings(path)
