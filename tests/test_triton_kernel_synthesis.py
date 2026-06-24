"""Tests for bob.triton_kernel_synthesis (feature 6cc31a74).

Covers synthesize_and_autotune and verify_numerical_correctness.
"""

from __future__ import annotations

import pytest

from bob.triton_kernel_synthesis import synthesize_and_autotune, verify_numerical_correctness
from bob.implementers.triton_kernel import NumericalGateError


class TestSynthesizeAndAutotune:
    def test_returns_dict_with_required_keys(self):
        result = synthesize_and_autotune("row-wise softmax over a 2-D float32 tensor")
        assert isinstance(result, dict)
        for key in ("kernel_source", "best_config", "all_timings", "hardware_label",
                    "numerical_report", "passed_gate", "config_path"):
            assert key in result, f"Missing key: {key}"

    def test_kernel_source_contains_triton_jit(self):
        result = synthesize_and_autotune("matrix multiply")
        assert "@triton.jit" in result["kernel_source"]

    def test_kernel_source_contains_autotune(self):
        result = synthesize_and_autotune("relu activation")
        assert "@triton.autotune" in result["kernel_source"]

    def test_best_config_is_dict(self):
        result = synthesize_and_autotune("softmax")
        assert isinstance(result["best_config"], dict)

    def test_all_timings_non_empty(self):
        result = synthesize_and_autotune("layer norm")
        assert len(result["all_timings"]) >= 1

    def test_hardware_label_is_string(self):
        result = synthesize_and_autotune("gelu")
        assert isinstance(result["hardware_label"], str)
        assert result["hardware_label"] in ("CUDA", "ROCm", "Triton-CPU")

    def test_numerical_report_keys(self):
        result = synthesize_and_autotune("add")
        nr = result["numerical_report"]
        assert "max_abs_err" in nr
        assert "max_rel_err" in nr

    def test_passed_gate_true_for_zero_error(self):
        result = synthesize_and_autotune(
            "softmax",
            kernel_output=[1.0, 2.0],
            reference_output=[1.0, 2.0],
        )
        assert result["passed_gate"] is True

    def test_passed_gate_false_when_tolerances_exceeded(self):
        result = synthesize_and_autotune(
            "softmax",
            kernel_output=[100.0],
            reference_output=[0.0],
            atol=1e-5,
            rtol=1e-5,
        )
        assert result["passed_gate"] is False

    def test_config_path_none_when_no_feature_id(self):
        result = synthesize_and_autotune("add", feature_id="")
        assert result["config_path"] is None

    def test_config_path_set_when_feature_id_given(self, tmp_path):
        result = synthesize_and_autotune(
            "softmax",
            feature_id="test-feat-abc",
            runs_root=tmp_path,
        )
        assert result["config_path"] is not None
        assert "triton_config.yaml" in result["config_path"]

    def test_custom_sweep_space_one_config(self):
        space = {
            "BLOCK_M": [32],
            "BLOCK_N": [32],
            "BLOCK_K": [32],
            "num_warps": [2],
            "num_stages": [2],
        }
        result = synthesize_and_autotune("softmax", sweep_space=space)
        assert len(result["all_timings"]) == 1

    def test_raises_value_error_for_empty_spec(self):
        with pytest.raises(ValueError):
            synthesize_and_autotune("")

    def test_raises_value_error_for_whitespace_spec(self):
        with pytest.raises(ValueError):
            synthesize_and_autotune("   ")

    def test_raises_value_error_for_non_string_spec(self):
        with pytest.raises(ValueError):
            synthesize_and_autotune(42)  # type: ignore[arg-type]

    def test_raises_value_error_for_invalid_sweep_space(self):
        with pytest.raises(ValueError):
            synthesize_and_autotune("softmax", sweep_space="bad")  # type: ignore[arg-type]


class TestVerifyNumericalCorrectness:
    def test_returns_dict_with_required_keys(self):
        result = verify_numerical_correctness([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert "max_abs_err" in result
        assert "max_rel_err" in result
        assert "passed" in result

    def test_passed_true_for_identical_outputs(self):
        result = verify_numerical_correctness([0.5, 0.5], [0.5, 0.5])
        assert result["passed"] is True
        assert result["max_abs_err"] == pytest.approx(0.0)

    def test_passed_true_within_tolerance(self):
        result = verify_numerical_correctness([1.0 + 1e-7], [1.0], atol=1e-5, rtol=1e-5)
        assert result["passed"] is True

    def test_raises_numerical_gate_error_when_exceeded(self):
        with pytest.raises(NumericalGateError):
            verify_numerical_correctness([100.0], [0.0], atol=1e-5, rtol=1e-5)

    def test_max_abs_err_computed_correctly(self):
        result = verify_numerical_correctness([1.1], [1.0], atol=1.0, rtol=1.0)
        assert result["max_abs_err"] == pytest.approx(0.1, rel=1e-4)

    def test_scalar_list_inputs(self):
        result = verify_numerical_correctness([0.0], [0.0])
        assert result["passed"] is True
        assert result["max_abs_err"] == pytest.approx(0.0)

    def test_nested_list_inputs(self):
        result = verify_numerical_correctness([[1.0, 2.0], [3.0, 4.0]],
                                              [[1.0, 2.0], [3.0, 4.0]])
        assert result["passed"] is True
