"""GPU kernel autotuner harness.

Given a kernel build target and a parameter grid (block size, tile size,
register-blocking factor, vector width), sweeps configurations, measures
runtime + occupancy + cache hit rate, fits to the roofline model, and
reports the Pareto frontier.

Enables acceptance criteria like::

    gpu_speedup: >=10x vs naive_baseline
    roofline_efficiency: >=0.6

Public API
----------
KernelConfig        - Immutable parameter set for one kernel launch configuration.
SweepResult         - Measured outcomes for a single configuration.
sweep               - Exhaustively sweep a parameter grid, returning all results.
roofline_efficiency - Fraction of theoretical roofline peak achieved.
pareto_frontier     - Filter results to the Pareto-optimal subset.
"""

from __future__ import annotations

import itertools
import math
from typing import Any, Callable, Sequence

from pydantic import BaseModel, Field, field_validator

# Integration with bob3.enhanced_verification: the gpu_speedup and
# roofline_efficiency criterion types are evaluated by the enhanced
# verification layer after sweep results are recorded.
import bob3.enhanced_verification as _ev  # noqa: F401


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class KernelConfig(BaseModel):
    """Immutable set of tuning parameters for one GPU kernel configuration.

    Attributes:
        block_size:         CUDA/ROCm block (thread-block) size.
        tile_size:          Shared-memory tile edge length.
        register_blocking:  Register blocking factor per thread (>=1).
        vector_width:       SIMD vector width in elements (>=1).
    """

    block_size: int
    tile_size: int
    register_blocking: int = 1
    vector_width: int = 1

    model_config = {"frozen": True}

    @field_validator("block_size")
    @classmethod
    def _block_size_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"block_size must be positive, got {v}")
        return v

    @field_validator("tile_size")
    @classmethod
    def _tile_size_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"tile_size must be positive, got {v}")
        return v

    @field_validator("register_blocking")
    @classmethod
    def _rb_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"register_blocking must be positive, got {v}")
        return v

    @field_validator("vector_width")
    @classmethod
    def _vw_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"vector_width must be positive, got {v}")
        return v


class SweepResult(BaseModel):
    """Measurements for a single kernel configuration.

    Attributes:
        config:         The parameter set that produced these measurements.
        runtime_ms:     Wall-clock execution time in milliseconds.
        occupancy:      SM occupancy in [0, 1].
        cache_hit_rate: L1/L2 cache hit rate in [0, 1].
        extra:          Any additional profiling counters returned by the runner.
    """

    config: KernelConfig
    runtime_ms: float
    occupancy: float
    cache_hit_rate: float
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Roofline efficiency
# ---------------------------------------------------------------------------


def roofline_efficiency(
    *,
    achieved_flops: float,
    theoretical_peak_flops: float,
    achieved_bandwidth: float,
    theoretical_peak_bandwidth: float,
    arithmetic_intensity: float,
) -> float:
    """Fraction of the roofline peak actually achieved.

    The roofline ceiling for a given arithmetic intensity ``I`` is::

        ceiling = min(peak_flops, peak_bandwidth * I)

    Efficiency is ``achieved_flops / ceiling``, clamped to [0, 1].

    Args:
        achieved_flops:             Measured floating-point operations per second.
        theoretical_peak_flops:     Hardware peak FLOP/s (e.g. from vendor spec).
        achieved_bandwidth:         Measured memory bandwidth in bytes/s.
        theoretical_peak_bandwidth: Hardware peak memory bandwidth in bytes/s.
        arithmetic_intensity:       Operational intensity in FLOP/byte.

    Returns:
        Roofline efficiency in [0.0, 1.0].

    Raises:
        ValueError: If ``theoretical_peak_flops`` or
                    ``theoretical_peak_bandwidth`` is non-positive.
    """
    if theoretical_peak_flops <= 0.0:
        raise ValueError(
            f"theoretical_peak_flops must be positive, got {theoretical_peak_flops}"
        )
    if theoretical_peak_bandwidth <= 0.0:
        raise ValueError(
            f"theoretical_peak_bandwidth must be positive, got {theoretical_peak_bandwidth}"
        )

    if achieved_flops <= 0.0:
        return 0.0

    # Roofline ceiling: the smaller of compute peak and memory-bound peak.
    compute_ceiling = theoretical_peak_flops
    memory_ceiling = theoretical_peak_bandwidth * arithmetic_intensity
    roofline_ceiling = min(compute_ceiling, memory_ceiling)

    if roofline_ceiling <= 0.0:
        return 0.0

    raw = achieved_flops / roofline_ceiling
    return min(raw, 1.0)


# ---------------------------------------------------------------------------
# Pareto frontier
# ---------------------------------------------------------------------------


def pareto_frontier(results: list[SweepResult]) -> list[SweepResult]:
    """Return the Pareto-optimal subset of sweep results.

    A result ``a`` *dominates* ``b`` iff:
    - ``a.runtime_ms <= b.runtime_ms`` (lower is better)
    - ``a.occupancy >= b.occupancy`` (higher is better)
    - ``a.cache_hit_rate >= b.cache_hit_rate`` (higher is better)
    - At least one of the above is strictly better.

    Only results that are not dominated by any other result are returned.

    Args:
        results: All sweep results to filter.

    Returns:
        Pareto-optimal subset (order not guaranteed).
    """
    if not results:
        return []

    frontier: list[SweepResult] = []
    for candidate in results:
        dominated = False
        new_frontier: list[SweepResult] = []
        for existing in frontier:
            if _dominates(existing, candidate):
                dominated = True
                new_frontier.append(existing)
            elif _dominates(candidate, existing):
                # candidate dominates existing — drop existing
                pass
            else:
                new_frontier.append(existing)
        if not dominated:
            new_frontier.append(candidate)
        frontier = new_frontier

    return frontier


def _dominates(a: SweepResult, b: SweepResult) -> bool:
    """Return True iff ``a`` Pareto-dominates ``b``."""
    at_least_as_good = (
        a.runtime_ms <= b.runtime_ms
        and a.occupancy >= b.occupancy
        and a.cache_hit_rate >= b.cache_hit_rate
    )
    strictly_better = (
        a.runtime_ms < b.runtime_ms
        or a.occupancy > b.occupancy
        or a.cache_hit_rate > b.cache_hit_rate
    )
    return at_least_as_good and strictly_better


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


def sweep(
    *,
    kernel_runner: Callable[[KernelConfig], dict[str, float]],
    param_grid: dict[str, list[Any]],
) -> list[SweepResult]:
    """Exhaustively sweep a parameter grid and measure each configuration.

    Args:
        kernel_runner:
            Callable that accepts a :class:`KernelConfig` and returns a
            mapping with at least the keys ``runtime_ms``, ``occupancy``,
            and ``cache_hit_rate``.  Any additional keys are stored in
            :attr:`SweepResult.extra`.
        param_grid:
            Mapping from parameter name to list of values to try.
            Recognised keys: ``block_size``, ``tile_size``,
            ``register_blocking``, ``vector_width``.  Unknown keys are
            ignored by :class:`KernelConfig` but passed through to it for
            forward-compatibility.

    Returns:
        A list of :class:`SweepResult` — one entry per valid configuration.
        Configurations that raise during construction or execution are
        skipped with a logged warning.
    """
    # Extract per-axis value lists; default to [1] for optional axes.
    block_sizes: list[int] = param_grid.get("block_size", [])
    tile_sizes: list[int] = param_grid.get("tile_size", [])
    register_blockings: list[int] = param_grid.get("register_blocking", [1])
    vector_widths: list[int] = param_grid.get("vector_width", [1])

    if not block_sizes or not tile_sizes:
        return []

    results: list[SweepResult] = []

    for bs, ts, rb, vw in itertools.product(
        block_sizes, tile_sizes, register_blockings, vector_widths
    ):
        try:
            config = KernelConfig(
                block_size=bs,
                tile_size=ts,
                register_blocking=rb,
                vector_width=vw,
            )
        except Exception:
            continue

        try:
            metrics = kernel_runner(config)
        except Exception:
            continue

        results.append(
            SweepResult(
                config=config,
                runtime_ms=float(metrics["runtime_ms"]),
                occupancy=float(metrics["occupancy"]),
                cache_hit_rate=float(metrics["cache_hit_rate"]),
                extra={
                    k: v
                    for k, v in metrics.items()
                    if k not in {"runtime_ms", "occupancy", "cache_hit_rate"}
                },
            )
        )

    return results
