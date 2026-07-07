"""Tests for the compile-cost build-budget layer (feature 949b76df).

Covers ccache+Ninja configuration, local-GPU-arch scoping, and per-feature
compile-time ceiling enforcement.

AC: pytest: tests/test_build_budget.py
"""

from __future__ import annotations

import pytest

from bob.build_budget import (
    CcacheNinjaConfig,
    CompileBudgetExceeded,
    CompileBudgetResult,
    DEFAULT_COMPILE_CEILING_S,
    KNOWN_GPU_ARCHS,
    configure_ccache_ninja,
    enforce_compile_budget,
    scope_gpu_targets,
)


class TestConfigureCcacheNinja:
    def test_forces_ninja_generator(self) -> None:
        cfg = configure_ccache_ninja()
        assert isinstance(cfg, CcacheNinjaConfig)
        assert "-GNinja" in cfg.cmake_flags

    def test_wires_both_compiler_launchers(self) -> None:
        cfg = configure_ccache_ninja()
        assert "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache" in cfg.cmake_flags
        assert "-DCMAKE_HIP_COMPILER_LAUNCHER=ccache" in cfg.cmake_flags

    def test_sets_ccache_dir_env(self) -> None:
        cfg = configure_ccache_ninja("/tmp/my-ccache")
        assert cfg.env["CCACHE_DIR"] == "/tmp/my-ccache"
        assert cfg.ccache_dir == "/tmp/my-ccache"

    def test_expands_user_home(self) -> None:
        cfg = configure_ccache_ninja("~/somecache")
        assert not cfg.ccache_dir.startswith("~")
        assert cfg.ccache_dir.endswith("somecache")

    def test_default_dir_is_shared_persistent(self) -> None:
        cfg = configure_ccache_ninja()
        # Default is a shared cross-feature cache location.
        assert "ccache" in cfg.ccache_dir
        assert cfg.env["CCACHE_MAXSIZE"]

    def test_extends_existing_args_without_duplication(self) -> None:
        cfg = configure_ccache_ninja(cmake_args=["-DFOO=1", "-GNinja"])
        assert "-DFOO=1" in cfg.cmake_flags
        assert cfg.cmake_flags.count("-GNinja") == 1

    def test_custom_max_size(self) -> None:
        cfg = configure_ccache_ninja(max_size="5G")
        assert cfg.env["CCACHE_MAXSIZE"] == "5G"


class TestScopeGpuTargets:
    def test_single_arch(self) -> None:
        flags = scope_gpu_targets("gfx942")
        assert flags == ["-DGPU_TARGETS=gfx942"]

    def test_default_arch(self) -> None:
        flags = scope_gpu_targets()
        assert flags == ["-DGPU_TARGETS=gfx942"]

    def test_multiple_archs(self) -> None:
        flags = scope_gpu_targets(["gfx942", "gfx950"])
        assert flags == ["-DGPU_TARGETS=gfx942;gfx950"]

    def test_local_only_flag(self) -> None:
        flags = scope_gpu_targets(local_only=True)
        assert flags == ["-DBUILD_LOCAL_GPU_TARGET_ONLY=ON"]

    def test_local_only_ignores_arch(self) -> None:
        flags = scope_gpu_targets("gfx942", local_only=True)
        assert flags == ["-DBUILD_LOCAL_GPU_TARGET_ONLY=ON"]

    def test_known_archs_populated(self) -> None:
        assert "gfx942" in KNOWN_GPU_ARCHS
        assert "gfx950" in KNOWN_GPU_ARCHS


class TestEnforceCompileBudget:
    def test_within_budget(self) -> None:
        res = enforce_compile_budget(100.0, 200.0)
        assert isinstance(res, CompileBudgetResult)
        assert res.within_budget is True
        assert res.overage_s == 0.0

    def test_over_budget_returns_result(self) -> None:
        res = enforce_compile_budget(300.0, 200.0)
        assert res.within_budget is False
        assert res.overage_s == pytest.approx(100.0)

    def test_over_budget_raises_when_requested(self) -> None:
        with pytest.raises(CompileBudgetExceeded):
            enforce_compile_budget(300.0, 200.0, raise_on_exceed=True)

    def test_records_ccache_hit_rate(self) -> None:
        res = enforce_compile_budget(50.0, 200.0, ccache_hit_rate=0.9)
        assert res.ccache_hit_rate == pytest.approx(0.9)

    def test_default_ceiling_used_when_none(self) -> None:
        res = enforce_compile_budget(10.0)
        assert res.ceiling_s == DEFAULT_COMPILE_CEILING_S
        assert res.within_budget is True

    def test_exactly_at_ceiling_is_within(self) -> None:
        res = enforce_compile_budget(200.0, 200.0)
        assert res.within_budget is True
        assert res.overage_s == 0.0

    def test_env_override_ceiling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BOB_COMPILE_BUDGET_CEILING_S", "60")
        res = enforce_compile_budget(120.0)
        assert res.ceiling_s == 60.0
        assert res.within_budget is False
