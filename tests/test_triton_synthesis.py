"""Tests for triton_synthesis.kernel_synthesizer.

Verifies that synthesize_triton_kernel and autotune_kernel satisfy the
acceptance criteria for the GPU/Triton kernel synthesis sub-agent feature.
"""

from __future__ import annotations

import pytest

from triton_synthesis.kernel_synthesizer import autotune_kernel, synthesize_triton_kernel


class TestSynthesizeTritonKernel:
    def test_returns_string(self):
        src = synthesize_triton_kernel("softmax")
        assert isinstance(src, str)
        assert len(src) > 0

    def test_contains_triton_jit(self):
        src = synthesize_triton_kernel("softmax over matrix")
        assert "@triton.jit" in src

    def test_contains_autotune_decorator(self):
        src = synthesize_triton_kernel("matrix multiply")
        assert "@triton.autotune" in src

    def test_custom_kernel_name_in_source(self):
        src = synthesize_triton_kernel("relu activation", kernel_name="my_relu")
        assert "my_relu" in src

    def test_default_kernel_name_in_source(self):
        src = synthesize_triton_kernel("row-wise softmax")
        assert "triton_kernel" in src

    def test_spec_reflected_in_source(self):
        spec = "layer normalization for transformer"
        src = synthesize_triton_kernel(spec)
        assert spec in src

    def test_empty_spec_raises_value_error(self):
        with pytest.raises(ValueError):
            synthesize_triton_kernel("")

    def test_whitespace_spec_raises_value_error(self):
        with pytest.raises(ValueError):
            synthesize_triton_kernel("   \t\n")

    def test_non_string_spec_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(123)  # type: ignore[arg-type]

    def test_none_spec_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(None)  # type: ignore[arg-type]

    def test_long_spec_accepted(self):
        long_spec = "matrix multiply " * 50
        src = synthesize_triton_kernel(long_spec.strip())
        assert isinstance(src, str)
        assert len(src) > 0

    def test_source_contains_block_m_config(self):
        src = synthesize_triton_kernel("attention kernel")
        assert "BLOCK_M" in src

    def test_source_contains_block_n_config(self):
        src = synthesize_triton_kernel("attention kernel")
        assert "BLOCK_N" in src


class TestAutotuneKernel:
    def test_returns_dict(self):
        result = autotune_kernel()
        assert isinstance(result, dict)

    def test_returns_best_config(self):
        result = autotune_kernel()
        assert "best_config" in result
        assert isinstance(result["best_config"], dict)

    def test_returns_all_timings(self):
        result = autotune_kernel()
        assert "all_timings" in result
        assert isinstance(result["all_timings"], list)
        assert len(result["all_timings"]) > 0

    def test_returns_hardware_label(self):
        result = autotune_kernel()
        assert "hardware_label" in result
        assert isinstance(result["hardware_label"], str)
        assert len(result["hardware_label"]) > 0

    def test_best_config_has_block_params(self):
        result = autotune_kernel()
        cfg = result["best_config"]
        assert any(k in cfg for k in ("BLOCK_M", "BLOCK_N", "BLOCK_K", "num_warps", "num_stages"))

    def test_hardware_label_is_known_value(self):
        result = autotune_kernel()
        assert result["hardware_label"] in ("CUDA", "ROCm", "Triton-CPU")

    def test_none_kernel_fn_uses_synthetic_benchmark(self):
        result = autotune_kernel(None)
        assert isinstance(result["best_config"], dict)
        assert len(result["all_timings"]) > 0

    def test_callable_kernel_fn_used_for_timing(self):
        call_count = []

        def counting_kernel(**cfg):
            call_count.append(cfg)
            return 1.0

        result = autotune_kernel(counting_kernel)
        assert len(call_count) > 0
        assert result["best_config"] is not None

    def test_custom_sweep_space_respected(self):
        space = {"BLOCK_M": [32], "BLOCK_N": [64], "BLOCK_K": [128], "num_warps": [4], "num_stages": [2]}
        result = autotune_kernel(sweep_space=space)
        assert len(result["all_timings"]) == 1
        cfg = result["best_config"]
        assert cfg["BLOCK_M"] == 32
        assert cfg["BLOCK_N"] == 64

    def test_hardware_label_override(self):
        result = autotune_kernel(hardware_label="CUDA")
        assert result["hardware_label"] == "CUDA"

    def test_invalid_sweep_space_raises_value_error(self):
        with pytest.raises(ValueError):
            autotune_kernel(sweep_space="invalid")  # type: ignore[arg-type]

    def test_list_sweep_space_raises_value_error(self):
        with pytest.raises(ValueError):
            autotune_kernel(sweep_space=[64, 128])  # type: ignore[arg-type]

    def test_kernel_fn_raising_does_not_crash(self):
        def bad_fn(**cfg):
            raise RuntimeError("kernel error")

        result = autotune_kernel(bad_fn)
        assert isinstance(result, dict)
        assert "best_config" in result

    def test_all_timings_are_float_pairs(self):
        result = autotune_kernel()
        for cfg, ms in result["all_timings"]:
            assert isinstance(cfg, dict)
            assert isinstance(ms, float)


class TestIntegrationWithResearchAgent:
    def test_synthesize_triton_kernel_importable(self):
        from triton_synthesis.kernel_synthesizer import synthesize_triton_kernel as f
        assert callable(f)

    def test_autotune_kernel_importable(self):
        from triton_synthesis.kernel_synthesizer import autotune_kernel as f
        assert callable(f)

    def test_combined_synthesize_and_autotune(self):
        src = synthesize_triton_kernel("softmax kernel")
        result = autotune_kernel()
        assert isinstance(src, str)
        assert "@triton.jit" in src
        assert isinstance(result["best_config"], dict)
        assert isinstance(result["hardware_label"], str)
