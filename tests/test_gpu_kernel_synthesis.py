"""Tests for bob73.gpu_kernel_synthesis module.

Covers synthesize_triton_kernel and autotune_kernel_config public API as
exposed through the bob73 package.
"""

from __future__ import annotations

import pytest

from bob73.gpu_kernel_synthesis import autotune_kernel_config, synthesize_triton_kernel


class TestSynthesizeTritonKernel:
    def test_returns_string(self):
        src = synthesize_triton_kernel("row-wise softmax over a 2-D float32 tensor")
        assert isinstance(src, str)
        assert len(src) > 0

    def test_contains_triton_jit(self):
        src = synthesize_triton_kernel("matrix multiply")
        assert "@triton.jit" in src

    def test_contains_triton_autotune(self):
        src = synthesize_triton_kernel("layer normalization")
        assert "@triton.autotune" in src

    def test_contains_block_m_param(self):
        src = synthesize_triton_kernel("softmax kernel")
        assert "BLOCK_M" in src

    def test_contains_block_n_param(self):
        src = synthesize_triton_kernel("attention kernel")
        assert "BLOCK_N" in src

    def test_contains_block_k_param(self):
        src = synthesize_triton_kernel("matmul kernel")
        assert "BLOCK_K" in src

    def test_custom_kernel_name(self):
        src = synthesize_triton_kernel("softmax", kernel_name="my_softmax")
        assert "my_softmax" in src

    def test_spec_appears_in_source(self):
        spec = "fused relu-matmul"
        src = synthesize_triton_kernel(spec)
        assert spec in src

    def test_launcher_function_present(self):
        src = synthesize_triton_kernel("softmax", kernel_name="softmax_kernel")
        assert "def softmax_kernel(" in src

    def test_raises_for_empty_spec(self):
        with pytest.raises(ValueError):
            synthesize_triton_kernel("")

    def test_raises_for_whitespace_spec(self):
        with pytest.raises(ValueError):
            synthesize_triton_kernel("   ")

    def test_raises_for_non_string_spec(self):
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(123)  # type: ignore[arg-type]


class TestAutotuneKernelConfig:
    def test_returns_dict(self):
        result = autotune_kernel_config()
        assert isinstance(result, dict)

    def test_has_best_config(self):
        result = autotune_kernel_config()
        assert "best_config" in result
        assert isinstance(result["best_config"], dict)

    def test_has_all_timings(self):
        result = autotune_kernel_config()
        assert "all_timings" in result
        assert isinstance(result["all_timings"], list)
        assert len(result["all_timings"]) > 0

    def test_has_hardware_label(self):
        result = autotune_kernel_config()
        assert "hardware_label" in result
        assert isinstance(result["hardware_label"], str)
        assert len(result["hardware_label"]) > 0

    def test_best_config_contains_block_params(self):
        result = autotune_kernel_config()
        cfg = result["best_config"]
        assert any(k in cfg for k in ("BLOCK_M", "BLOCK_N", "BLOCK_K", "num_warps", "num_stages"))

    def test_hardware_label_known_value(self):
        result = autotune_kernel_config()
        assert result["hardware_label"] in ("CUDA", "ROCm", "Triton-CPU")

    def test_custom_sweep_space(self):
        space = {
            "BLOCK_M": [16, 32],
            "BLOCK_N": [16, 32],
            "BLOCK_K": [16],
            "num_warps": [2],
            "num_stages": [2],
        }
        result = autotune_kernel_config(sweep_space=space)
        assert isinstance(result["best_config"], dict)
        assert len(result["all_timings"]) == 2 * 2 * 1 * 1 * 1

    def test_custom_hardware_label(self):
        result = autotune_kernel_config(hardware_label="CUDA")
        assert result["hardware_label"] == "CUDA"

    def test_callable_kernel_fn(self):
        call_count = [0]

        def fake_kernel(**cfg):
            call_count[0] += 1
            return 1.0

        result = autotune_kernel_config(fake_kernel)
        assert call_count[0] > 0
        assert isinstance(result["best_config"], dict)

    def test_raises_for_invalid_sweep_space(self):
        with pytest.raises(ValueError):
            autotune_kernel_config(sweep_space="not-a-dict")  # type: ignore[arg-type]

    def test_all_timings_is_list_of_tuples_or_pairs(self):
        result = autotune_kernel_config()
        for entry in result["all_timings"]:
            assert len(entry) == 2
            cfg, ms = entry
            assert isinstance(cfg, dict)
            assert isinstance(ms, float)
