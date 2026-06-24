"""GPU/Triton kernel synthesis + autotune for the bob package.

Provides two public functions:

- ``synthesize_triton_kernel``: generate a ``@triton.jit`` kernel source from
  a natural-language spec.
- ``autotune_kernel_config``: sweep autotune configurations and return the best
  one.

When no GPU is present the module operates in CPU-simulation mode, making it
fully testable without hardware.

Integration: bob.orchestrator — when a feature's AC mentions GPU keywords
(triton, cuda, rocm, @triton.jit, GPU kernel) the orchestrator routes through
:func:`synthesize_triton_kernel` and :func:`autotune_kernel_config` to
synthesize and autotune a kernel, persists the winning config, and gates on
numerical correctness vs a CPU torch reference.
"""

from __future__ import annotations

from typing import Any

from bob.implementers.triton_kernel import (
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
    "verify_numerical_correctness",
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

    - A ``@triton.autotune`` decorator over the default sweep space.
    - A ``@triton.jit`` kernel body derived from *spec*.
    - A Python launcher function.

    When Triton is not installed the returned source is still valid Python;
    the kernel raises ``ImportError`` only when actually called on hardware.

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
        kernel_fn: Callable accepting keyword config arguments and returning
                   a timing in ms.  ``None`` triggers the synthetic benchmark.
        sweep_space: Config grid to sweep.  Defaults to
                     ``default_sweep_space()``.
        hardware_label: Override for the hardware label string.  When
                        ``None``, auto-detected from the visible accelerator.

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


def verify_numerical_correctness(
    kernel_output: Any,
    reference_output: Any,
    *,
    atol: float = 1e-5,
    rtol: float = 1e-5,
    eps: float = 1e-8,
) -> dict[str, Any]:
    """Compare *kernel_output* against *reference_output* and gate on tolerances.

    Args:
        kernel_output: Output from the synthesized Triton kernel.
        reference_output: CPU reference output to compare against.
        atol: Absolute error tolerance.
        rtol: Relative error tolerance.
        eps: Small epsilon added to the denominator for relative error.

    Returns:
        A dict with ``max_abs_err``, ``max_rel_err``, and ``passed``.

    Raises:
        NumericalGateError: When tolerances are exceeded.
    """
    report: NumericalReport = verify_numerical(kernel_output, reference_output, eps=eps)

    passed = True
    try:
        gate_on_numerical_correctness(report, atol=atol, rtol=rtol)
    except NumericalGateError:
        passed = False
        raise

    return {
        "max_abs_err": report.max_abs_err,
        "max_rel_err": report.max_rel_err,
        "passed": passed,
    }
