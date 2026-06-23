"""bob3.loader — safe YAML loader with corruption quarantine.

Feature d43a5b31-ab9d-4c4a-9149-3e4758979a15

Provides a safe boot-path loader for spec_findings.yaml and related YAML
state files. On yaml.scanner.ScannerError (or any yaml.YAMLError), the
loader quarantines the corrupt file and returns an empty dict so boot
continues rather than crash-looping.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

__all__ = ["handle_scanner_error", "load_safe"]


def handle_scanner_error(path: Path | str) -> dict[str, Any]:
    """Handle a yaml.scanner.ScannerError by quarantining the corrupt file.

    Logs a structured ``spec_findings_corrupt`` event at ERROR level and
    renames the file to ``<path>.corrupt.<unix_ts>``. Returns {} so the
    caller can continue with empty findings rather than crash-looping.

    If the file does not exist, returns {} immediately.
    If renaming fails (e.g. permissions), logs the failure and returns {}.
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


def load_safe(path: Path | str) -> dict[str, Any]:
    """Load YAML from *path*; quarantine and return {} if corrupt or missing.

    Safe boot-path loader. On yaml.YAMLError (including
    yaml.scanner.ScannerError), calls :func:`handle_scanner_error` to
    quarantine the corrupt file and returns an empty dict rather than
    propagating the exception. Empty findings is recoverable; a boot-loop
    crash is not.
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
        handle_scanner_error(p)
        return {}
