"""Repo-tree prompt injection for worker-spawn path (F-R7-609 component A).

Provides the canonical public API for prepending a capped directory tree
to a worker prompt before spawning. Delegates to bob3.dispatch internals
so the dispatch module remains the single authoritative implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.dispatch import (
    build_repo_tree,
    inject_repo_tree_into_prompt,
    inject_repo_tree_to_worker,
)

__all__ = [
    "build_repo_tree",
    "inject_repo_tree_into_prompt",
    "inject_repo_tree_to_worker",
]
