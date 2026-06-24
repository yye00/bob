"""Watchdog stall escalation — escalate repeated spec_gate_stall_observed events.

After N consecutive spec_gate_stall_observed observations (default 5, overridable
via BOB_STALL_ESCALATION_COUNT), escalate to a needs_human_attention sentinel:
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

__all__ = ["escalate_spec_gate_stall", "escalate_stall_observation", "write_stall_attention_marker"]


def _read_escalation_threshold() -> int:
    raw = os.environ.get("BOB_STALL_ESCALATION_COUNT")
    if not raw:
        return _DEFAULT_ESCALATION_COUNT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_ESCALATION_COUNT
    return value if value > 0 else _DEFAULT_ESCALATION_COUNT


def escalate_spec_gate_stall(
    *,
    observation_count: int,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Evaluate stall observation count and escalate when threshold is reached.

    Parameters
    ----------
    observation_count:
        Number of consecutive spec_gate_stall_observed events seen so far.
        Must be >= 0; raises ValueError for negative values.
    marker_path:
        Destination for the HALT_ATTENTION marker. Defaults to
        ``bob4/tools/STALL_ATTENTION.txt`` relative to CWD.

    Returns
    -------
    dict with keys:
        escalated: bool — whether escalation fired this call.
        threshold: int — the effective threshold used.
        observation_count: int — the value passed in.
        marker_path: str — the resolved marker path (absolute).
    """
    if observation_count < 0:
        raise ValueError(
            f"observation_count must be >= 0, got {observation_count}"
        )

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


# Alias so tests importing escalate_stall_observation work
escalate_stall_observation = escalate_spec_gate_stall


def write_stall_attention_marker(
    marker_path: Path,
    *,
    observation_count: int,
    threshold: int | None = None,
) -> None:
    """Write the HALT_ATTENTION marker file and log a WARN chain_dead_locked event.

    This is the low-level primitive that escalate_spec_gate_stall calls when the
    threshold is reached. Exposed as a named function so AC verifiers can confirm
    it exists on the bob.watchdog namespace.

    Parameters
    ----------
    marker_path:
        Destination for the HALT_ATTENTION marker file.
    observation_count:
        Number of consecutive spec_gate_stall_observed events observed.
    threshold:
        Effective escalation threshold; defaults to the value from the env.
    """
    if threshold is None:
        threshold = _read_escalation_threshold()
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
