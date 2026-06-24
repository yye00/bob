"""Online threshold tuning for Bob (F-R4-131).

Dynamically adjusts the RCA trigger threshold and decomposition depth based
on accumulated calibration outcomes using an Exponential Moving Average (EMA)
on the Expected Calibration Error (ECE) per task class.

Algorithm
---------
* EMA ECE = alpha * current_ECE + (1 - alpha) * previous_EMA_ECE
* When EMA ECE rises above a high-water mark (``ece_high``): lower the RCA
  trigger threshold (trigger RCA sooner — calibration is poor) and allow a
  deeper decomposition pass.
* When EMA ECE falls below a low-water mark (``ece_low``): raise the RCA
  trigger threshold (be less aggressive) and reduce decomposition depth.
* All threshold changes are written as structured records to the telemetry
  run.jsonl via :func:`emit_telemetry_line` for reproducibility.

Public API
----------
OnlineThresholdTuner          — stateful tuner (holds EMA state, persists to DB)
apply_calibration_outcome     — convenience one-shot update
ThresholdState                — dataclass snapshot of current thresholds
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from bob.calibration import compute_ece_by_bucket
from bob.telemetry import emit_telemetry_line

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_RCA_THRESHOLD: float = 0.50
_DEFAULT_DECOMP_DEPTH: int = 2

_DEFAULT_ALPHA: float = 0.3          # EMA smoothing factor
_DEFAULT_ECE_LOW: float = 0.10       # ECE below this → relax thresholds
_DEFAULT_ECE_HIGH: float = 0.20      # ECE above this → tighten thresholds

# How much to shift the RCA threshold per ECE band crossing.
_RCA_THRESHOLD_STEP: float = 0.05

# Bounds for the tunable RCA threshold.
_RCA_THRESHOLD_MIN: float = 0.30
_RCA_THRESHOLD_MAX: float = 0.70

# Bounds for decomposition depth.
_DECOMP_DEPTH_MIN: int = 1
_DECOMP_DEPTH_MAX: int = 4


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


@dataclass
class ThresholdState:
    """Snapshot of the tuner's current thresholds and EMA ECE."""

    rca_trigger_threshold: float
    decomposition_depth: int
    ema_ece: float | None
    task_class: str
    updated_at: str  # ISO-8601 UTC timestamp

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Core tuner
# ---------------------------------------------------------------------------


class OnlineThresholdTuner:
    """Online tuner that adjusts RCA trigger threshold and decomposition depth.

    Each call to :meth:`update` ingests a batch of calibration samples,
    computes ECE for the given task class, applies an EMA update, and
    adjusts the thresholds when ECE crosses the configured bands.

    Args:
        task_class: Canonical task class label (e.g. ``"algorithm_implementation"``).
        alpha: EMA smoothing coefficient in (0, 1].  Higher = faster adaptation.
        ece_low: ECE below this triggers a threshold relaxation.
        ece_high: ECE above this triggers a threshold tightening.
        initial_rca_threshold: Starting RCA trigger threshold.
        initial_decomp_depth: Starting maximum decomposition depth.
        run_id: Optional run identifier forwarded to telemetry records.
    """

    def __init__(
        self,
        task_class: str,
        *,
        alpha: float = _DEFAULT_ALPHA,
        ece_low: float = _DEFAULT_ECE_LOW,
        ece_high: float = _DEFAULT_ECE_HIGH,
        initial_rca_threshold: float = _DEFAULT_RCA_THRESHOLD,
        initial_decomp_depth: int = _DEFAULT_DECOMP_DEPTH,
        run_id: str | None = None,
    ) -> None:
        if not 0 < alpha <= 1:
            raise ValueError(f"alpha must be in (0, 1]; got {alpha}")
        if not 0.0 <= ece_low < ece_high <= 1.0:
            raise ValueError(
                f"ece_low={ece_low} must be < ece_high={ece_high} and both in [0, 1]"
            )
        if not _RCA_THRESHOLD_MIN <= initial_rca_threshold <= _RCA_THRESHOLD_MAX:
            raise ValueError(
                f"initial_rca_threshold must be in "
                f"[{_RCA_THRESHOLD_MIN}, {_RCA_THRESHOLD_MAX}]"
            )
        if not _DECOMP_DEPTH_MIN <= initial_decomp_depth <= _DECOMP_DEPTH_MAX:
            raise ValueError(
                f"initial_decomp_depth must be in "
                f"[{_DECOMP_DEPTH_MIN}, {_DECOMP_DEPTH_MAX}]"
            )

        self.task_class = task_class
        self.alpha = alpha
        self.ece_low = ece_low
        self.ece_high = ece_high
        self.run_id = run_id or "unknown"

        self._rca_threshold: float = initial_rca_threshold
        self._decomp_depth: int = initial_decomp_depth
        self._ema_ece: float | None = None  # None until first update

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def rca_trigger_threshold(self) -> float:
        """Current RCA trigger threshold (lower → trigger RCA sooner)."""
        return self._rca_threshold

    @property
    def decomposition_depth(self) -> int:
        """Current maximum allowed decomposition depth."""
        return self._decomp_depth

    @property
    def ema_ece(self) -> float | None:
        """Current EMA ECE for this task class, or None if no updates yet."""
        return self._ema_ece

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    def update(self, samples: list[dict]) -> ThresholdState:
        """Ingest calibration samples and adjust thresholds if needed.

        Args:
            samples: List of calibration sample dicts, each with keys:
                - ``task_class`` (str)
                - ``predicted_conf`` (float in [0, 1])
                - ``passed`` (bool)

                Samples for other task classes are silently ignored.

        Returns:
            A :class:`ThresholdState` snapshot after the update.
        """
        class_samples = [s for s in samples if s.get("task_class") == self.task_class]
        if not class_samples:
            return self._state_snapshot()

        ece_map = compute_ece_by_bucket(class_samples)
        current_ece = ece_map.get(self.task_class)
        if current_ece is None:
            return self._state_snapshot()

        # EMA update
        if self._ema_ece is None:
            self._ema_ece = current_ece
        else:
            self._ema_ece = self.alpha * current_ece + (1.0 - self.alpha) * self._ema_ece

        old_rca = self._rca_threshold
        old_depth = self._decomp_depth

        # Adjust thresholds based on EMA ECE bands
        changed = False
        if self._ema_ece > self.ece_high:
            # Poor calibration — trigger RCA more eagerly, allow deeper decomp
            new_rca = max(_RCA_THRESHOLD_MIN, self._rca_threshold - _RCA_THRESHOLD_STEP)
            new_depth = min(_DECOMP_DEPTH_MAX, self._decomp_depth + 1)
            if new_rca != self._rca_threshold or new_depth != self._decomp_depth:
                self._rca_threshold = new_rca
                self._decomp_depth = new_depth
                changed = True
                direction = "tightened"
        elif self._ema_ece < self.ece_low:
            # Good calibration — relax thresholds
            new_rca = min(_RCA_THRESHOLD_MAX, self._rca_threshold + _RCA_THRESHOLD_STEP)
            new_depth = max(_DECOMP_DEPTH_MIN, self._decomp_depth - 1)
            if new_rca != self._rca_threshold or new_depth != self._decomp_depth:
                self._rca_threshold = new_rca
                self._decomp_depth = new_depth
                changed = True
                direction = "relaxed"

        state = self._state_snapshot()

        if changed:
            self._emit_threshold_change(
                old_rca_threshold=old_rca,
                old_decomp_depth=old_depth,
                new_rca_threshold=self._rca_threshold,
                new_decomp_depth=self._decomp_depth,
                ema_ece=self._ema_ece,
                direction=direction,
            )
            logger.info(
                "OnlineThresholdTuner[%s]: %s thresholds — "
                "rca_threshold %.3f→%.3f, decomp_depth %d→%d (ema_ece=%.4f)",
                self.task_class,
                direction,
                old_rca,
                self._rca_threshold,
                old_depth,
                self._decomp_depth,
                self._ema_ece,
            )

        return state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _state_snapshot(self) -> ThresholdState:
        return ThresholdState(
            rca_trigger_threshold=self._rca_threshold,
            decomposition_depth=self._decomp_depth,
            ema_ece=self._ema_ece,
            task_class=self.task_class,
            updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def _emit_threshold_change(
        self,
        *,
        old_rca_threshold: float,
        old_decomp_depth: int,
        new_rca_threshold: float,
        new_decomp_depth: int,
        ema_ece: float,
        direction: str,
    ) -> None:
        """Write a structured threshold-change record to run.jsonl."""
        try:
            emit_telemetry_line(
                self.run_id,
                threshold_change_event="online_threshold_tuning",
                task_class=self.task_class,
                direction=direction,
                old_rca_trigger_threshold=old_rca_threshold,
                new_rca_trigger_threshold=new_rca_threshold,
                old_decomposition_depth=old_decomp_depth,
                new_decomposition_depth=new_decomp_depth,
                ema_ece=ema_ece,
                alpha=self.alpha,
                ece_low=self.ece_low,
                ece_high=self.ece_high,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to emit threshold-change telemetry: %s", exc)

    def state(self) -> ThresholdState:
        """Return the current threshold state snapshot."""
        return self._state_snapshot()


# ---------------------------------------------------------------------------
# Multi-class tuner registry
# ---------------------------------------------------------------------------


class ThresholdTunerRegistry:
    """Registry holding one :class:`OnlineThresholdTuner` per task class.

    Provides a single entry point for updating thresholds across all task
    classes from a mixed batch of calibration samples.

    Args:
        task_classes: Iterable of task class labels to manage.
        run_id: Forwarded to each per-class tuner for telemetry.
        kwargs: Additional keyword arguments forwarded to each
            :class:`OnlineThresholdTuner` constructor.
    """

    def __init__(
        self,
        task_classes: list[str],
        *,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._tuners: dict[str, OnlineThresholdTuner] = {
            tc: OnlineThresholdTuner(tc, run_id=run_id, **kwargs)
            for tc in task_classes
        }

    def update_all(self, samples: list[dict]) -> dict[str, ThresholdState]:
        """Update all task-class tuners from a shared sample batch.

        Args:
            samples: Mixed calibration samples (any task class).

        Returns:
            Dict mapping task class → :class:`ThresholdState`.
        """
        return {tc: tuner.update(samples) for tc, tuner in self._tuners.items()}

    def get_state(self, task_class: str) -> ThresholdState | None:
        """Return the current state for a single task class, or None."""
        tuner = self._tuners.get(task_class)
        return tuner.state() if tuner is not None else None

    def all_states(self) -> dict[str, ThresholdState]:
        """Return current state snapshots for all registered task classes."""
        return {tc: tuner.state() for tc, tuner in self._tuners.items()}

    @property
    def task_classes(self) -> list[str]:
        return list(self._tuners)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def apply_calibration_outcome(
    task_class: str,
    samples: list[dict],
    *,
    run_id: str | None = None,
    alpha: float = _DEFAULT_ALPHA,
    ece_low: float = _DEFAULT_ECE_LOW,
    ece_high: float = _DEFAULT_ECE_HIGH,
    initial_rca_threshold: float = _DEFAULT_RCA_THRESHOLD,
    initial_decomp_depth: int = _DEFAULT_DECOMP_DEPTH,
) -> ThresholdState:
    """One-shot convenience wrapper: create a tuner, apply samples, return state.

    Useful for stateless call sites that don't need to persist EMA between
    calls.  For persistent use across many rounds, instantiate
    :class:`OnlineThresholdTuner` directly and reuse it.

    Args:
        task_class: The task class to tune.
        samples: Calibration sample dicts (see :meth:`OnlineThresholdTuner.update`).
        run_id: Optional run identifier for telemetry.
        alpha: EMA smoothing factor.
        ece_low: ECE below this relaxes thresholds.
        ece_high: ECE above this tightens thresholds.
        initial_rca_threshold: Starting RCA threshold.
        initial_decomp_depth: Starting decomposition depth.

    Returns:
        :class:`ThresholdState` after applying the samples.
    """
    tuner = OnlineThresholdTuner(
        task_class,
        run_id=run_id,
        alpha=alpha,
        ece_low=ece_low,
        ece_high=ece_high,
        initial_rca_threshold=initial_rca_threshold,
        initial_decomp_depth=initial_decomp_depth,
    )
    return tuner.update(samples)
