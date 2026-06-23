"""Triton kernel synthesis package.

Provides GPU/Triton kernel synthesis and autotuning for features that reference
GPU, CUDA, ROCm, or ``@triton.jit`` in their acceptance criteria.
"""

from triton_synthesis.kernel_synthesizer import autotune_kernel, synthesize_triton_kernel

__all__ = ["synthesize_triton_kernel", "autotune_kernel"]
