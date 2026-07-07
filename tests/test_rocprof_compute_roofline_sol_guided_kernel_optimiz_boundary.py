"""Boundary-case tests for rocprof_compute_roofline_loop.

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising exceptions.
"""

from __future__ import annotations

from bob.rocprof_compute_roofline_loop import (
    BottleneckClass,
    RooflinePoint,
    classify_bottleneck,
    recommend_optimizations,
    run_optimization_iteration,
)


class TestClassifyBottleneckBoundary:
    def test_zero_arithmetic_intensity(self):
        """AI of exactly zero is memory-bound, not an error."""
        result = classify_bottleneck(
            arithmetic_intensity=0.0,
            ridge_point=10.0,
            sol_by_block={"HBM": 80.0},
        )
        assert isinstance(result, BottleneckClass)
        assert result == BottleneckClass.MEMORY_BOUND

    def test_empty_sol_by_block(self):
        """Empty SOL dict falls back to intensity-only classification."""
        result = classify_bottleneck(
            arithmetic_intensity=1.0,
            ridge_point=10.0,
            sol_by_block={},
        )
        assert isinstance(result, BottleneckClass)

    def test_intensity_exactly_at_ridge(self):
        """AI exactly equal to ridge returns a well-defined class."""
        result = classify_bottleneck(
            arithmetic_intensity=10.0,
            ridge_point=10.0,
            sol_by_block={"HBM": 50.0, "VALU": 50.0},
        )
        assert isinstance(result, BottleneckClass)


class TestRecommendOptimizationsBoundary:
    def test_every_class_returns_non_empty(self):
        for bc in BottleneckClass:
            recs = recommend_optimizations(bc)
            assert isinstance(recs, list)
            assert len(recs) > 0


class TestRunOptimizationIterationBoundary:
    def test_identical_latency_not_kept(self):
        """Zero improvement (identical latency) is a well-defined non-keep."""
        def profile_fn(src):
            return RooflinePoint(
                arithmetic_intensity=1.0,
                ridge_point=10.0,
                sol_by_block={"HBM": 90.0},
                latency_ms=10.0,
            )

        result = run_optimization_iteration(
            kernel_source="k",
            profile_fn=profile_fn,
            tune_fn=lambda s, b, r: "cand",
        )
        assert result["kept"] is False
        assert result["kernel_source"] == "k"

    def test_minimal_kernel_source(self):
        """A single-character kernel source is accepted."""
        def profile_fn(src):
            return RooflinePoint(
                arithmetic_intensity=1.0,
                ridge_point=10.0,
                sol_by_block={"HBM": 90.0},
                latency_ms=2.0,
            )

        result = run_optimization_iteration(
            kernel_source="x",
            profile_fn=profile_fn,
            tune_fn=lambda s, b, r: s,
        )
        assert isinstance(result, dict)
        assert "kept" in result
