"""GPU/Triton kernel synthesis + autotune for bob.

Canonical module for GPU kernel synthesis — AC-required entry point for
feature 81c05422-5835-4628-8f96-4bb47c7199a0.

When a feature's AC mentions GPU keywords (triton, cuda, rocm, @triton.jit,
GPU kernel), the orchestrator routes through :func:`synthesize_triton_kernel`
and :func:`autotune_kernel_config` to synthesize and autotune a Triton kernel,
persists the winning config, and gates on numerical correctness vs a CPU torch
reference.

Uses a direct file-path import for triton_kernel to avoid triggering the
bob.implementers.__init__ → bob.orchestrator circular import chain.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

# Direct file-path load to avoid triggering bob.implementers.__init__,
# which imports bob.orchestrator.plan_gate, which imports bob.orchestrator,
# which would then try to import this module again before it is fully ready.
_TRITON_KERNEL_PATH = Path(__file__).parent / "implementers" / "triton_kernel.py"
if "bob.implementers.triton_kernel" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "bob.implementers.triton_kernel", _TRITON_KERNEL_PATH
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["bob.implementers.triton_kernel"] = _mod
    _spec.loader.exec_module(_mod)

from bob.implementers.triton_kernel import (  # noqa: E402
    AutotuneResult,
    NumericalGateError,
    NumericalReport,
    autotune_kernel,
    default_sweep_space,
    gate_on_numerical_correctness,
    is_gpu_feature,
    persist_winning_config,
    synthesize_kernel,
    verify_numerical,
)

__all__ = [
    "synthesize_triton_kernel",
    "autotune_kernel_config",
    "validate_against_cpu_reference",
    "is_gpu_feature",
    "default_sweep_space",
    "gate_on_numerical_correctness",
    "persist_winning_config",
    "verify_numerical",
    "AutotuneResult",
    "NumericalGateError",
    "NumericalReport",
]


def synthesize_triton_kernel(
    spec: str,
    *,
    kernel_name: str = "triton_kernel",
) -> str:
    """Synthesize a ``@triton.jit`` kernel source from a natural-language spec.

    The returned source contains:

    - A ``@triton.autotune`` decorator over the default sweep space
      (BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages).
    - A ``@triton.jit`` kernel body derived from *spec*.
    - A Python launcher function.

    When Triton is not installed the returned source is still valid Python;
    the kernel raises ``ImportError`` only when called on hardware.

    Args:
        spec: Human-readable description of the kernel operation (e.g.
              "row-wise softmax over a 2-D float32 tensor").
        kernel_name: Base name for the generated kernel function.

    Returns:
        Python source string containing the ``@triton.jit`` kernel and a
        matching Python launcher.

    Raises:
        ValueError: If *spec* is empty or not a string.
    """
    if not isinstance(spec, str):
        raise ValueError(f"spec must be a string, got {type(spec).__name__!r}")
    if not spec.strip():
        raise ValueError("spec must not be empty")

    return synthesize_kernel(spec, kernel_name=kernel_name)


def autotune_kernel_config(
    kernel_fn: Any = None,
    *,
    sweep_space: dict[str, list[int]] | None = None,
    hardware_label: str | None = None,
) -> dict[str, Any]:
    """Sweep autotune configurations and return the best one.

    Runs a benchmark over *sweep_space* (defaulting to the standard
    BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages grid) on *kernel_fn* and
    returns the fastest configuration along with timing data.

    When *kernel_fn* is ``None`` or no GPU is available, a deterministic
    synthetic benchmark is used so the function is testable without hardware.

    Args:
        kernel_fn: Callable accepting keyword config arguments and returning a
                   timing in ms.  ``None`` triggers the synthetic benchmark.
        sweep_space: Config grid to sweep.  Defaults to
                     ``default_sweep_space()``.
        hardware_label: Override for the hardware label string.  When ``None``,
                        auto-detected from the visible accelerator.

    Returns:
        A dict with:

        - ``best_config`` (dict): Winning configuration.
        - ``all_timings`` (list): All ``(config, ms)`` timing pairs.
        - ``hardware_label`` (str): Detected or overridden hardware label.

    Raises:
        ValueError: If *sweep_space* is provided but is not a dict.
    """
    if sweep_space is not None and not isinstance(sweep_space, dict):
        raise ValueError(
            f"sweep_space must be a dict or None, got {type(sweep_space).__name__!r}"
        )

    result: AutotuneResult = autotune_kernel(
        kernel_fn,
        sweep_space=sweep_space,
        hardware_label=hardware_label,
    )
    return {
        "best_config": result.best_config,
        "all_timings": result.all_timings,
        "hardware_label": result.hardware_label,
    }


def validate_against_cpu_reference(
    kernel_output: Any,
    reference_output: Any,
    *,
    atol: float = 1e-5,
    rtol: float = 1e-5,
    eps: float = 1e-8,
) -> dict[str, Any]:
    """Validate kernel output against a CPU reference and gate on correctness.

    Computes element-wise absolute and relative errors between *kernel_output*
    and *reference_output*, then raises :class:`NumericalGateError` if either
    error exceeds the tolerance thresholds.

    Args:
        kernel_output: Output from the synthesized Triton kernel (tensor,
                       array, or nested iterable of floats).
        reference_output: CPU reference output (e.g. ``torch.softmax`` result).
        atol: Absolute tolerance threshold. Defaults to ``1e-5``.
        rtol: Relative tolerance threshold. Defaults to ``1e-5``.
        eps: Small epsilon added to denominator for relative error. Defaults
             to ``1e-8``.

    Returns:
        A dict with:

        - ``max_abs_err`` (float): Maximum absolute error.
        - ``max_rel_err`` (float): Maximum relative error.
        - ``passed`` (bool): True when both tolerances are satisfied.

    Raises:
        NumericalGateError: When ``max_abs_err > atol`` or
                            ``max_rel_err > rtol``.
        ValueError: When *atol* or *rtol* are negative.
    """
    if atol < 0:
        raise ValueError(f"atol must be non-negative, got {atol!r}")
    if rtol < 0:
        raise ValueError(f"rtol must be non-negative, got {rtol!r}")

    report: NumericalReport = verify_numerical(
        kernel_output, reference_output, eps=eps
    )
    gate_on_numerical_correctness(report, atol=atol, rtol=rtol)
    return {
        "max_abs_err": report.max_abs_err,
        "max_rel_err": report.max_rel_err,
        "passed": True,
    }
