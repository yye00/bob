"""Tests for bob.triton_kernel_synthesizer."""

from __future__ import annotations

import pytest

from bob.triton_kernel_synthesizer import (
    autotune_kernel_config,
    synthesize_triton_kernel,
    verify_numerical_correctness,
)


class TestSynthesizeTritonKernel:
    def test_returns_string(self):
        src = synthesize_triton_kernel("softmax")
        assert isinstance(src, str)

    def test_source_nonempty(self):
        src = synthesize_triton_kernel("relu")
        assert len(src) > 0

    def test_source_contains_triton_jit(self):
        src = synthesize_triton_kernel("matrix multiply")
        assert "@triton.jit" in src or "triton" in src

    def test_default_kernel_name_in_source(self):
        src = synthesize_triton_kernel("layer norm")
        assert "triton_kernel" in src

    def test_custom_kernel_name_in_source(self):
        src = synthesize_triton_kernel("flash attention", kernel_name="flash_attn")
        assert "flash_attn" in src

    def test_empty_spec_raises(self):
        with pytest.raises(ValueError):
            synthesize_triton_kernel("")

    def test_whitespace_spec_raises(self):
        with pytest.raises(ValueError):
            synthesize_triton_kernel("   ")

    def test_non_string_spec_raises(self):
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(None)  # type: ignore[arg-type]

    def test_integer_spec_raises(self):
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(42)  # type: ignore[arg-type]

    def test_long_spec_accepted(self):
        src = synthesize_triton_kernel("matrix multiply " * 50)
        assert isinstance(src, str)
        assert len(src) > 0


class TestAutotuneKernelConfig:
    def test_returns_dict(self):
        result = autotune_kernel_config()
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = autotune_kernel_config()
        assert "best_config" in result
        assert "all_timings" in result
        assert "hardware_label" in result

    def test_best_config_is_dict(self):
        result = autotune_kernel_config()
        assert isinstance(result["best_config"], dict)

    def test_all_timings_nonempty(self):
        result = autotune_kernel_config()
        assert len(result["all_timings"]) >= 1

    def test_hardware_label_is_string(self):
        result = autotune_kernel_config()
        assert isinstance(result["hardware_label"], str)

    def test_none_kernel_fn_returns_synthetic(self):
        result = autotune_kernel_config(None)
        assert result["best_config"] is not None

    def test_custom_sweep_space(self):
        space = {"BLOCK_M": [32], "BLOCK_N": [64], "BLOCK_K": [32], "num_warps": [4], "num_stages": [2]}
        result = autotune_kernel_config(sweep_space=space)
        assert len(result["all_timings"]) == 1
        assert "BLOCK_M" in result["best_config"]

    def test_invalid_sweep_space_raises(self):
        with pytest.raises(ValueError):
            autotune_kernel_config(sweep_space="bad")  # type: ignore[arg-type]

    def test_invalid_sweep_space_list_raises(self):
        with pytest.raises(ValueError):
            autotune_kernel_config(sweep_space=[32, 64])  # type: ignore[arg-type]

    def test_hardware_label_override(self):
        result = autotune_kernel_config(hardware_label="Triton-CPU")
        assert result["hardware_label"] == "Triton-CPU"

    def test_kernel_fn_returning_zero(self):
        result = autotune_kernel_config(lambda **_: 0.0)
        assert all(ms == 0.0 for _, ms in result["all_timings"])


class TestVerifyNumericalCorrectness:
    def test_identical_inputs_pass(self):
        result = verify_numerical_correctness([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert result["passed"] is True
        assert result["max_abs_err"] == pytest.approx(0.0)

    def test_returns_dict_with_required_keys(self):
        result = verify_numerical_correctness([1.0], [1.0])
        assert "max_abs_err" in result
        assert "max_rel_err" in result
        assert "passed" in result

    def test_large_error_fails_gate(self):
        result = verify_numerical_correctness([0.0], [1.0], atol=1e-5, rtol=1e-5)
        assert result["passed"] is False
        assert result["max_abs_err"] == pytest.approx(1.0)

    def test_small_error_within_atol_passes(self):
        result = verify_numerical_correctness([1.0], [1.0 + 1e-7], atol=1e-5, rtol=1e-4)
        assert result["passed"] is True

    def test_none_kernel_output_raises(self):
        with pytest.raises(ValueError):
            verify_numerical_correctness(None, [1.0])  # type: ignore[arg-type]

    def test_none_reference_output_raises(self):
        with pytest.raises(ValueError):
            verify_numerical_correctness([1.0], None)  # type: ignore[arg-type]

    def test_max_abs_err_correct(self):
        result = verify_numerical_correctness([1.0, 2.0], [1.0, 2.5], atol=1.0)
        assert result["max_abs_err"] == pytest.approx(0.5)

    def test_custom_tolerances(self):
        result = verify_numerical_correctness([1.0], [1.0 + 0.1], atol=0.2, rtol=1.0)
        assert result["passed"] is True
