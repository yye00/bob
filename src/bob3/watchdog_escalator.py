"""Watchdog escalator — canonical entry-point for spec_gate_stall escalation.

Feature b6f360f6-a0f9-450b-ac15-5dc1b02728c1

After N consecutive spec_gate_stall_observed events (default 5, configurable
via BOB3_STALL_ESCALATION_COUNT), escalate to a needs_human_attention sentinel:
  - Write a HALT_ATTENTION marker file (bob4/tools/STALL_ATTENTION.txt by default).
  - Emit a structured chain_dead_locked event at WARN level.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.watchdog import escalate_stall_observation

__all__ = ["escalate_spec_gate_stalls", "escalate_stall_observations"]


def escalate_spec_gate_stalls(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Escalate repeated spec_gate_stall_observed events to a needs_human_attention sentinel.

    After observation_count reaches BOB3_STALL_ESCALATION_COUNT (default 5):
      - Writes a HALT_ATTENTION marker file at marker_path.
      - Logs a chain_dead_locked event at WARN level so monitoring greps
        that filter INFO noise still surface it.

    Parameters
    ----------
    observation_count:
        Number of consecutive spec_gate_stall_observed events seen so far.
        Must be >= 0; raises ValueError for negative values.
    marker_path:
        Destination for the HALT_ATTENTION marker file. Defaults to
        bob4/tools/STALL_ATTENTION.txt relative to CWD.

    Returns
    -------
    dict with keys:
        escalated (bool) — whether escalation fired this call.
        threshold (int) — the effective escalation threshold used.
        observation_count (int) — the value passed in.
        marker_path (str) — the resolved marker path (absolute).

    Raises
    ------
    ValueError
        If observation_count is negative.
    """
    return escalate_stall_observation(
        observation_count=observation_count,
        marker_path=marker_path,
    )


def escalate_stall_observations(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Escalate repeated spec_gate_stall_observed events to a needs_human_attention sentinel.

    Canonical entry-point required by AC: bob3.watchdog_escalator.escalate_stall_observations.
    After observation_count reaches BOB3_STALL_ESCALATION_COUNT (default 5):
      - Writes a HALT_ATTENTION marker file at marker_path.
      - Logs a chain_dead_locked event at WARN level so monitoring greps
        that filter INFO noise still surface it.

    Parameters
    ----------
    observation_count:
        Number of consecutive spec_gate_stall_observed events seen so far.
        Must be >= 0; raises ValueError for negative values.
    marker_path:
        Destination for the HALT_ATTENTION marker file. Defaults to
        bob4/tools/STALL_ATTENTION.txt relative to CWD.

    Returns
    -------
    dict with keys:
        escalated (bool) — whether escalation fired this call.
        threshold (int) — the effective escalation threshold used.
        observation_count (int) — the value passed in.
        marker_path (str) — the resolved marker path (absolute).

    Raises
    ------
    ValueError
        If observation_count is negative.
    """
    return escalate_stall_observation(
        observation_count=observation_count,
        marker_path=marker_path,
    )
