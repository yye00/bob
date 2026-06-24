"""Environment-capability preflight for bob73.

Enumerates external dependencies from acceptance criteria, probes each
for availability, and applies workarounds or raises actionable errors.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bob72.preflight import (
    MissingDependencyError,
    discover_workaround,
    probe_dependencies as _probe_dependencies_impl,
    run_preflight,
)

__all__ = [
    "MissingDependencyError",
    "probe_dependencies",
    "apply_workaround",
    "run_preflight",
]


def probe_dependencies(ac_list: List[str]) -> List[Dict[str, Any]]:
    """Probe all external dependencies inferred from acceptance criteria.

    Enumerates every external dependency from *ac_list* (CLIs and Python
    modules), then probes each for availability via ``shutil.which`` or
    ``python3 -c "import X"``.

    Args:
        ac_list: List of acceptance criteria strings. May be empty.

    Returns:
        A list of probe-result dicts, each with keys:
        - ``dep``: ``{"kind": "cli"|"python", "name": str}``
        - ``present``: bool
        - ``path``: resolved path string or None

    Raises:
        ValueError: If *ac_list* is not a list.
    """
    return _probe_dependencies_impl(ac_list)


def apply_workaround(probe_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Discover and classify a workaround for a missing dependency.

    Simulates spawning a research sub-agent to surface installation or
    emulation strategies. Low-risk workarounds (Python pip installs) can be
    auto-applied; high-risk ones require operator action.

    Args:
        probe_result: A dict as returned by an element of ``probe_dependencies``.
            Must have ``dep`` and ``present`` keys.

    Returns:
        A workaround dict with keys ``dep_name``, ``description``, ``low_risk``,
        ``commands``; or None if the dependency is already present.

    Raises:
        ValueError: If *probe_result* is not a dict or is missing required keys.
    """
    return discover_workaround(probe_result)
