"""Watchdog stall escalation — public entry-point module.

Feature b4d1f1f3-639e-4abe-89a4-350a1d3006a4

After N consecutive spec_gate_stall_observed events (default 5, configurable
via BOB_STALL_ESCALATION_COUNT), escalate to a needs_human_attention sentinel:
  - Write a HALT_ATTENTION marker file (bob4/tools/STALL_ATTENTION.txt by default).
  - Emit a structured chain_dead_locked event at WARN level so monitoring
    greps that filter out INFO noise still surface it.

Public API
----------
escalate_repeated_stall_observations
    Evaluate whether the stall observation count crosses the escalation
    threshold; if so, write the marker and emit the WARN log.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from bob.watchdog import escalate_stall_observation as _escalate_stall_observation

logger = logging.getLogger(__name__)

_DEFAULT_ESCALATION_COUNT = 5

__all__ = [
    "escalate_repeated_stall_observations",
    "escalate_stall_observation",
    "write_stall_attention_marker",
]


def _read_escalation_threshold() -> int:
    raw = os.environ.get("BOB_STALL_ESCALATION_COUNT")
    if not raw:
        return _DEFAULT_ESCALATION_COUNT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_ESCALATION_COUNT
    return value if value > 0 else _DEFAULT_ESCALATION_COUNT


def write_stall_attention_marker(
    marker_path: Path,
    *,
    observation_count: int,
    threshold: int,
) -> None:
    """Write a HALT_ATTENTION marker file and log a chain_dead_locked WARN event.

    Parameters
    ----------
    marker_path:
        Destination path for the HALT_ATTENTION marker file.
    observation_count:
        Number of consecutive spec_gate_stall_observed events that triggered escalation.
    threshold:
        The escalation threshold that was crossed.
    """
    marker_path = Path(marker_path)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        f"chain_dead_locked: {observation_count} consecutive spec_gate_stall_observed events "
        f"(threshold={threshold}). Operator action required: drop thresholds and manually relaunch.\n"
    )
    logger.warning(
        "chain_dead_locked: %d consecutive spec_gate_stall_observed events reached "
        "escalation threshold=%d; wrote HALT_ATTENTION marker at %s",
        observation_count,
        threshold,
        marker_path,
    )


def escalate_stall_observation(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Escalate repeated spec_gate_stall_observed events to a needs_human_attention sentinel.

    After observation_count reaches BOB_STALL_ESCALATION_COUNT (default 5):
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
    return _escalate_stall_observation(
        observation_count=observation_count,
        marker_path=marker_path,
    )


def escalate_repeated_stall_observations(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Escalate repeated spec_gate_stall_observed events to a needs_human_attention sentinel.

    After observation_count reaches BOB_STALL_ESCALATION_COUNT (default 5):
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
