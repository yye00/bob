"""Startup checks for bob3 run_loop initialization.

This module provides the canonical startup verification entrypoint for bob3.
It is called at run_loop startup to detect and correct stale project metadata
left by spawn_next_generation.sh rsync-copying the parent DB without re-running
``bob3 init``.
"""

from __future__ import annotations

from bob3.run_loop import ProjectMetadataCheckResult, verify_project_metadata

__all__ = [
    "ProjectMetadataCheckResult",
    "verify_project_metadata",
]
