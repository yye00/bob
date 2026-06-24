"""orchestrator.reaper — re-exports sweep_orphan_subagents from bob.orchestrator.

Satisfies the AC requiring ``orchestrator.reaper.sweep_orphan_subagents``
(feature 230dac5a: final reaper sweep on orchestrator exit).
"""

from __future__ import annotations

from bob.orchestrator.subagent_reaper import sweep_orphan_subagents  # noqa: F401

__all__ = ["sweep_orphan_subagents"]
