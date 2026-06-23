"""Analysis notebooks (paper artifact).

Reproducible Jupyter notebooks generating: reliability diagrams, ablation
tables (V-1 vs V0 vs V1 vs V2 vs V3), bootstrap confidence intervals, and
ECE plots. All from raw run.jsonl telemetry data.

This module provides the Python infrastructure that the notebooks import:
- Telemetry loading and parsing from run.jsonl
- Reliability diagram data computation
- Ablation table generation across version groups
- Bootstrap confidence interval estimation
- Expected Calibration Error (ECE) computation

The notebooks themselves will be authored in Round 5 after sweep data is
available. This module ships the reusable, testable computational core.

Public API
----------
- ``RunRecord``              — parsed record from run.jsonl
- ``load_run_jsonl``         — parse a run.jsonl file into RunRecord objects
- ``compute_ece``            — Expected Calibration Error from confidence/outcome pairs
- ``reliability_diagram_data`` — bucket statistics for reliability diagrams
- ``bootstrap_ci``           — parametric bootstrap confidence interval for a statistic
- ``ablation_table``         — summary table across version groups (V-1 … V3)
- ``VERSION_LABELS``         — ordered list of version labels used in ablation tables
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION_LABELS: list[str] = ["V-1", "V0", "V1", "V2", "V3"]

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RunRecord:
    """One parsed record from a run.jsonl telemetry file.

    Attributes:
        feature_id:    UUID of the feature being implemented.
        feature_name:  Human-readable feature name.
        outcome:       'completed', 'failed', or 'needs_human'.
        confidence:    Agent-reported confidence in [0.0, 1.0], or None.
        version:       Model/generation version label, e.g. 'V1'.
        duration_ms:   Wall-clock duration in milliseconds, or None.
        cost_usd:      API cost in USD, or None.
        num_turns:     Number of dialogue turns, or None.
        raw:           The original parsed JSON dict.
    """

    feature_id: str
    feature_name: str
    outcome: str
    confidence: Optional[float]
    version: Optional[str]
    duration_ms: Optional[int]
    cost_usd: Optional[float]
    num_turns: Optional[int]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def success(self) -> bool:
        """True when outcome is 'completed'."""
        return self.outcome == "completed"


# ---------------------------------------------------------------------------
# Telemetry loading
# ---------------------------------------------------------------------------


def load_run_jsonl(path: str | Path) -> list[RunRecord]:
    """Parse a run.jsonl telemetry file into a list of RunRecord objects.

    Each line must be a JSON object. Lines that are blank or begin with '#'
    are silently skipped. Lines that fail JSON parsing raise ``ValueError``.

    Args:
        path: Path to the .jsonl file.

    Returns:
        List of :class:`RunRecord` objects, one per non-empty line.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError:        If a line contains invalid JSON.
    """
    path = Path(path)
    records: list[RunRecord] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {lineno}: {exc}") from exc
            records.append(_record_from_dict(obj))
    return records


def _record_from_dict(obj: dict[str, Any]) -> RunRecord:
    """Convert a raw JSON dict to a RunRecord."""
    confidence = obj.get("confidence")
    if confidence is not None:
        confidence = float(confidence)

    duration_ms = obj.get("duration_ms")
    if duration_ms is not None:
        duration_ms = int(duration_ms)

    cost_usd = obj.get("cost_usd")
    if cost_usd is not None:
        cost_usd = float(cost_usd)

    num_turns = obj.get("num_turns")
    if num_turns is not None:
        num_turns = int(num_turns)

    return RunRecord(
        feature_id=str(obj.get("feature_id", "")),
        feature_name=str(obj.get("feature_name", "")),
        outcome=str(obj.get("outcome", "failed")),
        confidence=confidence,
        version=obj.get("version"),
        duration_ms=duration_ms,
        cost_usd=cost_usd,
        num_turns=num_turns,
        raw=obj,
    )


# ---------------------------------------------------------------------------
# Expected Calibration Error (ECE)
# ---------------------------------------------------------------------------


def compute_ece(
    confidences: Sequence[float],
    outcomes: Sequence[bool],
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error (ECE).

    Partitions predictions into *n_bins* equal-width bins on [0, 1] and
    computes the weighted average of |accuracy − confidence| within each bin.

    ECE = Σ (|B_m| / n) * |acc(B_m) − conf(B_m)|

    Args:
        confidences: Sequence of predicted confidence values in [0, 1].
        outcomes:    Sequence of ground-truth boolean success flags.
        n_bins:      Number of equal-width calibration bins.

    Returns:
        ECE as a float in [0, 1].  Returns 0.0 for empty inputs.

    Raises:
        ValueError: If *confidences* and *outcomes* differ in length.
        ValueError: If *n_bins* < 1.
    """
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")
    if len(confidences) != len(outcomes):
        raise ValueError(
            f"confidences and outcomes must have the same length: "
            f"{len(confidences)} vs {len(outcomes)}"
        )
    n = len(confidences)
    if n == 0:
        return 0.0

    bin_correct: list[int] = [0] * n_bins
    bin_conf_sum: list[float] = [0.0] * n_bins
    bin_count: list[int] = [0] * n_bins

    for conf, outcome in zip(confidences, outcomes):
        conf = float(conf)
        # Clamp to [0, 1]
        conf = max(0.0, min(1.0, conf))
        # Bin index: use floor(conf * n_bins), clamp to n_bins-1 at boundary
        b = min(int(conf * n_bins), n_bins - 1)
        bin_count[b] += 1
        bin_conf_sum[b] += conf
        if outcome:
            bin_correct[b] += 1

    ece = 0.0
    for b in range(n_bins):
        cnt = bin_count[b]
        if cnt == 0:
            continue
        acc = bin_correct[b] / cnt
        avg_conf = bin_conf_sum[b] / cnt
        ece += (cnt / n) * abs(acc - avg_conf)

    return ece


# ---------------------------------------------------------------------------
# Reliability diagram data
# ---------------------------------------------------------------------------


@dataclass
class ReliabilityBucket:
    """Statistics for one bin of a reliability diagram.

    Attributes:
        lower:       Lower bound of the confidence bin (inclusive).
        upper:       Upper bound of the confidence bin (exclusive, or 1.0 for last).
        count:       Number of predictions in this bin.
        accuracy:    Fraction of predictions in this bin that succeeded.
        avg_confidence: Average predicted confidence in this bin.
    """

    lower: float
    upper: float
    count: int
    accuracy: float
    avg_confidence: float


def reliability_diagram_data(
    confidences: Sequence[float],
    outcomes: Sequence[bool],
    n_bins: int = 10,
) -> list[ReliabilityBucket]:
    """Compute per-bucket statistics for a reliability (calibration) diagram.

    Args:
        confidences: Sequence of predicted confidence values in [0, 1].
        outcomes:    Sequence of boolean success flags.
        n_bins:      Number of equal-width bins.

    Returns:
        List of :class:`ReliabilityBucket` objects, one per bin (including
        empty bins with count=0, accuracy=0, avg_confidence=midpoint).

    Raises:
        ValueError: If *confidences* and *outcomes* differ in length.
        ValueError: If *n_bins* < 1.
    """
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")
    if len(confidences) != len(outcomes):
        raise ValueError(
            f"confidences and outcomes must have the same length: "
            f"{len(confidences)} vs {len(outcomes)}"
        )

    bin_correct: list[int] = [0] * n_bins
    bin_conf_sum: list[float] = [0.0] * n_bins
    bin_count: list[int] = [0] * n_bins

    for conf, outcome in zip(confidences, outcomes):
        conf = float(max(0.0, min(1.0, conf)))
        b = min(int(conf * n_bins), n_bins - 1)
        bin_count[b] += 1
        bin_conf_sum[b] += conf
        if outcome:
            bin_correct[b] += 1

    buckets: list[ReliabilityBucket] = []
    bin_width = 1.0 / n_bins
    for b in range(n_bins):
        lower = b * bin_width
        upper = (b + 1) * bin_width
        cnt = bin_count[b]
        if cnt > 0:
            accuracy = bin_correct[b] / cnt
            avg_confidence = bin_conf_sum[b] / cnt
        else:
            accuracy = 0.0
            avg_confidence = lower + bin_width / 2.0
        buckets.append(
            ReliabilityBucket(
                lower=lower,
                upper=upper,
                count=cnt,
                accuracy=accuracy,
                avg_confidence=avg_confidence,
            )
        )
    return buckets


# ---------------------------------------------------------------------------
# Bootstrap confidence intervals
# ---------------------------------------------------------------------------


def bootstrap_ci(
    data: Sequence[float],
    statistic: Callable[[list[float]], float],
    n_bootstrap: int = 1000,
    confidence_level: float = 0.95,
    seed: Optional[int] = None,
) -> tuple[float, float]:
    """Estimate a bootstrap confidence interval for a scalar statistic.

    Resamples *data* with replacement *n_bootstrap* times, applies *statistic*
    to each resample, and returns the (alpha/2, 1-alpha/2) percentile interval.

    Args:
        data:             Observed sample values.
        statistic:        Function mapping a list of floats to a scalar.
        n_bootstrap:      Number of bootstrap resamples.
        confidence_level: Desired coverage (e.g. 0.95 for 95% CI).
        seed:             Optional RNG seed for reproducibility.

    Returns:
        Tuple (lower, upper) of the confidence interval endpoints.

    Raises:
        ValueError: If *data* is empty.
        ValueError: If *n_bootstrap* < 1.
        ValueError: If *confidence_level* not in (0, 1).
    """
    if len(data) == 0:
        raise ValueError("data must be non-empty")
    if n_bootstrap < 1:
        raise ValueError(f"n_bootstrap must be >= 1, got {n_bootstrap}")
    if not (0.0 < confidence_level < 1.0):
        raise ValueError(f"confidence_level must be in (0, 1), got {confidence_level}")

    rng = random.Random(seed)
    data_list = list(data)
    n = len(data_list)

    bootstrap_stats: list[float] = []
    for _ in range(n_bootstrap):
        resample = [rng.choice(data_list) for _ in range(n)]
        bootstrap_stats.append(statistic(resample))

    bootstrap_stats.sort()
    alpha = 1.0 - confidence_level
    lo_idx = int(math.floor(alpha / 2.0 * n_bootstrap))
    hi_idx = int(math.ceil((1.0 - alpha / 2.0) * n_bootstrap)) - 1
    lo_idx = max(0, min(lo_idx, n_bootstrap - 1))
    hi_idx = max(0, min(hi_idx, n_bootstrap - 1))

    return bootstrap_stats[lo_idx], bootstrap_stats[hi_idx]


# ---------------------------------------------------------------------------
# Ablation table
# ---------------------------------------------------------------------------


@dataclass
class AblationRow:
    """One row in an ablation table, representing one version group.

    Attributes:
        version:       Version label (e.g. 'V1').
        n:             Total number of runs in this version group.
        success_rate:  Fraction of runs with outcome 'completed'.
        mean_cost_usd: Mean API cost per run (None if no cost data).
        mean_turns:    Mean number of turns per run (None if no turn data).
        ece:           Expected Calibration Error (None if no confidence data).
        ci_lower:      Lower bound of 95% bootstrap CI on success_rate (None if n < 2).
        ci_upper:      Upper bound of 95% bootstrap CI on success_rate (None if n < 2).
    """

    version: str
    n: int
    success_rate: float
    mean_cost_usd: Optional[float]
    mean_turns: Optional[float]
    ece: Optional[float]
    ci_lower: Optional[float]
    ci_upper: Optional[float]


def ablation_table(
    records: Sequence[RunRecord],
    versions: Optional[list[str]] = None,
    n_bootstrap: int = 1000,
    seed: Optional[int] = 42,
) -> list[AblationRow]:
    """Build an ablation table across version groups.

    Groups *records* by their ``.version`` field, then for each group
    (filtered to *versions* if provided) computes:

    - success_rate and its 95% bootstrap CI
    - mean cost and mean turns
    - Expected Calibration Error (when confidence data is available)

    Args:
        records:     Parsed run records from ``load_run_jsonl``.
        versions:    Ordered list of version labels to include.
                     Defaults to ``VERSION_LABELS``.
        n_bootstrap: Bootstrap resamples for CI estimation.
        seed:        RNG seed for reproducibility.

    Returns:
        List of :class:`AblationRow` objects in *versions* order.
        Versions with no matching records appear with ``n=0`` and
        ``success_rate=0.0``.
    """
    if versions is None:
        versions = VERSION_LABELS

    # Group records by version
    by_version: dict[str, list[RunRecord]] = {v: [] for v in versions}
    for rec in records:
        v = rec.version
        if v in by_version:
            by_version[v].append(rec)

    rows: list[AblationRow] = []
    for v in versions:
        group = by_version[v]
        n = len(group)
        if n == 0:
            rows.append(
                AblationRow(
                    version=v,
                    n=0,
                    success_rate=0.0,
                    mean_cost_usd=None,
                    mean_turns=None,
                    ece=None,
                    ci_lower=None,
                    ci_upper=None,
                )
            )
            continue

        outcomes = [r.success for r in group]
        success_rate = sum(outcomes) / n

        # Bootstrap CI on success rate
        if n >= 2:
            outcome_floats = [1.0 if o else 0.0 for o in outcomes]
            ci_lower, ci_upper = bootstrap_ci(
                outcome_floats,
                statistic=lambda xs: sum(xs) / len(xs),
                n_bootstrap=n_bootstrap,
                confidence_level=0.95,
                seed=seed,
            )
        else:
            ci_lower = ci_upper = None

        # Mean cost
        costs = [r.cost_usd for r in group if r.cost_usd is not None]
        mean_cost = sum(costs) / len(costs) if costs else None

        # Mean turns
        turns = [r.num_turns for r in group if r.num_turns is not None]
        mean_turns = sum(turns) / len(turns) if turns else None

        # ECE
        conf_pairs = [
            (r.confidence, r.success)
            for r in group
            if r.confidence is not None
        ]
        if conf_pairs:
            confs, outc = zip(*conf_pairs)
            ece = compute_ece(list(confs), list(outc))
        else:
            ece = None

        rows.append(
            AblationRow(
                version=v,
                n=n,
                success_rate=success_rate,
                mean_cost_usd=mean_cost,
                mean_turns=mean_turns,
                ece=ece,
                ci_lower=ci_lower,
                ci_upper=ci_upper,
            )
        )

    return rows
