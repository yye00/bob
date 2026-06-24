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

__all__ = [
    "DepInventory",
    "HaltOnMissingDepError",
    "ProbeResult",
    "SilentSkipForbiddenError",
    "Workaround",
    "apply_or_halt",
    "discover_workaround",
    "enumerate_deps",
    "persist_applied_workarounds",
    "probe",
    "run_preflight",
    "spawns_research_subagent",
]
