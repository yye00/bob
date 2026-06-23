"""Calibration-aware budget allocator for Bob3.

Uses ECE (Expected Calibration Error) per task class to determine how many
retry attempts to allocate. High ECE (poor calibration → hard tasks) gets
more attempts; low ECE (well-calibrated → easy tasks) gets fewer.

ECE source: compute_ece_by_bucket() from bob3.calibration, fed by the
calibration_data table (populated by F-R2-128 / record_calibration_result).
"""

from __future__ import annotations

import math

from bob3.calibration import TASK_CLASSES, compute_ece_by_bucket


# Mid-range ECE treated as "neutral" — no adjustment to base_attempts.
_NEUTRAL_ECE = 0.15


class CalibrationAwareBudgetAllocator:
    """Allocate retry attempts per task class based on calibration error.

    The adjustment formula scales additively around base_attempts using the
    difference between the observed ECE and a neutral ECE threshold.  A
    larger positive deviation (worse calibration) adds attempts; a negative
    deviation subtracts, clamped to [1, max_attempts].

    Args:
        base_attempts: Default attempt count when no calibration signal.
        max_attempts: Hard ceiling on allocated attempts.
        scale: Sensitivity of the adjustment; higher values produce larger
            deltas for the same ECE deviation.
    """

    def __init__(
        self,
        base_attempts: int = 3,
        max_attempts: int = 7,
        scale: float = 10.0,
    ) -> None:
        if base_attempts < 1:
            raise ValueError("base_attempts must be >= 1")
        if max_attempts < base_attempts:
            raise ValueError("max_attempts must be >= base_attempts")
        self.base_attempts = base_attempts
        self.max_attempts = max_attempts
        self.scale = scale

    def allocate(
        self,
        task_class: str,
        ece_by_task_class: dict[str, float],
    ) -> int:
        """Return the number of attempts to allocate for a task class.

        Args:
            task_class: The task class label (e.g. "refactor").
            ece_by_task_class: Mapping of task class → ECE.  Missing entries
                are treated as having ECE equal to the neutral threshold,
                which yields base_attempts unchanged.

        Returns:
            Integer attempt count in [1, max_attempts].
        """
        if task_class not in ece_by_task_class:
            return self.base_attempts

        ece = float(ece_by_task_class[task_class])
        delta = (ece - _NEUTRAL_ECE) * self.scale
        raw = self.base_attempts + math.ceil(delta)
        return max(1, min(self.max_attempts, raw))

    def allocate_all(
        self,
        task_classes: list[str],
        ece_by_task_class: dict[str, float],
    ) -> dict[str, int]:
        """Return allocations for every requested task class.

        Args:
            task_classes: List of task class labels to allocate for.
            ece_by_task_class: ECE mapping; see :meth:`allocate`.

        Returns:
            Dict mapping each task class to its allocated attempt count.
        """
        return {tc: self.allocate(tc, ece_by_task_class) for tc in task_classes}


def allocate_budget_from_db(
    project_id: str | None = None,
    base_attempts: int = 3,
    max_attempts: int = 7,
    scale: float = 10.0,
) -> dict[str, int]:
    """Compute calibration-aware attempt budgets from the live database.

    Reads calibration_data rows for the given project (or global if
    project_id is None), computes ECE per task class via
    :func:`~bob3.calibration.compute_ece_by_bucket`, and returns the
    resulting allocation for all canonical task classes.

    Args:
        project_id: Restrict calibration reads to this project.  Pass
            ``None`` to use the global (project-agnostic) records.
        base_attempts: Baseline attempt count; see
            :class:`CalibrationAwareBudgetAllocator`.
        max_attempts: Ceiling on attempt count.
        scale: Sensitivity multiplier.

    Returns:
        Dict mapping each of :data:`~bob3.calibration.TASK_CLASSES` to an
        attempt count.
    """
    from bob3.db import connect

    with connect() as conn:
        if project_id is None:
            rows = conn.execute(
                "SELECT task_class, confidence_bucket, total_passes, total_attempts "
                "FROM calibration_data WHERE project_id IS NULL"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT task_class, confidence_bucket, total_passes, total_attempts "
                "FROM calibration_data WHERE project_id = ?",
                (project_id,),
            ).fetchall()

    samples = _rows_to_samples(rows)
    ece_by_class = compute_ece_by_bucket(samples) if samples else {}

    allocator = CalibrationAwareBudgetAllocator(
        base_attempts=base_attempts,
        max_attempts=max_attempts,
        scale=scale,
    )
    return allocator.allocate_all(
        task_classes=list(TASK_CLASSES),
        ece_by_task_class=ece_by_class,
    )


def _rows_to_samples(
    rows: list[tuple],
) -> list[dict]:
    """Convert calibration_data DB rows to the sample format for compute_ece_by_bucket.

    Each DB row stores aggregate counts rather than individual predictions.
    We reconstruct pseudo-samples by treating the confidence bucket midpoint
    as the predicted confidence and expanding pass/fail counts into individual
    sample dicts.  This gives compute_ece_by_bucket a faithful view of the
    aggregate.

    Args:
        rows: Tuples of (task_class, confidence_bucket, total_passes, total_attempts).

    Returns:
        List of sample dicts with keys task_class, predicted_conf, passed.
    """
    samples: list[dict] = []
    for task_class, confidence_bucket, total_passes, total_attempts in rows:
        if not total_attempts:
            continue
        predicted_conf = _bucket_midpoint(confidence_bucket)
        total_failures = total_attempts - total_passes
        for _ in range(total_passes):
            samples.append({"task_class": task_class, "predicted_conf": predicted_conf, "passed": True})
        for _ in range(total_failures):
            samples.append({"task_class": task_class, "predicted_conf": predicted_conf, "passed": False})
    return samples


def _bucket_midpoint(bucket: str) -> float:
    """Return the midpoint of a confidence bucket string like '0.7-0.8'.

    Falls back to 0.5 for unparseable strings.
    """
    try:
        lo, hi = bucket.split("-")
        return (float(lo) + float(hi)) / 2.0
    except (ValueError, AttributeError):
        return 0.5
