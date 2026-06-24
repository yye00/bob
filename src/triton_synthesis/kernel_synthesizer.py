"""Triton kernel synthesizer — synthesize and autotune GPU kernels.

Provides two public functions:

- ``synthesize_triton_kernel``: generate a ``@triton.jit`` kernel source from a spec.
- ``autotune_kernel``: sweep autotune configurations and return the best one.

Operates in CPU-simulation mode when no GPU accelerator is visible, making
both functions fully testable without hardware.
"""

from __future__ import annotations

from typing import Any

from bob.implementers.triton_kernel import (
    AutotuneResult,
    NumericalGateError,
    NumericalReport,
    autotune_kernel as _autotune_kernel,
    default_sweep_space,
    is_gpu_feature,
    persist_winning_config,
    synthesize_kernel,
    verify_numerical,
)


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
        ValueError: If *spec* is empty, whitespace-only, or not a string.
    """
    if not isinstance(spec, str):
        raise ValueError(f"spec must be a string, got {type(spec).__name__!r}")
    if not spec.strip():
        raise ValueError("spec must not be empty or whitespace-only")

    return synthesize_kernel(spec, kernel_name=kernel_name)


def autotune_kernel(
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

    result: AutotuneResult = _autotune_kernel(
        kernel_fn,
        sweep_space=sweep_space,
        hardware_label=hardware_label,
    )
    return {
        "best_config": result.best_config,
        "all_timings": result.all_timings,
        "hardware_label": result.hardware_label,
    }
