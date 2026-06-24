"""Per-feature settings and WORKER.md generation for Claude-Code worker dispatch.

Workers do NOT inherit hooks/permissions from the parent settings.json
(Claude Code issue #27661). This module provides write_worker_config,
the canonical entry point for generating both the per-feature settings.json
and the slim WORKER.md at dispatch time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bob.dispatch import (
    build_worker_md,
    write_feature_settings,
)


def write_worker_config(
    feature: Any,
    *,
    bob_dir: str | Path,
    workspace: str | Path | None = None,
    extra_allow: list[str] | None = None,
) -> dict[str, Path]:
    """Write per-feature settings.json and WORKER.md for a Claude-Code worker.

    Workers do NOT inherit hooks/permissions from the parent settings.json
    (Issue #27661), so settings must be declared per-worker at dispatch time.
    This function writes both artifacts needed before spawning a worker:

    1. ``.bob/features/<id>/settings.json`` — permission allowlist for the worker.
    2. ``.bob/features/WORKER.md`` — slim per-feature context (feature title,
       description, ACs, localization shortlist, workspace path).

    Args:
        feature:     Feature object; ``feature.id`` is used as the directory name.
        bob_dir:    Path to the .bob directory (project-level).
        workspace:   Project workspace path (used for WORKER.md). If None,
                     defaults to the parent of bob_dir.
        extra_allow: Additional allow patterns merged with project defaults.

    Returns:
        Dict with keys ``settings`` (Path to settings.json) and ``worker_md``
        (Path to WORKER.md).

    Raises:
        ValueError: If feature is None.
    """
    if feature is None:
        raise ValueError("feature must not be None")

    bob_dir = Path(bob_dir)

    if workspace is None:
        workspace = bob_dir.parent

    settings_path = write_feature_settings(
        feature, bob_dir=bob_dir, extra_allow=extra_allow
    )

    worker_md_content = build_worker_md(feature, workspace)
    worker_md_path = bob_dir / "features" / "WORKER.md"
    worker_md_path.parent.mkdir(parents=True, exist_ok=True)
    worker_md_path.write_text(worker_md_content)

    return {
        "settings": settings_path,
        "worker_md": worker_md_path,
    }


__all__ = ["write_worker_config"]
