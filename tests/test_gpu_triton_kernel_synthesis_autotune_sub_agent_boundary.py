"""Boundary-case tests for gpu_triton_kernel_synthesis.

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising exceptions.
"""

from __future__ import annotations

import pytest

from gpu_triton_kernel_synthesis import autotune_kernel_config, synthesize_triton_kernel


class TestSynthesizeTritonKernelBoundary:
    def test_minimal_spec_single_word(self):
        """Minimum meaningful spec returns a kernel source without raising."""
        src = synthesize_triton_kernel("add")
        assert isinstance(src, str)
        assert len(src) > 0

    def test_very_long_spec_does_not_raise(self):
        """A very long spec string is accepted without error."""
        long_spec = "matrix multiply " * 100
        src = synthesize_triton_kernel(long_spec.strip())
        assert isinstance(src, str)
        assert len(src) > 0

    def test_spec_with_special_characters(self):
        """Spec with special chars (parens, slashes) does not raise."""
        src = synthesize_triton_kernel("softmax(x / sqrt(d_k))")
        assert isinstance(src, str)

    def test_spec_with_unicode(self):
        """Spec with unicode characters is accepted."""
        src = synthesize_triton_kernel("softmax over matrix A∈R^{M×N}")
        assert isinstance(src, str)

    def test_default_kernel_name_in_source(self):
        """Default kernel_name='triton_kernel' appears in source."""
        src = synthesize_triton_kernel("relu")
        assert "triton_kernel" in src


class TestAutotuneKernelConfigBoundary:
    def test_none_kernel_fn_returns_valid_result(self):
        """Passing None as kernel_fn (default) returns a valid result."""
        result = autotune_kernel_config(None)
        assert isinstance(result, dict)
        assert "best_config" in result
        assert "all_timings" in result
        assert "hardware_label" in result

    def test_minimal_sweep_space_one_config(self):
        """Sweep space with single config per axis returns exactly one timing."""
        space = {
            "BLOCK_M": [32],
            "BLOCK_N": [32],
            "BLOCK_K": [32],
            "num_warps": [2],
            "num_stages": [2],
        }
        result = autotune_kernel_config(sweep_space=space)
        assert len(result["all_timings"]) == 1
        assert isinstance(result["best_config"], dict)

    def test_sweep_space_single_axis(self):
        """Sweep space with one axis still returns a best_config."""
        space = {"BLOCK_M": [64]}
        result = autotune_kernel_config(sweep_space=space)
        assert "BLOCK_M" in result["best_config"]

    def test_empty_hardware_label_override_accepted(self):
        """hardware_label=None falls back to auto-detection without raising."""
        result = autotune_kernel_config(hardware_label=None)
        assert isinstance(result["hardware_label"], str)

    def test_kernel_fn_returning_zero(self):
        """kernel_fn that returns 0.0 ms is accepted (best possible timing)."""
        result = autotune_kernel_config(lambda **_: 0.0)
        assert result["best_config"] is not None
        # All timings should be 0.0
        assert all(ms == 0.0 for _, ms in result["all_timings"])

    def test_all_timings_non_empty(self):
        """all_timings always contains at least one entry."""
        result = autotune_kernel_config()
        assert len(result["all_timings"]) >= 1
