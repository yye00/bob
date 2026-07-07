"""Error-path tests for rocprof_compute_roofline_loop.

Verifies that invalid inputs raise ValueError and functions do not
silently succeed on erroneous input.
"""

from __future__ import annotations

import pytest

from bob.rocprof_compute_roofline_loop import (
    classify_bottleneck,
    recommend_optimizations,
    run_optimization_iteration,
    RooflinePoint,
)


class TestClassifyBottleneckErrors:
    def test_negative_arithmetic_intensity_raises(self):
        with pytest.raises(ValueError):
            classify_bottleneck(
                arithmetic_intensity=-1.0,
                ridge_point=10.0,
                sol_by_block={"HBM": 50.0},
            )

    def test_zero_ridge_point_raises(self):
        with pytest.raises(ValueError):
            classify_bottleneck(
                arithmetic_intensity=1.0,
                ridge_point=0.0,
                sol_by_block={"HBM": 50.0},
            )

    def test_negative_ridge_point_raises(self):
        with pytest.raises(ValueError):
            classify_bottleneck(
                arithmetic_intensity=1.0,
                ridge_point=-5.0,
                sol_by_block={"HBM": 50.0},
            )

    def test_none_sol_by_block_raises(self):
        with pytest.raises((ValueError, TypeError)):
            classify_bottleneck(
                arithmetic_intensity=1.0,
                ridge_point=10.0,
                sol_by_block=None,  # type: ignore[arg-type]
            )

    def test_string_sol_by_block_raises(self):
        with pytest.raises((ValueError, TypeError)):
            classify_bottleneck(
                arithmetic_intensity=1.0,
                ridge_point=10.0,
                sol_by_block="HBM=90",  # type: ignore[arg-type]
            )


class TestRecommendOptimizationsErrors:
    def test_invalid_bottleneck_class_raises(self):
        with pytest.raises((ValueError, TypeError)):
            recommend_optimizations("memory_bound")  # type: ignore[arg-type]

    def test_none_bottleneck_raises(self):
        with pytest.raises((ValueError, TypeError)):
            recommend_optimizations(None)  # type: ignore[arg-type]


class TestRunOptimizationIterationErrors:
    def _good_profile(self, src):
        return RooflinePoint(
            arithmetic_intensity=1.0,
            ridge_point=10.0,
            sol_by_block={"HBM": 90.0},
            latency_ms=5.0,
        )

    def test_empty_kernel_source_raises(self):
        with pytest.raises(ValueError):
            run_optimization_iteration(
                kernel_source="",
                profile_fn=self._good_profile,
                tune_fn=lambda s, b, r: s,
            )

    def test_none_profile_fn_raises(self):
        with pytest.raises((ValueError, TypeError)):
            run_optimization_iteration(
                kernel_source="k",
                profile_fn=None,  # type: ignore[arg-type]
                tune_fn=lambda s, b, r: s,
            )

    def test_non_callable_tune_fn_raises(self):
        with pytest.raises((ValueError, TypeError)):
            run_optimization_iteration(
                kernel_source="k",
                profile_fn=self._good_profile,
                tune_fn="not-callable",  # type: ignore[arg-type]
            )

    def test_profile_fn_returning_wrong_type_raises(self):
        with pytest.raises((ValueError, TypeError)):
            run_optimization_iteration(
                kernel_source="k",
                profile_fn=lambda s: {"latency_ms": 5.0},  # type: ignore[return-value]
                tune_fn=lambda s, b, r: s,
            )

    def test_empty_kernel_source_does_not_silently_succeed(self):
        try:
            run_optimization_iteration(
                kernel_source="",
                profile_fn=self._good_profile,
                tune_fn=lambda s, b, r: s,
            )
            pytest.fail("Expected ValueError for empty kernel_source")
        except ValueError:
            pass
