"""Watchdog stall escalator — escalate spec_gate_stall_observed to needs_human_attention.

After N consecutive spec_gate_stall_observed events (default 5, overridable via
BOB3_STALL_ESCALATION_COUNT env), escalate to a needs_human_attention sentinel:
  - Write a HALT_ATTENTION marker file (bob4/tools/STALL_ATTENTION.txt by default).
  - Emit a structured chain_dead_locked event at WARN level.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.watchdog import escalate_stall_observation

__all__ = ["escalate_spec_gate_stall"]


def escalate_spec_gate_stall(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Escalate repeated spec_gate_stall_observed events to needs_human_attention.

    After observation_count reaches BOB3_STALL_ESCALATION_COUNT (default 5):
      - Writes a HALT_ATTENTION marker file at marker_path.
      - Logs a chain_dead_locked event at WARN level.

    Parameters
    ----------
    observation_count:
        Number of consecutive spec_gate_stall_observed events seen so far.
        Must be >= 0; raises ValueError for negative values.
    marker_path:
        Destination for the HALT_ATTENTION marker.  Defaults to
        bob4/tools/STALL_ATTENTION.txt relative to CWD.

    Returns
    -------
    dict with keys: escalated (bool), threshold (int),
                    observation_count (int), marker_path (str).

    Raises
    ------
    ValueError
        If observation_count is negative.
    """
    return escalate_stall_observation(
        observation_count=observation_count,
        marker_path=marker_path,
    )
