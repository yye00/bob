"""Boundary-case tests for the compile-cost build-budget layer (949b76df).

Empty, zero, or minimum input returns a well-defined result rather than raising.

AC: pytest: tests/test_compile_cost_build_budgeting_ccache_local_gpu_arch_boundary.py
"""

from __future__ import annotations

from bob.build_budget import (
    CcacheNinjaConfig,
    configure_ccache_ninja,
    enforce_compile_budget,
    scope_gpu_targets,
)


class TestBoundary:
    def test_configure_with_empty_cmake_args(self) -> None:
        cfg = configure_ccache_ninja(cmake_args=[])
        assert isinstance(cfg, CcacheNinjaConfig)
        assert "-GNinja" in cfg.cmake_flags

    def test_configure_defaults_all_none(self) -> None:
        cfg = configure_ccache_ninja()
        assert cfg.ccache_dir
        assert cfg.cmake_flags

    def test_scope_defaults(self) -> None:
        flags = scope_gpu_targets()
        assert flags and flags[0].startswith("-DGPU_TARGETS=")

    def test_zero_wall_clock_within_budget(self) -> None:
        res = enforce_compile_budget(0.0, 200.0)
        assert res.within_budget is True
        assert res.overage_s == 0.0
        assert res.wall_clock_s == 0.0

    def test_zero_hit_rate_accepted(self) -> None:
        res = enforce_compile_budget(10.0, 200.0, ccache_hit_rate=0.0)
        assert res.ccache_hit_rate == 0.0

    def test_full_hit_rate_accepted(self) -> None:
        res = enforce_compile_budget(10.0, 200.0, ccache_hit_rate=1.0)
        assert res.ccache_hit_rate == 1.0

    def test_ceiling_none_returns_default(self) -> None:
        res = enforce_compile_budget(0.0)
        assert res.within_budget is True
        assert res.ceiling_s > 0
