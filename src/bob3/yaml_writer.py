"""bob3.yaml_writer — atomic YAML write utilities.

Feature d43a5b31-ab9d-4c4a-9149-3e4758979a15

Provides atomic tmp+rename writes to prevent partial-write corruption of
spec_findings.yaml and other YAML state files under reviews/. A mid-write
SIGKILL leaves only <path>.tmp on disk; the target file is either absent
(first write ever) or contains the previous valid version.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

__all__ = ["atomic_write"]


def atomic_write(data: dict[str, Any], path: Path | str) -> None:
    """Write *data* to *path* as YAML using an atomic tmp+rename sequence.

    Steps:
    1. Serialize *data* to ``<path>.tmp``.
    2. ``os.fsync`` the tmp file handle to flush kernel buffers.
    3. ``os.rename`` the tmp onto the target (atomic on POSIX).

    A mid-write SIGTERM/SIGKILL leaves only ``<path>.tmp`` on disk. The
    target file is either absent (first write) or contains the previous
    valid version. Concurrent writers cannot leave a malformed YAML on disk.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, indent=2, allow_unicode=True, width=88)
        fh.flush()
        os.fsync(fh.fileno())
    os.rename(tmp, p)
