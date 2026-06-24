"""Watchdog escalation for repeated spec_gate_stall_observed events.

Feature 1c71893f-b668-47f0-8f62-8e4d05b5f1b9

Problem: the watchdog emitted spec_gate_stall_observed as an INFO event every
60 s during a chain dead-lock, but monitoring greps filtered it out, so
~3h of wall time was lost silently (bob version 13 r10, 2026-05-28).

Fix: after N consecutive stall observations (default 5, overridable via
BOB_STALL_ESCALATION_COUNT), escalate to a distinct needs_human_attention
sentinel:
  - Write a HALT_ATTENTION marker file (bob4/tools/STALL_ATTENTION.txt by
    default, but callers may pass any path).
  - Emit a structured chain_dead_locked event at WARN level so monitoring
    greps that filter out INFO noise still surface it.

Public API
----------
watchdog_must_escalate_repeated_spec_gate_stall_observed_needs_human_attention_sentinel_silent_60s_log_spam_masks_chain_dead_lock
    Evaluate whether the current stall observation count crosses the escalation
    threshold and, if so, write the marker and emit the WARN log.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_ESCALATION_COUNT = 5

__all__ = [
    "watchdog_must_escalate_repeated_spec_gate_stall_observed_needs_human_attention_sentinel_silent_60s_log_spam_masks_chain_dead_lock",
]


def _read_escalation_threshold() -> int:
    """Return BOB_STALL_ESCALATION_COUNT as int, or _DEFAULT_ESCALATION_COUNT."""
    raw = os.environ.get("BOB_STALL_ESCALATION_COUNT")
    if not raw:
        return _DEFAULT_ESCALATION_COUNT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_ESCALATION_COUNT
    return value if value > 0 else _DEFAULT_ESCALATION_COUNT


def watchdog_must_escalate_repeated_spec_gate_stall_observed_needs_human_attention_sentinel_silent_60s_log_spam_masks_chain_dead_lock(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate stall observation count and escalate when threshold is reached.

    If ``observation_count`` >= threshold:
      - Writes a HALT_ATTENTION marker file at *marker_path* (creating parent
        directories as needed).
      - Logs a structured ``chain_dead_locked`` event at WARN level.

    If below threshold: no side effects.

    Parameters
    ----------
    observation_count:
        Number of consecutive spec_gate_stall_observed events seen so far.
    marker_path:
        Destination for the HALT_ATTENTION marker.  Defaults to
        ``bob4/tools/STALL_ATTENTION.txt`` relative to CWD.

    Returns
    -------
    dict with keys:
        escalated: bool — whether escalation fired this call.
        threshold: int — the effective threshold used.
        observation_count: int — the value passed in.
        marker_path: str — the resolved marker path (absolute).
    """
    threshold = _read_escalation_threshold()

    if marker_path is None:
        marker_path = Path("bob4") / "tools" / "STALL_ATTENTION.txt"

    marker_path = Path(marker_path)

    if observation_count >= threshold:
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
        return {
            "escalated": True,
            "threshold": threshold,
            "observation_count": observation_count,
            "marker_path": str(marker_path.resolve()),
        }

    return {
        "escalated": False,
        "threshold": threshold,
        "observation_count": observation_count,
        "marker_path": str(marker_path.resolve()),
    }
