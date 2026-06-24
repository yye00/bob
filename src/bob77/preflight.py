"""bob77 environment-capability preflight with Voyager-style skill library.

Extends bob73.preflight by exposing the skill library search as
``bob77.preflight.search_skill_library`` and re-exporting ``run_preflight``
and companion helpers from bob73.

The bob77-generation API is:
- ``retrieve_by_similarity`` (via bob77.skill_library) — search before research.
- ``persist_skill`` (via bob77.skill_library) — write back after discovery.
- ``search_skill_library`` — alias exposed here for direct preflight integration.
- ``run_preflight`` — full preflight pipeline (delegates to bob72 via bob73).

Integration: callers import from ``bob77.preflight`` directly; this module is
the canonical integration point for the bob77 generation's env preflight.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

from bob73.preflight import (
    MissingDependencyError,
    discover_workaround,
    probe_dependencies,
    run_preflight as _bob73_run_preflight,
    search_skill_library as _bob73_search_skill_library,
)

__all__ = [
    "MissingDependencyError",
    "probe_dependencies",
    "discover_workaround",
    "search_skill_library",
    "run_preflight",
]


def search_skill_library(
    capability_query: str,
    workspace: Optional[pathlib.Path] = None,
    context: Optional[dict] = None,
    threshold: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Search the persistent skill library for an existing workaround shim.

    Thin wrapper around ``bob73.preflight.search_skill_library`` exposed as
    ``bob77.preflight.search_skill_library`` for the bob77 generation.

    Called during env preflight BEFORE spawning a research sub-agent. Returns
    a result dict on hit, ``None`` on miss.

    Args:
        capability_query: Natural-language description of the needed capability.
        workspace: Project root directory; defaults to current working directory.
        context: Optional dict passed to the shim's apply() function.
        threshold: Minimum cosine similarity; defaults to 0.75.

    Returns:
        Dict with keys ``"hit"``, ``"apply_result"``, ``"research_needed": False``
        on hit; ``None`` on miss.

    Raises:
        ValueError: If ``capability_query`` is not a non-empty string.
    """
    return _bob73_search_skill_library(
        capability_query=capability_query,
        workspace=workspace,
        context=context,
        threshold=threshold,
    )


def run_preflight(
    ac_list: List[str],
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full preflight pipeline with skill-library integration.

    Delegates to bob73.preflight.run_preflight (which in turn delegates to
    bob72.preflight). The skill library search hook is exposed via
    search_skill_library for callers that run preflight step-by-step.

    Args:
        ac_list: List of acceptance criteria strings. May be empty.
        workspace: Optional project root path.

    Returns:
        A summary dict with keys total_deps, missing, applied_workarounds, halted.

    Raises:
        ValueError: If ac_list is not a list.
        MissingDependencyError: If a high-risk dep cannot be resolved.
    """
    return _bob73_run_preflight(ac_list=ac_list, workspace=workspace)
