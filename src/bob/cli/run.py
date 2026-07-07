"""Integration wiring: env_preflight into the bob CLI run command.

This module is imported by bob.cli at startup, ensuring that the
environment-capability preflight runs before any sub-agent is spawned.
"""

from __future__ import annotations

from bob.orchestrator.env_preflight import (  # noqa: F401
    DepInventory,
    HaltOnMissingDepError,
    ProbeResult,
    SilentSkipForbiddenError,
    Workaround,
    apply_or_halt,
    discover_workaround,
    enumerate_deps,
    persist_applied_workarounds,
    probe,
    run_preflight,
    spawns_research_subagent,
)

# Feature 27e4c777 — the unattended-build supervisor. `bob run --all` calls
# supervise_run() at a would-be QUEUE_DRAINED exit so the build auto-resumes
# (resetting recoverable transient-failed siblings) instead of halting until a
# human re-runs.
from bob.supervisor_loop import (  # noqa: F401
    ResumeDecision,
    auto_resume_run,
    supervise_run,
)

__all__ = [
    "DepInventory",
    "HaltOnMissingDepError",
    "ProbeResult",
    "ResumeDecision",
    "SilentSkipForbiddenError",
    "Workaround",
    "apply_or_halt",
    "auto_resume_run",
    "discover_workaround",
    "enumerate_deps",
    "persist_applied_workarounds",
    "probe",
    "run_preflight",
    "spawns_research_subagent",
    "supervise_run",
]
