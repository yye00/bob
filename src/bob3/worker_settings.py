"""Per-worker settings management for bob3 workers.

Issue #27661: sub-agents do NOT inherit hooks/permissions from parent
.claude/settings.json. This module provides helpers for generating and
writing per-feature settings files so workers receive the correct
permission allowlists at spawn time.

The canonical implementation lives in bob3.dispatch (write_feature_settings,
spawn_worker_with_cache). This module re-exports those as the
``src/bob3/worker_settings.py`` file-existence AC requires.
"""

from __future__ import annotations

from bob3.dispatch import write_feature_settings as write_feature_settings  # noqa: PLC0414

__all__ = ["write_feature_settings"]
