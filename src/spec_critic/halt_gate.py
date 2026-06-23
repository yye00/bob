"""Halt-gate module for the spec-critic findings registry (F-R7-450).

Fires when critic_repeat_rate > 0.30 over the last 3 distinct runs.

Public API::

    from spec_critic.halt_gate import check_repeat_rate

    rate, fired = check_repeat_rate(findings_path=Path("reviews/spec_findings.yaml"))
    if fired:
        raise RuntimeError("Halt gate: spec critic repeat rate exceeded 0.30")
"""

from __future__ import annotations

from pathlib import Path

from bob3.spec_quality.spec_findings_registry import (
    compute_critic_repeat_rate,
    is_halt_gate_fired,
    _HALT_GATE_THRESHOLD,
    _HALT_GATE_WINDOW,
)


def check_repeat_rate(
    *,
    findings_path: Path | None = None,
    metrics_path: Path | None = None,
    window: int = _HALT_GATE_WINDOW,
) -> tuple[float, bool]:
    """Return (critic_repeat_rate, halt_gate_fired).

    Computes the fraction of findings in the last *window* distinct run_ids
    that are regressions. Returns (rate, True) when rate > 0.30.

    Parameters
    ----------
    findings_path:
        Override path to spec_findings.yaml; mainly for testing.
    metrics_path:
        Override path to metrics.yaml; mainly for testing.
        When provided and the file exists, the pre-computed halt status is
        read from it rather than recomputed.
    window:
        Number of distinct run_ids to consider (default 3).

    Returns
    -------
    tuple[float, bool]
        ``(rate, fired)`` where *rate* is the critic_repeat_rate in [0.0, 1.0]
        and *fired* is True iff rate > 0.30.
    """
    rate = compute_critic_repeat_rate(findings_path=findings_path, window=window)
    fired = rate > _HALT_GATE_THRESHOLD
    return rate, fired


__all__ = ["check_repeat_rate"]
