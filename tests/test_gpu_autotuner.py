"""Tests for bob.gpu_autotuner."""

from __future__ import annotations

import math
import pytest

from bob.gpu_autotuner import (
    KernelConfig,
    SweepResult,
    roofline_efficiency,
    sweep,
)


# ---------------------------------------------------------------------------
# KernelConfig
# ---------------------------------------------------------------------------


class TestKernelConfig:
    def test_default_fields(self):
        cfg = KernelConfig(block_size=128, tile_size=16)
        assert cfg.block_size == 128
        assert cfg.tile_size == 16
        assert cfg.register_blocking == 1
        assert cfg.vector_width == 1

    def test_all_fields(self):
        cfg = KernelConfig(
            block_size=256, tile_size=32, register_blocking=4, vector_width=8
        )
        assert cfg.register_blocking == 4
        assert cfg.vector_width == 8

    def test_invalid_block_size_raises(self):
        with pytest.raises((ValueError, Exception)):
            KernelConfig(block_size=0, tile_size=16)

    def test_invalid_tile_size_raises(self):
        with pytest.raises((ValueError, Exception)):
            KernelConfig(block_size=128, tile_size=0)


# ---------------------------------------------------------------------------
# SweepResult
# ---------------------------------------------------------------------------


class TestSweepResult:
    def test_fields(self):
        cfg = KernelConfig(block_size=128, tile_size=16)
        result = SweepResult(
            config=cfg,
            runtime_ms=5.0,
            occupancy=0.75,
            cache_hit_rate=0.9,
        )
        assert result.config is cfg
        assert result.runtime_ms == pytest.approx(5.0)
        assert result.occupancy == pytest.approx(0.75)
        assert result.cache_hit_rate == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# roofline_efficiency
# ---------------------------------------------------------------------------


class TestRooflineEfficiency:
    def test_perfect_efficiency(self):
        # achieved == theoretical -> efficiency 1.0
        eff = roofline_efficiency(
            achieved_flops=1e12,
            theoretical_peak_flops=1e12,
            achieved_bandwidth=1e11,
            theoretical_peak_bandwidth=1e11,
            arithmetic_intensity=10.0,
        )
        assert eff == pytest.approx(1.0)

    def test_half_efficiency_compute_bound(self):
        # compute bound: achieved = half of peak compute
        eff = roofline_efficiency(
            achieved_flops=5e11,
            theoretical_peak_flops=1e12,
            achieved_bandwidth=1e11,
            theoretical_peak_bandwidth=1e11,
            arithmetic_intensity=100.0,
        )
        assert 0.0 < eff <= 1.0
        assert eff == pytest.approx(0.5)

    def test_half_efficiency_memory_bound(self):
        # memory bound: achieved bandwidth = half of peak
        eff = roofline_efficiency(
            achieved_flops=5e9,
            theoretical_peak_flops=1e12,
            achieved_bandwidth=5e10,
            theoretical_peak_bandwidth=1e11,
            arithmetic_intensity=0.1,
        )
        assert 0.0 < eff <= 1.0
        assert eff == pytest.approx(0.5)

    def test_efficiency_clamped_to_one(self):
        # Efficiency should never exceed 1.0 due to measurement noise
        eff = roofline_efficiency(
            achieved_flops=1.1e12,
            theoretical_peak_flops=1e12,
            achieved_bandwidth=1e11,
            theoretical_peak_bandwidth=1e11,
            arithmetic_intensity=100.0,
        )
        assert eff <= 1.0

    def test_zero_flops_raises_or_zero(self):
        # A zero achieved_flops indicates no work done — should return 0.0
        eff = roofline_efficiency(
            achieved_flops=0.0,
            theoretical_peak_flops=1e12,
            achieved_bandwidth=0.0,
            theoretical_peak_bandwidth=1e11,
            arithmetic_intensity=10.0,
        )
        assert eff == pytest.approx(0.0)

    def test_invalid_peak_raises(self):
        with pytest.raises((ValueError, ZeroDivisionError)):
            roofline_efficiency(
                achieved_flops=1e12,
                theoretical_peak_flops=0.0,
                achieved_bandwidth=1e11,
                theoretical_peak_bandwidth=1e11,
                arithmetic_intensity=10.0,
            )


# ---------------------------------------------------------------------------
# sweep
# ---------------------------------------------------------------------------


class _FakeRunner:
    """Fake kernel runner for testing sweep without GPU hardware."""

    def __call__(self, config: KernelConfig) -> dict:
        # Faster with larger blocks (simulated)
        base_ms = 100.0 / config.block_size
        return {
            "runtime_ms": base_ms,
            "occupancy": min(1.0, config.block_size / 256),
            "cache_hit_rate": min(1.0, config.tile_size / 32),
        }


class TestSweep:
    def _param_grid(self):
        return {
            "block_size": [64, 128, 256],
            "tile_size": [8, 16],
            "register_blocking": [1, 2],
            "vector_width": [1],
        }

    def test_returns_list_of_sweep_results(self):
        results = sweep(
            kernel_runner=_FakeRunner(),
            param_grid=self._param_grid(),
        )
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, SweepResult) for r in results)

    def test_all_configs_evaluated(self):
        grid = self._param_grid()
        expected_count = (
            len(grid["block_size"])
            * len(grid["tile_size"])
            * len(grid["register_blocking"])
            * len(grid["vector_width"])
        )
        results = sweep(kernel_runner=_FakeRunner(), param_grid=grid)
        assert len(results) == expected_count

    def test_results_have_metrics(self):
        results = sweep(kernel_runner=_FakeRunner(), param_grid=self._param_grid())
        for r in results:
            assert r.runtime_ms > 0
            assert 0.0 <= r.occupancy <= 1.0
            assert 0.0 <= r.cache_hit_rate <= 1.0

    def test_sweep_with_minimal_grid(self):
        results = sweep(
            kernel_runner=_FakeRunner(),
            param_grid={
                "block_size": [128],
                "tile_size": [16],
                "register_blocking": [1],
                "vector_width": [1],
            },
        )
        assert len(results) == 1
        assert results[0].config.block_size == 128

    def test_empty_grid_returns_empty(self):
        results = sweep(
            kernel_runner=_FakeRunner(),
            param_grid={"block_size": [], "tile_size": [16]},
        )
        assert results == []


# ---------------------------------------------------------------------------
# Pareto frontier
# ---------------------------------------------------------------------------


class TestParetoFrontier:
    """Tests for the pareto_frontier function."""

    def test_import(self):
        from bob.gpu_autotuner import pareto_frontier
        assert callable(pareto_frontier)

    def test_single_result_is_pareto(self):
        from bob.gpu_autotuner import pareto_frontier
        cfg = KernelConfig(block_size=128, tile_size=16)
        r = SweepResult(config=cfg, runtime_ms=5.0, occupancy=0.8, cache_hit_rate=0.9)
        frontier = pareto_frontier([r])
        assert len(frontier) == 1
        assert frontier[0] is r

    def test_dominated_result_excluded(self):
        from bob.gpu_autotuner import pareto_frontier
        # r1 dominates r2: lower runtime AND higher occupancy
        r1 = SweepResult(
            config=KernelConfig(block_size=256, tile_size=16),
            runtime_ms=2.0, occupancy=0.9, cache_hit_rate=0.8,
        )
        r2 = SweepResult(
            config=KernelConfig(block_size=64, tile_size=16),
            runtime_ms=10.0, occupancy=0.5, cache_hit_rate=0.5,
        )
        frontier = pareto_frontier([r1, r2])
        assert r1 in frontier
        assert r2 not in frontier

    def test_tradeoff_both_on_frontier(self):
        from bob.gpu_autotuner import pareto_frontier
        # r1: fast but low occupancy; r2: slow but high occupancy — neither dominates
        r1 = SweepResult(
            config=KernelConfig(block_size=256, tile_size=16),
            runtime_ms=2.0, occupancy=0.4, cache_hit_rate=0.7,
        )
        r2 = SweepResult(
            config=KernelConfig(block_size=64, tile_size=16),
            runtime_ms=10.0, occupancy=0.9, cache_hit_rate=0.9,
        )
        frontier = pareto_frontier([r1, r2])
        assert r1 in frontier
        assert r2 in frontier

    def test_empty_input(self):
        from bob.gpu_autotuner import pareto_frontier
        assert pareto_frontier([]) == []


# ---------------------------------------------------------------------------
# Integration with enhanced_verification
# ---------------------------------------------------------------------------


class TestEnhancedVerificationIntegration:
    """Verify the module is importable from the project and wired correctly."""

    def test_module_importable(self):
        import bob.gpu_autotuner as ga
        assert hasattr(ga, "sweep")
        assert hasattr(ga, "roofline_efficiency")

    def test_sweep_callable(self):
        from bob.gpu_autotuner import sweep
        assert callable(sweep)

    def test_roofline_efficiency_callable(self):
        from bob.gpu_autotuner import roofline_efficiency
        assert callable(roofline_efficiency)

    def test_enhanced_verification_importable(self):
        # Ensure enhanced_verification is importable (integration criterion)
        import bob.enhanced_verification
        assert bob.enhanced_verification is not None
