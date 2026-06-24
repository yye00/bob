"""Tests for bob3.gpu_kernel_synthesizer.

Verifies that synthesize_triton_kernel and autotune_kernel_config are importable
from bob3.gpu_kernel_synthesizer and behave correctly.
"""

from __future__ import annotations

import pytest

from bob3.gpu_kernel_synthesizer import (
    autotune_kernel_config,
    synthesize_triton_kernel,
)


class TestSynthesizeTritonKernel:
    def test_returns_string(self):
        src = synthesize_triton_kernel("row-wise softmax over a 2-D float32 tensor")
        assert isinstance(src, str)
        assert len(src) > 0

    def test_contains_kernel_name(self):
        src = synthesize_triton_kernel("matrix multiply", kernel_name="matmul_kernel")
        assert "matmul_kernel" in src

    def test_default_kernel_name_in_source(self):
        src = synthesize_triton_kernel("relu activation")
        assert "triton_kernel" in src

    def test_empty_spec_raises_value_error(self):
        with pytest.raises(ValueError):
            synthesize_triton_kernel("")

    def test_whitespace_only_spec_raises_value_error(self):
        with pytest.raises(ValueError):
            synthesize_triton_kernel("   ")

    def test_non_string_spec_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(42)  # type: ignore[arg-type]

    def test_none_spec_raises(self):
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(None)  # type: ignore[arg-type]


class TestAutotuneKernelConfig:
    def test_returns_dict_with_required_keys(self):
        result = autotune_kernel_config()
        assert isinstance(result, dict)
        assert "best_config" in result
        assert "all_timings" in result
        assert "hardware_label" in result

    def test_best_config_is_dict(self):
        result = autotune_kernel_config()
        assert isinstance(result["best_config"], dict)

    def test_all_timings_non_empty(self):
        result = autotune_kernel_config()
        assert len(result["all_timings"]) >= 1

    def test_hardware_label_is_string(self):
        result = autotune_kernel_config()
        assert isinstance(result["hardware_label"], str)

    def test_none_kernel_fn_accepted(self):
        result = autotune_kernel_config(None)
        assert isinstance(result, dict)

    def test_custom_kernel_fn(self):
        result = autotune_kernel_config(lambda **_: 1.5)
        assert result["best_config"] is not None
        assert all(ms == 1.5 for _, ms in result["all_timings"])

    def test_minimal_sweep_space(self):
        space = {
            "BLOCK_M": [32],
            "BLOCK_N": [32],
            "BLOCK_K": [32],
            "num_warps": [2],
            "num_stages": [2],
        }
        result = autotune_kernel_config(sweep_space=space)
        assert len(result["all_timings"]) == 1

    def test_invalid_sweep_space_raises_value_error(self):
        with pytest.raises(ValueError):
            autotune_kernel_config(sweep_space="BLOCK_M=64")  # type: ignore[arg-type]

    def test_list_sweep_space_raises_value_error(self):
        with pytest.raises(ValueError):
            autotune_kernel_config(sweep_space=[64, 128])  # type: ignore[arg-type]

    def test_hardware_label_override(self):
        result = autotune_kernel_config(hardware_label="test-gpu")
        assert result["hardware_label"] == "test-gpu"

    def test_none_sweep_space_uses_default(self):
        result = autotune_kernel_config(sweep_space=None)
        assert isinstance(result, dict)
        assert len(result["all_timings"]) >= 1
