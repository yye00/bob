"""Startup checks for bob run_loop initialization.

This module provides the canonical startup verification entrypoint for bob.
It is called at run_loop startup to detect and correct stale project metadata
left by spawn_next_generation.sh rsync-copying the parent DB without re-running
``bob init``.
"""

from __future__ import annotations

from bob.run_loop import ProjectMetadataCheckResult, verify_project_metadata

__all__ = [
    "ProjectMetadataCheckResult",
    "verify_project_metadata",
]
