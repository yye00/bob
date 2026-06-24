"""Facade for environment-capability preflight with research-driven workaround discovery.

At spec-load, enumerate every external dependency. Probe each via ``command -v``
for CLIs and ``python3 -c "import X"`` for modules. For each MISSING dep, spawn
a research sub-agent that surfaces a concrete workaround. Auto-apply when
low-risk; halt with operator-actionable error otherwise.
"""

from __future__ import annotations

import pathlib
from typing import Any, List, Optional

from bob.orchestrator.env_preflight import run_preflight


def environment_capability_preflight_research_driven_workaround_discovery(
    ac_list: List[str],
    round_num: int = 0,
    workspace: Optional[pathlib.Path] = None,
) -> dict[str, Any]:
    """Run environment-capability preflight with research-driven workaround discovery.

    Enumerates every external dependency declared in the acceptance criteria,
    probes each one, discovers workarounds for missing deps via research
    sub-agents, auto-applies low-risk workarounds, and halts with an
    operator-actionable error for high-risk missing deps.

    Args:
        ac_list: List of acceptance criteria strings to enumerate deps from.
        round_num: Current orchestration round number (used for persistence path).
        workspace: Project root directory; defaults to current working directory.

    Returns:
        A summary dict with keys:
        - total_deps: total number of deps enumerated
        - missing: list of dep names that were not found
        - applied_workarounds: list of dep names that had workarounds applied
        - halted: always False (raises on unresolvable deps instead)
    """
    return run_preflight(ac_list, round_num=round_num, workspace=workspace)
