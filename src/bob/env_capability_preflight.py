"""Environment-capability preflight with research-driven workaround discovery.

At spec-load, enumerate every external dependency. Probe each via ``command -v``
for CLIs and ``python3 -c "import X"`` for modules. For each MISSING dep, spawn
a research sub-agent that surfaces a concrete workaround. Auto-apply when
low-risk; halt with an operator-actionable error otherwise.

This module is the canonical entry point for feature 9cea2d12. It re-exports the
full API from :mod:`bob.preflight` so both ``bob.env_capability_preflight.*`` and
the orchestrator integration share a single underlying implementation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bob.preflight import (
    MissingDependencyError,
    apply_workaround,
    check_environment_capabilities,
    discover_workarounds,
    enumerate_dependencies,
    probe_dependency,
    run_preflight,
    spawn_workaround_research,
)


def probe_dependencies(ac_list: List[str]) -> List[Dict[str, Any]]:
    """Enumerate and probe all external dependencies from acceptance criteria.

    Scans *ac_list* for CLI and Python module references, then probes each to
    determine availability.

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


def discover_workaround(probe_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Discover a concrete workaround for a missing dep via a research sub-agent.

    When the dependency is present, returns None. When missing, returns a
    workaround dict with keys ``dep_name``, ``description``, ``low_risk``,
    ``commands``.

    Args:
        probe_result: A probe-result dict as returned by :func:`probe_dependency`.

    Returns:
        A workaround dict, or None if the dep is already present.

    Raises:
        ValueError: If probe_result is not a dict or is missing required keys.
    """
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
