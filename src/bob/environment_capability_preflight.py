"""Environment-capability preflight with research-driven workaround discovery.

At spec-load, enumerate every external dependency. Probe each via ``command -v``
for CLIs and ``python3 -c "import X"`` for modules. For each MISSING dep, spawn
a research sub-agent that surfaces a concrete workaround. Auto-apply when
low-risk; halt with operator-actionable error otherwise.

This module is the canonical entry point for the feature (F 0409c0bf).
It re-exports the full API from ``bob.preflight`` so that both
``bob.environment_capability_preflight.*`` and the orchestrator integration
work via a single underlying implementation.
"""

from __future__ import annotations

from bob.preflight import (  # noqa: F401
    MissingDependencyError,
    apply_workaround,
    check_environment_capabilities,
    discover_workaround,
    discover_workarounds,
    enumerate_dependencies,
    probe_dependencies,
    probe_dependency,
    run_preflight,
    spawn_workaround_research,
)


def probe_dependencies(ac_list):  # noqa: F811  # explicit re-export with same signature
    """Enumerate and probe all external dependencies from a list of acceptance criteria.

    Combines enumerate_dependencies and probe_dependency into a single call:
    scans *ac_list* for CLI and Python module references, then probes each
    to determine availability.

    Args:
        ac_list: List of acceptance criteria strings. May be empty.

    Returns:
        A list of probe-result dicts (each with ``dep``, ``present``, ``path``).
        Returns an empty list when ac_list is empty or no deps are found.

    Raises:
        ValueError: If ac_list is not a list.
    """
    from bob.preflight import probe_dependencies as _probe_dependencies
    return _probe_dependencies(ac_list)


def discover_workaround(probe_result):  # noqa: F811  # explicit re-export
    """Discover a concrete workaround for a missing dep by spawning a research sub-agent.

    When a dependency is present, returns None. When missing, returns a workaround
    dict with keys: dep_name, description, low_risk, commands.

    Args:
        probe_result: A probe-result dict as returned by probe_dependency.

    Returns:
        A workaround dict or None if the dep is already present.

    Raises:
        ValueError: If probe_result is not a dict or is missing required keys.
    """
    from bob.preflight import spawn_workaround_research
    return spawn_workaround_research(probe_result)


__all__ = [
    "MissingDependencyError",
    "enumerate_dependencies",
    "probe_dependency",
    "probe_dependencies",
    "discover_workaround",
    "discover_workarounds",
    "spawn_workaround_research",
    "apply_workaround",
    "check_environment_capabilities",
    "run_preflight",
]
