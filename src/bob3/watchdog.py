"""Bob3 watchdog utilities for stall detection and escalation.

Provides escalate_stall_observation and escalate_stall_to_needs_human_attention:
canonical public entry-points for escalating repeated spec_gate_stall_observed
events to a needs_human_attention sentinel (HALT_ATTENTION marker file +
WARN-level chain_dead_locked log event).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.watchdog_must_escalate_repeated_spec_gate_stall_observed import (
    watchdog_must_escalate_repeated_spec_gate_stall_observed as _escalate_impl,
)

_DEFAULT_MARKER_PATH = Path("bob4") / "tools" / "STALL_ATTENTION.txt"

__all__ = ["escalate_spec_gate_stall", "escalate_stall_observation", "escalate_stall_to_needs_human_attention"]


def escalate_spec_gate_stall(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Escalate repeated spec_gate_stall_observed events to needs_human_attention.

    Canonical entry-point named for the feature AC requirement.  After
    observation_count reaches BOB3_STALL_ESCALATION_COUNT (default 5):
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


def escalate_stall_observation(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Escalate repeated spec_gate_stall_observed events to a sentinel.

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
    if observation_count < 0:
        raise ValueError(
            f"observation_count must be >= 0, got {observation_count!r}"
        )
    if marker_path is None:
        marker_path = _DEFAULT_MARKER_PATH
    return _escalate_impl(
        observation_count=observation_count,
        marker_path=marker_path,
    )


def escalate_stall_to_needs_human_attention(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Escalate repeated spec_gate_stall_observed events to needs_human_attention.

    Alias for escalate_stall_observation with the canonical name matching the
    needs_human_attention sentinel pattern described in the feature spec.

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
