"""Environment-capability preflight with research-driven workaround discovery.

At spec-load, enumerate every external dependency. Probe each via ``command -v``
for CLIs and ``python3 -c "import X"`` for modules. For each MISSING dep, spawn
a research sub-agent that surfaces a concrete workaround. Auto-apply when
low-risk; halt with operator-actionable error otherwise.

Public API::

    from environment_capability import probe_dependencies, discover_workaround
    from environment_capability import run_preflight, MissingDependencyError
"""

from __future__ import annotations

from bob72.preflight import (
    MissingDependencyError,
    discover_workaround,
    probe_dependencies,
    run_preflight,
)

__all__ = [
    "MissingDependencyError",
    "discover_workaround",
    "probe_dependencies",
    "run_preflight",
]
