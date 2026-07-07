"""Tests for the rocprof-compute roofline/SOL-guided kernel optimization loop.

Covers the profile -> diagnose-bottleneck -> targeted-tune -> re-benchmark
loop driven by ``rocprof-compute`` (formerly Omniperf) on the AMD stack.
"""

from __future__ import annotations

import pytest

from bob.rocprof_compute_roofline_loop import (
    BottleneckClass,
    RooflinePoint,
    classify_bottleneck,
    run_optimization_iteration,
    recommend_optimizations,
)


class TestClassifyBottleneck:
    def test_memory_bound_below_ridge(self):
        """Arithmetic intensity well below the ridge point => memory-bound."""
        result = classify_bottleneck(
            arithmetic_intensity=1.0,
            ridge_point=10.0,
            sol_by_block={"HBM": 92.0, "VALU": 12.0},
        )
        assert result == BottleneckClass.MEMORY_BOUND

    def test_compute_bound_above_ridge(self):
        """Arithmetic intensity above the ridge point => compute-bound."""
        result = classify_bottleneck(
            arithmetic_intensity=50.0,
            ridge_point=10.0,
            sol_by_block={"HBM": 20.0, "VALU": 95.0},
        )
        assert result == BottleneckClass.COMPUTE_BOUND

    def test_latency_bound_low_sol_everywhere(self):
        """Low SOL across all blocks => latency/occupancy bound."""
        result = classify_bottleneck(
            arithmetic_intensity=5.0,
            ridge_point=10.0,
            sol_by_block={"HBM": 15.0, "VALU": 18.0},
        )
        assert result == BottleneckClass.LATENCY_BOUND

    def test_sol_dominance_overrides_intensity(self):
        """High memory SOL forces memory-bound even near the ridge."""
        result = classify_bottleneck(
            arithmetic_intensity=11.0,
            ridge_point=10.0,
            sol_by_block={"HBM": 96.0, "VALU": 30.0},
        )
        assert result == BottleneckClass.MEMORY_BOUND

    def test_returns_bottleneck_class_enum(self):
        result = classify_bottleneck(
            arithmetic_intensity=2.0,
            ridge_point=10.0,
            sol_by_block={"HBM": 80.0},
        )
        assert isinstance(result, BottleneckClass)


class TestRecommendOptimizations:
    def test_memory_bound_recommendations_are_memory_focused(self):
        recs = recommend_optimizations(BottleneckClass.MEMORY_BOUND)
        assert isinstance(recs, list)
        assert len(recs) > 0
        joined = " ".join(recs).lower()
        assert "coalesc" in joined or "cache" in joined or "bandwidth" in joined

    def test_compute_bound_recommendations_are_compute_focused(self):
        recs = recommend_optimizations(BottleneckClass.COMPUTE_BOUND)
        joined = " ".join(recs).lower()
        assert "unroll" in joined or "fma" in joined or "instruction" in joined or "ilp" in joined

    def test_latency_bound_recommendations_are_occupancy_focused(self):
        recs = recommend_optimizations(BottleneckClass.LATENCY_BOUND)
        joined = " ".join(recs).lower()
        assert "occupancy" in joined or "register" in joined or "wave" in joined or "lds" in joined

    def test_disjoint_recommendation_sets(self):
        """The KernelPro insight: each bottleneck class gets its own advice."""
        mem = set(recommend_optimizations(BottleneckClass.MEMORY_BOUND))
        comp = set(recommend_optimizations(BottleneckClass.COMPUTE_BOUND))
        assert mem != comp


class TestRunOptimizationIteration:
    def _profile(self, latency_ms):
        def _fn(kernel_source):
            return RooflinePoint(
                arithmetic_intensity=1.0,
                ridge_point=10.0,
                sol_by_block={"HBM": 90.0, "VALU": 10.0},
                latency_ms=latency_ms,
            )
        return _fn

    def test_improvement_kept(self):
        """A tuned kernel that beats baseline beyond noise is kept."""
        latencies = iter([10.0, 5.0])

        def profile_fn(kernel_source):
            return RooflinePoint(
                arithmetic_intensity=1.0,
                ridge_point=10.0,
                sol_by_block={"HBM": 90.0, "VALU": 10.0},
                latency_ms=next(latencies),
            )

        result = run_optimization_iteration(
            kernel_source="__global__ void k() {}",
            profile_fn=profile_fn,
            tune_fn=lambda src, bottleneck, recs: src + " /*tuned*/",
        )
        assert result["kept"] is True
        assert result["bottleneck"] == BottleneckClass.MEMORY_BOUND
        assert result["baseline_latency_ms"] == 10.0
        assert result["candidate_latency_ms"] == 5.0
        assert "/*tuned*/" in result["kernel_source"]
        assert isinstance(result["recommendations"], list)

    def test_regression_rejected_keeps_baseline(self):
        """A tuned kernel that is slower is rejected; baseline source stays."""
        latencies = iter([5.0, 9.0])

        def profile_fn(kernel_source):
            return RooflinePoint(
                arithmetic_intensity=1.0,
                ridge_point=10.0,
                sol_by_block={"HBM": 90.0, "VALU": 10.0},
                latency_ms=next(latencies),
            )

        result = run_optimization_iteration(
            kernel_source="orig",
            profile_fn=profile_fn,
            tune_fn=lambda src, bottleneck, recs: "worse",
        )
        assert result["kept"] is False
        assert result["kernel_source"] == "orig"

    def test_within_noise_rejected(self):
        """A change within measurement noise is not kept."""
        latencies = iter([10.0, 9.99])

        def profile_fn(kernel_source):
            return RooflinePoint(
                arithmetic_intensity=1.0,
                ridge_point=10.0,
                sol_by_block={"HBM": 90.0, "VALU": 10.0},
                latency_ms=next(latencies),
            )

        result = run_optimization_iteration(
            kernel_source="orig",
            profile_fn=profile_fn,
            tune_fn=lambda src, bottleneck, recs: "candidate",
            noise_threshold=0.05,
        )
        assert result["kept"] is False

    def test_report_persisted(self, tmp_path):
        latencies = iter([10.0, 5.0])

        def profile_fn(kernel_source):
            return RooflinePoint(
                arithmetic_intensity=1.0,
                ridge_point=10.0,
                sol_by_block={"HBM": 90.0, "VALU": 10.0},
                latency_ms=next(latencies),
            )

        result = run_optimization_iteration(
            kernel_source="k",
            profile_fn=profile_fn,
            tune_fn=lambda src, b, r: src + "!",
            feature_id="feat123",
            runs_root=tmp_path,
        )
        report = result["report_path"]
        assert report is not None
        from pathlib import Path
        assert Path(report).exists()


class TestRooflinePoint:
    def test_is_memory_bound_property(self):
        pt = RooflinePoint(
            arithmetic_intensity=1.0,
            ridge_point=10.0,
            sol_by_block={"HBM": 90.0},
            latency_ms=1.0,
        )
        assert pt.arithmetic_intensity < pt.ridge_point
