"""Error-path tests for gpu_triton_kernel_synthesis.

Verifies that invalid inputs raise ValueError and functions do not
silently succeed on erroneous input.
"""

from __future__ import annotations

import pytest

from gpu_triton_kernel_synthesis import autotune_kernel_config, synthesize_triton_kernel


class TestSynthesizeTritonKernelErrors:
    def test_empty_spec_raises_value_error(self):
        """Empty string spec must raise ValueError."""
        with pytest.raises(ValueError):
            synthesize_triton_kernel("")

    def test_whitespace_only_spec_raises_value_error(self):
        """Whitespace-only spec must raise ValueError, not return silently."""
        with pytest.raises(ValueError):
            synthesize_triton_kernel("   \t\n")

    def test_integer_spec_raises(self):
        """Non-string spec type must raise ValueError or TypeError, not succeed."""
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(42)  # type: ignore[arg-type]

    def test_none_spec_raises(self):
        """None spec must raise ValueError or TypeError, not succeed."""
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(None)  # type: ignore[arg-type]

    def test_list_spec_raises(self):
        """List spec must raise ValueError or TypeError, not succeed."""
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(["softmax"])  # type: ignore[arg-type]

    def test_empty_spec_does_not_return_empty_string(self):
        """Empty spec must not silently return an empty string."""
        try:
            result = synthesize_triton_kernel("")
            # If it somehow doesn't raise, the result must not be an empty string
            assert result != "", "Empty spec silently returned empty string"
            pytest.fail("Expected ValueError for empty spec but got a result")
        except ValueError:
            pass  # Expected path


class TestAutotuneKernelConfigErrors:
    def test_string_sweep_space_raises_value_error(self):
        """String sweep_space must raise ValueError."""
        with pytest.raises(ValueError):
            autotune_kernel_config(sweep_space="BLOCK_M=64")  # type: ignore[arg-type]

    def test_list_sweep_space_raises_value_error(self):
        """List sweep_space must raise ValueError, not succeed."""
        with pytest.raises(ValueError):
            autotune_kernel_config(sweep_space=[64, 128])  # type: ignore[arg-type]

    def test_integer_sweep_space_raises_value_error(self):
        """Integer sweep_space must raise ValueError."""
        with pytest.raises(ValueError):
            autotune_kernel_config(sweep_space=64)  # type: ignore[arg-type]

    def test_none_sweep_space_does_not_raise(self):
        """None sweep_space is valid (uses default), must not raise."""
        result = autotune_kernel_config(sweep_space=None)
        assert isinstance(result, dict)

    def test_kernel_fn_raising_exception_does_not_crash(self):
        """kernel_fn that always raises must not crash the autotune harness."""
        def bad_kernel(**cfg):
            raise RuntimeError("kernel error")

        result = autotune_kernel_config(bad_kernel)
        # Should still return a result (with inf timings)
        assert isinstance(result, dict)
        assert "best_config" in result
        assert "all_timings" in result
