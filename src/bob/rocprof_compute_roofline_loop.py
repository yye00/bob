"""rocprof-compute roofline / SOL-guided kernel optimization loop (AMD stack).

bob previously had no structured GPU-kernel optimization methodology: a perf
feature was a blind edit-and-benchmark with no bottleneck classification, so a
subagent could waste effort tuning compute on a memory-bound kernel (or vice
versa).

This module implements the converged 2026 SOTA loop (KernelAgent / KernelPro;
the AMD analog of NVIDIA's perf-nsight-compute-analysis skill) driven by
``rocprof-compute`` (formerly Omniperf) — the AMD analog of Nsight Compute,
which uniquely provides Speed-of-Light (SOL%) per hardware block and
hierarchical roofline analysis on MI200+ (MI300 / MI355 supported).

Each optimization iteration:

1. **Profile** — ``rocprof-compute profile`` then ``analyze`` (or
   ``--roof-only`` for a standalone roofline) to capture SOL% per hardware
   block and the kernel's position on the roofline. Modeled here by the
   caller-supplied ``profile_fn`` returning a :class:`RooflinePoint`, so the
   loop is fully testable without a GPU / ROCm install.
2. **Diagnose** — :func:`classify_bottleneck` maps arithmetic intensity
   relative to the ridge point (plus per-block SOL dominance) to a
   :class:`BottleneckClass`.
3. **Targeted tune** — apply ONLY optimizations relevant to that bottleneck
   class (the KernelPro insight: SEPARATE telemetry-interpretation, a
   rule-governed step, from code generation, a creative step). The rule-governed
   half is :func:`recommend_optimizations`; the creative half is the
   caller-supplied ``tune_fn``.
4. **Re-benchmark** — keep the change only if the core metric (kernel latency)
   improved beyond measurement noise.

The rocprof-compute report is persisted as verification evidence.

Because ncu roofline metrics do NOT map to AMD (no L1/L2/HBM transaction
counts via rocprof), this loop uses rocprof-compute's native roofline, not a
ported ncu-metric formula.

Sources: AMD rocprof-compute (Omniperf) docs; KernelAgent / KernelPro (2026).
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

__all__ = [
    "BottleneckClass",
    "RooflinePoint",
    "classify_bottleneck",
    "recommend_optimizations",
    "run_optimization_iteration",
]

# A hardware block whose SOL% at/above this level is treated as the dominant
# bottleneck regardless of where the kernel sits on the roofline.
_SOL_DOMINANCE = 85.0

# Below this SOL across every block the kernel is neither saturating memory nor
# compute — it is starved by latency / low occupancy.
_LATENCY_SOL_CEILING = 40.0

_MEMORY_BLOCKS = frozenset({"HBM", "L2", "L1", "LDS", "VMEM", "TCC", "TCP"})
_COMPUTE_BLOCKS = frozenset({"VALU", "SALU", "MFMA", "FMA", "SGPR", "ALU"})


class BottleneckClass(enum.Enum):
    """The dominant bottleneck class diagnosed from a roofline point."""

    MEMORY_BOUND = "memory_bound"
    COMPUTE_BOUND = "compute_bound"
    LATENCY_BOUND = "latency_bound"


@dataclass
class RooflinePoint:
    """A single rocprof-compute roofline / SOL measurement for a kernel.

    ``sol_by_block`` maps a hardware block name (e.g. ``"HBM"``, ``"VALU"``)
    to its Speed-of-Light percentage (0-100). ``arithmetic_intensity`` is
    FLOP/byte; ``ridge_point`` is the roofline ridge (peak FLOP/s divided by
    peak bandwidth) in the same units.
    """

    arithmetic_intensity: float
    ridge_point: float
    sol_by_block: Mapping[str, float]
    latency_ms: float
    extra: dict[str, Any] = field(default_factory=dict)


# Rule-governed optimization catalog keyed by bottleneck class. This is the
# telemetry-interpretation half of the KernelPro split — deterministic, not
# generative.
_RECOMMENDATIONS: dict[BottleneckClass, list[str]] = {
    BottleneckClass.MEMORY_BOUND: [
        "coalesce global memory accesses for contiguous HBM transactions",
        "stage reused data in LDS to cut redundant HBM traffic",
        "improve cache locality / tiling to raise L2 hit rate",
        "widen loads (float4/dwordx4) to increase achieved bandwidth",
    ],
    BottleneckClass.COMPUTE_BOUND: [
        "unroll inner loops to expose more ILP",
        "use FMA / MFMA matrix instructions where applicable",
        "reduce redundant instruction issue on the VALU",
        "hoist loop-invariant compute out of the hot path",
    ],
    BottleneckClass.LATENCY_BOUND: [
        "raise occupancy by lowering register (VGPR/SGPR) pressure",
        "increase active waves per SIMD to hide memory latency",
        "reduce LDS usage that caps concurrent workgroups",
        "restructure to overlap memory and compute across waves",
    ],
}


def classify_bottleneck(
    arithmetic_intensity: float,
    ridge_point: float,
    sol_by_block: Mapping[str, float],
) -> BottleneckClass:
    """Classify the dominant bottleneck from a rocprof-compute roofline point.

    Rule-governed diagnosis (KernelPro): first honor per-block SOL dominance
    (a block at/above ``_SOL_DOMINANCE`` is the bottleneck), then fall back to
    the kernel's position on the roofline relative to the ridge point. If no
    block is saturating and every block's SOL is low, the kernel is
    latency/occupancy bound.

    Raises ``ValueError`` on negative intensity or non-positive ridge point,
    and ``TypeError`` if ``sol_by_block`` is not a mapping.
    """
    if not isinstance(sol_by_block, Mapping):
        raise TypeError("sol_by_block must be a mapping of block name -> SOL%")
    if arithmetic_intensity < 0:
        raise ValueError("arithmetic_intensity must be non-negative")
    if ridge_point <= 0:
        raise ValueError("ridge_point must be positive")

    max_mem_sol = max(
        (sol for name, sol in sol_by_block.items() if name.upper() in _MEMORY_BLOCKS),
        default=0.0,
    )
    max_compute_sol = max(
        (sol for name, sol in sol_by_block.items() if name.upper() in _COMPUTE_BLOCKS),
        default=0.0,
    )

    # 1. Per-block SOL dominance overrides everything.
    if max_mem_sol >= _SOL_DOMINANCE and max_mem_sol >= max_compute_sol:
        return BottleneckClass.MEMORY_BOUND
    if max_compute_sol >= _SOL_DOMINANCE and max_compute_sol > max_mem_sol:
        return BottleneckClass.COMPUTE_BOUND

    # 2. Nothing saturating + universally low SOL => latency/occupancy bound.
    if sol_by_block:
        peak_sol = max(sol_by_block.values())
        if peak_sol < _LATENCY_SOL_CEILING:
            return BottleneckClass.LATENCY_BOUND

    # 3. Fall back to roofline position relative to the ridge.
    if arithmetic_intensity < ridge_point:
        return BottleneckClass.MEMORY_BOUND
    return BottleneckClass.COMPUTE_BOUND


def recommend_optimizations(bottleneck: BottleneckClass) -> list[str]:
    """Return the rule-governed optimization list for a bottleneck class.

    Applies ONLY optimizations relevant to *bottleneck* — the KernelPro
    insight that raw counters should not be dumped into a code-gen prompt.
    """
    if not isinstance(bottleneck, BottleneckClass):
        raise TypeError("bottleneck must be a BottleneckClass")
    return list(_RECOMMENDATIONS[bottleneck])


def _persist_report(
    runs_root: Path | str,
    feature_id: str,
    payload: dict[str, Any],
) -> str:
    """Persist the rocprof-compute report as verification evidence."""
    root = Path(runs_root) / feature_id
    root.mkdir(parents=True, exist_ok=True)
    report_path = root / "rocprof_compute_roofline.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return str(report_path)


def run_optimization_iteration(
    kernel_source: str,
    profile_fn: Callable[[str], RooflinePoint],
    tune_fn: Callable[[str, BottleneckClass, list[str]], str],
    *,
    noise_threshold: float = 0.02,
    feature_id: str | None = None,
    runs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Run one profile -> diagnose -> tune -> re-benchmark iteration.

    1. Profile the baseline ``kernel_source`` via ``profile_fn``.
    2. Diagnose the dominant bottleneck.
    3. Ask ``tune_fn(source, bottleneck, recommendations)`` for a candidate.
    4. Re-profile the candidate; keep it ONLY if latency improved by more than
       ``noise_threshold`` (fractional, e.g. 0.02 == 2%).

    Persists the rocprof-compute report to
    ``<runs_root>/<feature_id>/rocprof_compute_roofline.json`` when both are
    given, and returns the path in ``result["report_path"]``.

    Raises ``ValueError`` / ``TypeError`` on empty kernel source, non-callable
    hooks, or a ``profile_fn`` that does not return a :class:`RooflinePoint`.
    """
    if not isinstance(kernel_source, str):
        raise TypeError("kernel_source must be a string")
    if not kernel_source.strip():
        raise ValueError("kernel_source must be a non-empty kernel body")
    if not callable(profile_fn):
        raise TypeError("profile_fn must be callable")
    if not callable(tune_fn):
        raise TypeError("tune_fn must be callable")
    if not 0.0 <= noise_threshold < 1.0:
        raise ValueError("noise_threshold must be in [0, 1)")

    baseline = profile_fn(kernel_source)
    if not isinstance(baseline, RooflinePoint):
        raise TypeError("profile_fn must return a RooflinePoint")

    bottleneck = classify_bottleneck(
        baseline.arithmetic_intensity,
        baseline.ridge_point,
        baseline.sol_by_block,
    )
    recommendations = recommend_optimizations(bottleneck)

    candidate_source = tune_fn(kernel_source, bottleneck, recommendations)
    if not isinstance(candidate_source, str) or not candidate_source.strip():
        raise ValueError("tune_fn must return a non-empty kernel source")

    candidate = profile_fn(candidate_source)
    if not isinstance(candidate, RooflinePoint):
        raise TypeError("profile_fn must return a RooflinePoint")

    # Keep only if latency improved beyond measurement noise.
    improvement = (
        (baseline.latency_ms - candidate.latency_ms) / baseline.latency_ms
        if baseline.latency_ms > 0
        else 0.0
    )
    kept = improvement > noise_threshold

    result: dict[str, Any] = {
        "kept": kept,
        "bottleneck": bottleneck,
        "recommendations": recommendations,
        "baseline_latency_ms": baseline.latency_ms,
        "candidate_latency_ms": candidate.latency_ms,
        "improvement": improvement,
        "kernel_source": candidate_source if kept else kernel_source,
        "report_path": None,
    }

    if feature_id is not None and runs_root is not None:
        payload = {
            "feature_id": feature_id,
            "bottleneck": bottleneck.value,
            "recommendations": recommendations,
            "baseline": {
                "arithmetic_intensity": baseline.arithmetic_intensity,
                "ridge_point": baseline.ridge_point,
                "sol_by_block": dict(baseline.sol_by_block),
                "latency_ms": baseline.latency_ms,
            },
            "candidate": {
                "arithmetic_intensity": candidate.arithmetic_intensity,
                "ridge_point": candidate.ridge_point,
                "sol_by_block": dict(candidate.sol_by_block),
                "latency_ms": candidate.latency_ms,
            },
            "improvement": improvement,
            "kept": kept,
        }
        result["report_path"] = _persist_report(runs_root, feature_id, payload)

    return result
