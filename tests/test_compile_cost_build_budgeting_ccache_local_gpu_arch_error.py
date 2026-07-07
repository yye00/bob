"""Error-path tests for the compile-cost build-budget layer (949b76df).

Invalid input raises ValueError and the function does not silently succeed.

AC: pytest: tests/test_compile_cost_build_budgeting_ccache_local_gpu_arch_error.py
"""

from __future__ import annotations

import pytest

from bob.build_budget import (
    configure_ccache_ninja,
    enforce_compile_budget,
    scope_gpu_targets,
)


class TestConfigureErrors:
    def test_bad_ccache_dir_type_raises(self) -> None:
        with pytest.raises(ValueError):
            configure_ccache_ninja(123)  # type: ignore[arg-type]

    def test_empty_ccache_dir_raises(self) -> None:
        with pytest.raises(ValueError):
            configure_ccache_ninja("   ")

    def test_bad_cmake_args_type_raises(self) -> None:
        with pytest.raises(ValueError):
            configure_ccache_ninja(cmake_args="-GNinja")  # type: ignore[arg-type]

    def test_cmake_args_non_str_element_raises(self) -> None:
        with pytest.raises(ValueError):
            configure_ccache_ninja(cmake_args=[1, 2])  # type: ignore[list-item]

    def test_empty_max_size_raises(self) -> None:
        with pytest.raises(ValueError):
            configure_ccache_ninja(max_size="  ")


class TestScopeErrors:
    def test_unknown_arch_raises(self) -> None:
        with pytest.raises(ValueError):
            scope_gpu_targets("gfx999")

    def test_empty_arch_raises(self) -> None:
        with pytest.raises(ValueError):
            scope_gpu_targets("")

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError):
            scope_gpu_targets([])

    def test_bad_arch_type_raises(self) -> None:
        with pytest.raises(ValueError):
            scope_gpu_targets(942)  # type: ignore[arg-type]

    def test_list_with_unknown_arch_raises(self) -> None:
        with pytest.raises(ValueError):
            scope_gpu_targets(["gfx942", "gfxbad"])


class TestEnforceErrors:
    def test_non_number_wall_clock_raises(self) -> None:
        with pytest.raises(ValueError):
            enforce_compile_budget("100")  # type: ignore[arg-type]

    def test_bool_wall_clock_raises(self) -> None:
        with pytest.raises(ValueError):
            enforce_compile_budget(True)  # type: ignore[arg-type]

    def test_negative_wall_clock_raises(self) -> None:
        with pytest.raises(ValueError):
            enforce_compile_budget(-1.0)

    def test_non_positive_ceiling_raises(self) -> None:
        with pytest.raises(ValueError):
            enforce_compile_budget(10.0, 0.0)

    def test_hit_rate_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            enforce_compile_budget(10.0, 200.0, ccache_hit_rate=1.5)

    def test_hit_rate_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            enforce_compile_budget(10.0, 200.0, ccache_hit_rate=-0.1)
