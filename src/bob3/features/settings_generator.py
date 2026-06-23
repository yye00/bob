"""Per-feature settings.json generator for Claude-Code worker dispatch.

Workers do NOT inherit hooks/permissions from the parent settings.json
(Claude Code issue #27661).  This module generates and writes an explicit
settings.json for each worker before it is launched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.dispatch import generate_worker_settings as _generate_worker_settings


def generate_worker_settings(
    feature: Any,
    *,
    bob3_dir: str | Path,
    extra_allow: list[str] | None = None,
) -> Path:
    """Generate and write per-feature settings.json for a Claude-Code worker.

    Workers do NOT inherit hooks/permissions from the parent settings.json
    (Issue #27661), so settings must be declared per-worker at dispatch time.

    Args:
        feature:     Feature object; ``feature.id`` used as directory name.
        bob3_dir:    Path to the .bob3 directory (project-level).
        extra_allow: Additional allow patterns merged with project defaults.

    Returns:
        Path to the written settings.json file.
    """
    return _generate_worker_settings(feature, bob3_dir=bob3_dir, extra_allow=extra_allow)


__all__ = ["generate_worker_settings"]
