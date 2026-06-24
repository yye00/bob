"""Tests for autotune_kernel — verifies it selects the minimum-timing config."""

from __future__ import annotations

import bob3.implementers.triton_kernel as tk
from bob3.implementers.triton_kernel import AutotuneResult


class TestAutotunePicksBestConfig:
    def test_returns_autotune_result(self):
        result = tk.autotune_kernel(None)
        assert isinstance(result, AutotuneResult)

    def test_best_config_is_dict(self):
        result = tk.autotune_kernel(None)
        assert isinstance(result.best_config, dict)

    def test_all_timings_is_list(self):
        result = tk.autotune_kernel(None)
        assert isinstance(result.all_timings, list)

    def test_all_timings_nonempty(self):
        result = tk.autotune_kernel(None)
        assert len(result.all_timings) > 0

    def test_hardware_label_is_string(self):
        result = tk.autotune_kernel(None)
        assert isinstance(result.hardware_label, str)

    def test_hardware_label_in_fallback_order(self):
        result = tk.autotune_kernel(None)
        assert result.hardware_label in tk.hardware_fallback_order()

    def test_best_config_has_block_m(self):
        result = tk.autotune_kernel(None)
        assert "BLOCK_M" in result.best_config

    def test_best_config_has_num_warps(self):
        result = tk.autotune_kernel(None)
        assert "num_warps" in result.best_config

    def test_picks_minimum_timing(self):
        """When kernel_fn always returns a fixed ms for one config, that one is best."""
        target_config = {"BLOCK_M": 32, "BLOCK_N": 32, "BLOCK_K": 32, "num_warps": 2, "num_stages": 2}

        def fake_kernel(**cfg):
            if (cfg.get("BLOCK_M") == 32 and cfg.get("BLOCK_N") == 32
                    and cfg.get("BLOCK_K") == 32
                    and cfg.get("num_warps") == 2 and cfg.get("num_stages") == 2):
                return 0.001  # fastest
            return 100.0

        result = tk.autotune_kernel(fake_kernel)
        assert result.best_config == target_config

    def test_custom_sweep_space_used(self):
        tiny_space = {"BLOCK_M": [64], "BLOCK_N": [64], "BLOCK_K": [64],
                      "num_warps": [4], "num_stages": [3]}
        result = tk.autotune_kernel(None, sweep_space=tiny_space)
        assert len(result.all_timings) == 1
        assert result.best_config["BLOCK_M"] == 64

    def test_hardware_label_override(self):
        result = tk.autotune_kernel(None, hardware_label="CUDA")
        assert result.hardware_label == "CUDA"
