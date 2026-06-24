"""Watchdog escalation module for repeated spec_gate_stall_observed events.

Feature 7f1288b8-cbfc-4b70-87d2-4d806d86a19f

Public surface for escalating repeated spec_gate_stall_observed events to a
needs_human_attention sentinel after N consecutive observations (default 5,
configurable via BOB3_STALL_ESCALATION_COUNT).

Escalation:
  - Writes a HALT_ATTENTION marker file (bob4/tools/STALL_ATTENTION.txt by default).
  - Emits a structured chain_dead_locked event at WARN level.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.watchdog import escalate_stall_observation

__all__ = ["escalate_stall_to_attention", "escalate_stall_to_needs_human_attention", "write_halt_attention_marker"]

_DEFAULT_MARKER_PATH = Path("bob4") / "tools" / "STALL_ATTENTION.txt"


def write_halt_attention_marker(marker_path: Path | None = None) -> Path:
    """Write the HALT_ATTENTION marker file and return the resolved path.

    Creates parent directories as needed.
    """
    if marker_path is None:
        marker_path = _DEFAULT_MARKER_PATH
    marker_path = Path(marker_path)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        "chain_dead_locked: repeated spec_gate_stall_observed events. "
        "Operator action required: drop thresholds and manually relaunch.\n"
    )
    return marker_path.resolve()


def escalate_stall_to_needs_human_attention(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Escalate repeated spec_gate_stall_observed events to needs_human_attention sentinel.

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


def escalate_stall_to_attention(
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
