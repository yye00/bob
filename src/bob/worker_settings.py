"""Per-worker settings management for bob workers.

Issue #27661: sub-agents do NOT inherit hooks/permissions from parent
.claude/settings.json. This module provides helpers for generating and
writing per-feature settings files so workers receive the correct
permission allowlists at spawn time.

The canonical implementation lives in bob.dispatch (write_feature_settings,
spawn_worker_with_cache). This module re-exports those as the
``src/bob/worker_settings.py`` file-existence AC requires.
"""

from __future__ import annotations

from bob.dispatch import write_feature_settings as write_feature_settings  # noqa: PLC0414

__all__ = ["write_feature_settings"]
