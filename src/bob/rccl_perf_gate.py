"""RCCL busbw/algbw perf-uplift gate — self-measured, noise-aware A/B.

Feature 1ce12ad4-3312-43a9-9720-1791c3f2aa0b

The RCCL spec (F-R8-001) has a single pass/fail bar for every performance
feature: *the optimized build beats bob's OWN freshly-measured baseline for
this same machine / partition / protocol by a margin exceeding measurement
noise*.  It explicitly warns that back-to-back runs vary up to 2x.

bob's existing AC vocabulary (File exists / Function-Class defined / pytest /
integration / behavior) cannot express this, and its ``regression_*`` modules
parse only pytest results.  This module adds:

``parse_busbw_algbw_table`` — parse the rccl-tests table columns
    (size, count, type, redop, root, then time/algbw/busbw/#wrong for
    out-of-place AND in-place).

``evaluate_perf_uplift_gate`` — implement the F-R8-001 protocol:
    * baseline is bob's OWN freshly-measured UNMODIFIED build (never an
      internet/blog number);
    * N>=10 interleaved OLD/NEW reps with identical warmup/iters;
    * MEDIAN busbw per size with bootstrap 95% CIs and a per-size noise band
      = max(CI half-width, half-IQR);
    * a "win" passes only if NEW median > OLD median, the CIs are disjoint,
      and delta exceeds max(feature threshold, 2x noise half-band).

Guards against the obvious cheats: stale/absent baseline, cherry-picking
best-of-N, and changing the size range between baseline and candidate.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

__all__ = [
    "MIN_REPS",
    "DEFAULT_WARMUP",
    "DEFAULT_ITERS",
    "PerfRow",
    "SizeStats",
    "SizeVerdict",
    "PerfGateResult",
    "parse_busbw_algbw_table",
    "evaluate_perf_uplift_gate",
    "compute_size_stats",
]

# F-R8-001: at least 10 interleaved OLD/NEW reps are required.
MIN_REPS = 10
# Identical warmup/iters mandated by the protocol: -w 20 -n 50.
DEFAULT_WARMUP = 20
DEFAULT_ITERS = 50
# Number of bootstrap resamples used for the median 95% CI.
_BOOTSTRAP_RESAMPLES = 1000
# Deterministic LCG seed — reproducible bootstrap without importing random
# state that would make the gate non-reproducible across processes.
_LCG_A = 6364136223846793005
_LCG_C = 1442695040888963407
_LCG_M = 2 ** 64


@dataclass(frozen=True)
class PerfRow:
    """One rccl-tests row: out-of-place AND in-place measurements."""

    size: int
    count: int
    dtype: str
    redop: str
    root: int
    oop_time_us: float
    oop_algbw: float
    oop_busbw: float
    oop_wrong: str
    ip_time_us: float
    ip_algbw: float
    ip_busbw: float
    ip_wrong: str


@dataclass(frozen=True)
class SizeStats:
    """Aggregated busbw statistics for one message size."""

    size: int
    n: int
    median: float
    ci_low: float
    ci_high: float
    iqr: float
    noise_half_band: float
    samples: tuple[float, ...]


@dataclass(frozen=True)
class SizeVerdict:
    """Per-size win/no-win verdict."""

    size: int
    old: SizeStats
    new: SizeStats
    delta: float
    required_margin: float
    cis_disjoint: bool
    new_beats_old: bool
    is_win: bool
    reason: str


@dataclass(frozen=True)
class PerfGateResult:
    """Overall gate result."""

    passed: bool
    reason: str
    per_size: tuple[SizeVerdict, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_busbw_algbw_table(text: str) -> list[PerfRow]:
    """Parse an rccl-tests busbw/algbw table into :class:`PerfRow` rows.

    The rccl-tests data lines have this column layout::

        #  size  count  type  redop  root  time  algbw  busbw  #wrong  \
                                     time  algbw  busbw  #wrong
        # (out-of-place ..............................)  (in-place ...........)

    Comment lines (starting with ``#``) and blank lines are skipped.  Returns
    an empty list for empty / header-only input (a well-defined boundary
    result, not an exception).

    Raises :class:`ValueError` if *text* is not a string, or if a non-comment
    data line is malformed (too few columns / non-numeric size).
    """
    if not isinstance(text, str):
        raise ValueError("parse_busbw_algbw_table: text must be a str")

    rows: list[PerfRow] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        # 5 leading descriptor cols + 4 out-of-place + 4 in-place = 13.
        if len(fields) < 13:
            raise ValueError(
                f"parse_busbw_algbw_table: line {lineno} has "
                f"{len(fields)} columns, expected >= 13: {line!r}"
            )
        try:
            row = PerfRow(
                size=int(fields[0]),
                count=int(fields[1]),
                dtype=fields[2],
                redop=fields[3],
                root=int(fields[4]),
                oop_time_us=float(fields[5]),
                oop_algbw=float(fields[6]),
                oop_busbw=float(fields[7]),
                oop_wrong=fields[8],
                ip_time_us=float(fields[9]),
                ip_algbw=float(fields[10]),
                ip_busbw=float(fields[11]),
                ip_wrong=fields[12],
            )
        except ValueError as exc:
            raise ValueError(
                f"parse_busbw_algbw_table: line {lineno} not numeric: {line!r} ({exc})"
            ) from exc
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _bootstrap_median_ci(samples: Sequence[float], seed: int) -> tuple[float, float]:
    """Return a bootstrap 95% CI (low, high) for the median of *samples*.

    Uses a deterministic LCG so the CI is reproducible across processes.
    """
    n = len(samples)
    if n == 0:
        return (0.0, 0.0)
    if n == 1:
        return (samples[0], samples[0])
    state = (seed ^ 0x9E3779B97F4A7C15) % _LCG_M
    medians: list[float] = []
    for _ in range(_BOOTSTRAP_RESAMPLES):
        resample = []
        for _ in range(n):
            state = (_LCG_A * state + _LCG_C) % _LCG_M
            idx = state % n
            resample.append(samples[idx])
        medians.append(statistics.median(resample))
    medians.sort()
    lo_idx = int(0.025 * (len(medians) - 1))
    hi_idx = int(0.975 * (len(medians) - 1))
    return (medians[lo_idx], medians[hi_idx])


def compute_size_stats(size: int, busbw_samples: Sequence[float]) -> SizeStats:
    """Aggregate busbw samples for one size into a :class:`SizeStats`.

    Noise half-band = max(CI half-width, half-IQR) per the protocol.
    """
    if not busbw_samples:
        raise ValueError("compute_size_stats: busbw_samples must be non-empty")
    samples = [float(x) for x in busbw_samples]
    median = statistics.median(samples)
    ci_low, ci_high = _bootstrap_median_ci(samples, seed=size or 1)
    if len(samples) >= 2:
        try:
            q1, _, q3 = statistics.quantiles(samples, n=4, method="inclusive")
            iqr = q3 - q1
        except statistics.StatisticsError:
            iqr = 0.0
    else:
        iqr = 0.0
    ci_half_width = (ci_high - ci_low) / 2.0
    noise_half_band = max(ci_half_width, iqr / 2.0)
    return SizeStats(
        size=size,
        n=len(samples),
        median=median,
        ci_low=ci_low,
        ci_high=ci_high,
        iqr=iqr,
        noise_half_band=noise_half_band,
        samples=tuple(samples),
    )


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def _extract_busbw_by_size(
    reps: Iterable[Any], *, label: str
) -> dict[int, list[float]]:
    """Collect busbw samples keyed by size from a sequence of reps.

    Each rep may be:
      * a list of :class:`PerfRow`;
      * a raw rccl-tests table string (parsed on the fly);
      * a mapping {size: busbw}.
    """
    by_size: dict[int, list[float]] = {}
    reps = list(reps)
    if not reps:
        raise ValueError(f"evaluate_perf_uplift_gate: {label} reps are empty")
    for rep in reps:
        if isinstance(rep, str):
            parsed = parse_busbw_algbw_table(rep)
            for row in parsed:
                by_size.setdefault(row.size, []).append(row.oop_busbw)
        elif isinstance(rep, dict):
            for size, busbw in rep.items():
                by_size.setdefault(int(size), []).append(float(busbw))
        elif isinstance(rep, (list, tuple)):
            for row in rep:
                if not isinstance(row, PerfRow):
                    raise ValueError(
                        f"evaluate_perf_uplift_gate: {label} rep row must be a "
                        f"PerfRow, got {type(row).__name__}"
                    )
                by_size.setdefault(row.size, []).append(row.oop_busbw)
        else:
            raise ValueError(
                f"evaluate_perf_uplift_gate: {label} rep has unsupported type "
                f"{type(rep).__name__}"
            )
    return by_size


def evaluate_perf_uplift_gate(
    baseline_reps: Sequence[Any],
    candidate_reps: Sequence[Any],
    *,
    threshold: float = 0.0,
    min_reps: int = MIN_REPS,
    baseline_is_self_measured: bool = True,
    require_disjoint_ci: bool = True,
) -> PerfGateResult:
    """Evaluate the F-R8-001 perf-uplift gate on OLD vs NEW reps.

    *baseline_reps* and *candidate_reps* are sequences of measurement reps
    (rccl-tests table strings, PerfRow lists, or {size: busbw} maps).  Each
    entry is one repetition; there must be at least *min_reps* of each.

    A per-size "win" requires:
      * NEW median > OLD median;
      * the median 95% CIs are disjoint (unless *require_disjoint_ci* off);
      * delta (NEW - OLD median) > max(*threshold* fraction of OLD median,
        2x noise half-band).

    The overall gate passes only if EVERY common size is a win, the size
    ranges match (no size added/dropped between baseline and candidate), and
    the baseline is self-measured.

    Raises :class:`ValueError` on invalid input (non-sequence reps, negative
    threshold, non-positive min_reps).  Returns a well-defined
    :class:`PerfGateResult` (``passed=False``) for empty / too-few reps rather
    than raising, so callers get a verdict, not a crash.
    """
    if not isinstance(threshold, (int, float)) or threshold < 0:
        raise ValueError("evaluate_perf_uplift_gate: threshold must be >= 0")
    if not isinstance(min_reps, int) or min_reps < 1:
        raise ValueError("evaluate_perf_uplift_gate: min_reps must be a positive int")
    if baseline_reps is None or candidate_reps is None:
        raise ValueError("evaluate_perf_uplift_gate: reps must not be None")
    if isinstance(baseline_reps, (str, bytes)) or isinstance(candidate_reps, (str, bytes)):
        raise ValueError(
            "evaluate_perf_uplift_gate: reps must be a sequence of reps, not a str"
        )

    warnings: list[str] = []

    # Cheat guard: baseline must be bob's own freshly-measured build.
    if not baseline_is_self_measured:
        return PerfGateResult(
            passed=False,
            reason="baseline is not self-measured (internet/blog numbers are "
            "not a valid denominator)",
            warnings=("stale-or-external-baseline",),
        )

    baseline_list = list(baseline_reps)
    candidate_list = list(candidate_reps)

    # Boundary: empty / too-few reps → well-defined non-passing result.
    if not baseline_list or not candidate_list:
        return PerfGateResult(
            passed=False,
            reason="empty baseline or candidate reps",
            warnings=("empty-input",),
        )
    if len(baseline_list) < min_reps or len(candidate_list) < min_reps:
        return PerfGateResult(
            passed=False,
            reason=(
                f"too few reps: need >= {min_reps} interleaved OLD/NEW reps "
                f"(got baseline={len(baseline_list)}, candidate={len(candidate_list)})"
            ),
            warnings=("insufficient-reps",),
        )

    old_by_size = _extract_busbw_by_size(baseline_list, label="baseline")
    new_by_size = _extract_busbw_by_size(candidate_list, label="candidate")

    if not old_by_size or not new_by_size:
        return PerfGateResult(
            passed=False,
            reason="no busbw samples parsed from reps",
            warnings=("no-samples",),
        )

    # Cheat guard: size range must not change between baseline and candidate.
    old_sizes = set(old_by_size)
    new_sizes = set(new_by_size)
    if old_sizes != new_sizes:
        return PerfGateResult(
            passed=False,
            reason=(
                "size range changed between baseline and candidate "
                f"(baseline-only={sorted(old_sizes - new_sizes)}, "
                f"candidate-only={sorted(new_sizes - old_sizes)})"
            ),
            warnings=("size-range-mismatch",),
        )

    per_size: list[SizeVerdict] = []
    all_win = True
    for size in sorted(old_sizes):
        old_stats = compute_size_stats(size, old_by_size[size])
        new_stats = compute_size_stats(size, new_by_size[size])
        delta = new_stats.median - old_stats.median
        noise_half_band = max(old_stats.noise_half_band, new_stats.noise_half_band)
        required_margin = max(threshold * old_stats.median, 2.0 * noise_half_band)
        cis_disjoint = new_stats.ci_low > old_stats.ci_high
        new_beats_old = new_stats.median > old_stats.median
        is_win = new_beats_old and delta > required_margin
        if require_disjoint_ci:
            is_win = is_win and cis_disjoint

        if is_win:
            reason = "win"
        elif not new_beats_old:
            reason = "NEW median does not exceed OLD median"
        elif require_disjoint_ci and not cis_disjoint:
            reason = "median CIs overlap (within measurement noise)"
        else:
            reason = (
                f"delta {delta:.4f} does not exceed required margin "
                f"{required_margin:.4f}"
            )

        per_size.append(
            SizeVerdict(
                size=size,
                old=old_stats,
                new=new_stats,
                delta=delta,
                required_margin=required_margin,
                cis_disjoint=cis_disjoint,
                new_beats_old=new_beats_old,
                is_win=is_win,
                reason=reason,
            )
        )
        if not is_win:
            all_win = False

    if all_win:
        overall_reason = f"win on all {len(per_size)} sizes"
    else:
        losers = [v.size for v in per_size if not v.is_win]
        overall_reason = f"no uplift on sizes {losers}"

    return PerfGateResult(
        passed=all_win,
        reason=overall_reason,
        per_size=tuple(per_size),
        warnings=tuple(warnings),
    )
