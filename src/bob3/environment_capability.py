"""Environment-capability preflight with research-driven workaround discovery.

At spec-load, enumerate every external dependency. Probe each via ``command -v``
for CLIs and ``python3 -c "import X"`` for modules. For each MISSING dep, spawn
a research sub-agent that surfaces a concrete workaround. Auto-apply when
low-risk; halt with operator-actionable error otherwise.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bob72.preflight import (
    MissingDependencyError,
    discover_workaround as _discover_workaround,
    probe_dependencies as _probe_dependencies,
    run_preflight,
)
from bob3.skill_library import (
    search_skill_by_similarity,
    write_skill_to_library,
    apply_skill,
)

__all__ = [
    "MissingDependencyError",
    "probe_dependencies",
    "discover_workaround",
    "run_preflight",
    "search_skill_by_similarity",
    "write_skill_to_library",
    "apply_skill",
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
    return _probe_dependencies(ac_list)


def discover_workaround(probe_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Discover a concrete workaround for a missing dependency.

    Simulates spawning a research sub-agent that surfaces installation or
    emulation strategies. Python module workarounds are marked ``low_risk=True``
    (pip install). CLI workarounds are ``low_risk=False`` and require operator
    action.

    Args:
        probe_result: A dict as returned by an element of ``probe_dependencies``.
            Must have ``dep`` and ``present`` keys.

    Returns:
        A workaround dict with keys ``dep_name``, ``description``, ``low_risk``,
        ``commands``; or None if the dependency is already present.

    Raises:
        ValueError: If *probe_result* is not a dict or is missing required keys.
    """
    return _discover_workaround(probe_result)
