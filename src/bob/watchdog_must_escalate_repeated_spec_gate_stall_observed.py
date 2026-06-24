"""Watchdog escalation for repeated spec_gate_stall_observed events.

Feature 21e7c6f5-0435-4bc2-862a-1724f4e19232

After N consecutive spec_gate_stall_observed events (default 5, overridable via
BOB_STALL_ESCALATION_COUNT), escalate to a needs_human_attention sentinel:
  - Write a HALT_ATTENTION marker file (bob4/tools/STALL_ATTENTION.txt by default).
  - Emit a structured chain_dead_locked event at WARN level.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_ESCALATION_COUNT = 5

__all__ = ["watchdog_must_escalate_repeated_spec_gate_stall_observed"]


def _read_escalation_threshold() -> int:
    raw = os.environ.get("BOB_STALL_ESCALATION_COUNT")
    if not raw:
        return _DEFAULT_ESCALATION_COUNT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_ESCALATION_COUNT
    return value if value > 0 else _DEFAULT_ESCALATION_COUNT


def watchdog_must_escalate_repeated_spec_gate_stall_observed(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate stall observation count and escalate when threshold is reached.

    If observation_count >= threshold:
      - Writes a HALT_ATTENTION marker file at marker_path.
      - Logs a chain_dead_locked event at WARN level.

    Returns a dict with keys: escalated, threshold, observation_count, marker_path.
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
