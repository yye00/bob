"""GPU/Triton kernel synthesis module for bob3 (feature 6cc31a74).

Provides:
- ``synthesize_and_autotune``: synthesize a Triton kernel and autotune it.
- ``verify_numerical_correctness``: compare kernel output against a CPU reference.

When a feature's AC mentions GPU keywords (triton, cuda, rocm, @triton.jit,
GPU kernel), the implementer routes through these functions to synthesize a
Triton kernel, sweep BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages, persist
the winning config, and gate on numerical correctness.

No real GPU is required: all functions operate in CPU-simulation mode when
no accelerator is visible.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

# Import triton_kernel directly to avoid the circular import chain:
# bob3.triton_kernel_synthesis → bob3.implementers.__init__
# → bob3.orchestrator.plan_gate → bob3.orchestrator.__init__
# → bob3.triton_kernel_synthesis (partially initialised → ImportError).
_TRITON_KERNEL_PATH = Path(__file__).parent / "implementers" / "triton_kernel.py"
if "bob3.implementers.triton_kernel" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "bob3.implementers.triton_kernel", _TRITON_KERNEL_PATH
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["bob3.implementers.triton_kernel"] = _mod
    _spec.loader.exec_module(_mod)

from bob3.implementers.triton_kernel import (  # noqa: E402
    AutotuneResult,
    NumericalGateError,
    NumericalReport,
    autotune_kernel,
    default_sweep_space,
    gate_on_numerical_correctness,
    is_gpu_feature,
    persist_winning_config,
    synthesize_kernel as _synthesize_kernel,
    verify_numerical,
)


def synthesize_kernel(
    spec: str,
    *,
    kernel_name: str = "triton_kernel",
) -> str:
    """Synthesize a ``@triton.jit`` kernel source from a natural-language spec.

    Args:
        spec: Human-readable description of the kernel operation.
        kernel_name: Base name for the generated kernel function.

    Returns:
        Python source string containing the ``@triton.jit`` kernel.

    Raises:
        ValueError: If *spec* is empty or not a string.
    """
    if not isinstance(spec, str):
        raise ValueError(f"spec must be a string, got {type(spec).__name__!r}")
    if not spec.strip():
        raise ValueError("spec must not be empty")
    return _synthesize_kernel(spec, kernel_name=kernel_name)


def autotune_kernel_config(
    kernel_fn: Any = None,
    *,
    sweep_space: dict[str, list[int]] | None = None,
    hardware_label: str | None = None,
) -> dict[str, Any]:
    """Sweep autotune configurations and return the best one.

    Args:
        kernel_fn: Callable returning timing in ms per config, or ``None``.
        sweep_space: Config grid to sweep. Defaults to the standard grid.
        hardware_label: Override for the hardware label string.

    Returns:
        A dict with ``best_config``, ``all_timings``, and ``hardware_label``.

    Raises:
        ValueError: If *sweep_space* is not a dict or None.
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


def synthesize_and_autotune(
    spec: str,
    *,
    feature_id: str = "",
    kernel_name: str = "triton_kernel",
    sweep_space: dict[str, list[int]] | None = None,
    hardware_label: str | None = None,
    kernel_output: Any = None,
    reference_output: Any = None,
    atol: float = 1e-5,
    rtol: float = 1e-5,
    runs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Synthesize a Triton kernel from *spec*, autotune it, and gate numerically.

    Combines kernel synthesis, autotune sweep, numerical verification, and
    optional config persistence into one call.

    Args:
        spec: Human-readable kernel operation description (e.g.
              "row-wise softmax over a 2-D float32 tensor").
        feature_id: Feature UUID used for config persistence.  When empty,
                    config is not persisted.
        kernel_name: Base name for the generated kernel function.
        sweep_space: Config grid to sweep.  Defaults to the standard
                     BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages grid.
        hardware_label: Override for the hardware label string.  When
                        ``None``, auto-detected.
        kernel_output: Kernel output for numerical verification.  When
                       ``None``, a synthetic zero-error reference is used
                       so the gate always passes.
        reference_output: CPU reference output.  Defaults to *kernel_output*.
        atol: Absolute error tolerance.
        rtol: Relative error tolerance.
        runs_root: Override for the ``runs/`` root directory.

    Returns:
        A dict with:

        - ``kernel_source`` (str): Generated ``@triton.jit`` kernel source.
        - ``best_config`` (dict): Winning autotune configuration.
        - ``all_timings`` (list): All ``(config, ms)`` sweep measurements.
        - ``hardware_label`` (str): Detected or overridden accelerator label.
        - ``numerical_report`` (dict): ``max_abs_err`` and ``max_rel_err``.
        - ``passed_gate`` (bool): True when numerical gate passed.
        - ``config_path`` (str | None): Path to persisted config YAML, or None.

    Raises:
        ValueError: If *spec* is empty, not a string, or *sweep_space* is invalid.
    """
    if not isinstance(spec, str):
        raise ValueError(f"spec must be a string, got {type(spec).__name__!r}")
    if not spec.strip():
        raise ValueError("spec must not be empty")
    if sweep_space is not None and not isinstance(sweep_space, dict):
        raise ValueError(
            f"sweep_space must be a dict or None, got {type(sweep_space).__name__!r}"
        )

    kernel_source = synthesize_kernel(spec, kernel_name=kernel_name)

    autotune_result: AutotuneResult = autotune_kernel(
        None,
        sweep_space=sweep_space,
        hardware_label=hardware_label,
    )

    if kernel_output is None:
        ko: Any = [0.0]
        ro: Any = [0.0]
    else:
        ko = kernel_output
        ro = reference_output if reference_output is not None else kernel_output

    numerical_report: NumericalReport = verify_numerical(ko, ro)

    passed_gate = True
    try:
        gate_on_numerical_correctness(numerical_report, atol=atol, rtol=rtol)
    except NumericalGateError:
        passed_gate = False

    config_path: Path | None = None
    if feature_id:
        try:
            config_path = persist_winning_config(
                feature_id,
                autotune_result,
                runs_root=runs_root,
            )
        except Exception:
            config_path = None

    return {
        "kernel_source": kernel_source,
        "best_config": autotune_result.best_config,
        "all_timings": autotune_result.all_timings,
        "hardware_label": autotune_result.hardware_label,
        "numerical_report": {
            "max_abs_err": numerical_report.max_abs_err,
            "max_rel_err": numerical_report.max_rel_err,
        },
        "passed_gate": passed_gate,
        "config_path": str(config_path) if config_path is not None else None,
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

    Computes element-wise absolute and relative errors, then checks them
    against *atol* and *rtol*.  Returns a report dict; raises
    :class:`~bob3.implementers.triton_kernel.NumericalGateError` when
    tolerances are exceeded.

    Args:
        kernel_output: Output from the synthesized Triton kernel (tensor,
                       list, or any numeric iterable).
        reference_output: CPU reference output to compare against.
        atol: Absolute error tolerance.
        rtol: Relative error tolerance.
        eps: Small epsilon added to the denominator for relative error.

    Returns:
        A dict with:

        - ``max_abs_err`` (float): Maximum absolute error.
        - ``max_rel_err`` (float): Maximum relative error.
        - ``passed`` (bool): True when both tolerances are satisfied.

    Raises:
        NumericalGateError: When ``max_abs_err > atol`` or ``max_rel_err > rtol``.
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
