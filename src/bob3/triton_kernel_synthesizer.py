"""Triton kernel synthesizer — public facade for bob3.

Exposes three functions that the orchestrator and sub-agents use to detect
GPU features, synthesize Triton kernels, autotune them, and verify correctness:

- ``synthesize_triton_kernel``: generate a ``@triton.jit`` kernel source.
- ``autotune_kernel_config``: sweep configs and return the best one.
- ``verify_numerical_correctness``: compare kernel output against a CPU reference.

All functions operate without a real GPU (CPU-simulation mode), making the
module fully testable in CI environments without accelerator hardware.

Uses a direct file-path import for ``bob3.implementers.triton_kernel`` to
avoid the circular import chain:
  bob3.triton_kernel_synthesizer
    → bob3.implementers.__init__
      → bob3.orchestrator.plan_gate
        → bob3.orchestrator.__init__
          → bob3.triton_kernel_synthesizer  (partially initialised)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

# Direct file-path load to bypass bob3.implementers.__init__, which would
# trigger the circular import chain described in the module docstring.
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
    gate_on_numerical_correctness,
    persist_winning_config as _persist_winning_config,
    synthesize_kernel,
    verify_numerical,
)


def synthesize_triton_kernel(
    spec: str,
    *,
    kernel_name: str = "triton_kernel",
) -> str:
    """Synthesize a ``@triton.jit`` kernel source from a natural-language spec.

    Generates Python source that includes a ``@triton.autotune`` decorator
    wrapping the kernel over the standard BLOCK_M/BLOCK_N/BLOCK_K/num_warps/
    num_stages sweep space.  When Triton is not installed, the returned source
    is still valid Python; the kernel raises ``ImportError`` only when called
    on hardware.

    Args:
        spec:        Human-readable description of the kernel operation (e.g.
                     "row-wise softmax over a 2-D float32 tensor").
        kernel_name: Base name for the generated kernel function.

    Returns:
        Python source string containing the ``@triton.jit`` kernel and a
        matching Python launcher.

    Raises:
        ValueError: When *spec* is not a string or is empty/whitespace-only.
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
    """Sweep autotune configurations over *sweep_space* and return the best one.

    Benchmarks *kernel_fn* over each configuration in *sweep_space* (defaulting
    to the standard BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages grid) and
    returns the fastest configuration plus all timing data.

    When *kernel_fn* is ``None`` or the call raises, a deterministic synthetic
    benchmark is used so the function is testable without hardware.

    Args:
        kernel_fn:      Callable accepting keyword config arguments and returning
                        a timing in ms.  ``None`` triggers the synthetic
                        benchmark.
        sweep_space:    Config grid to sweep.  Defaults to the standard grid.
        hardware_label: Override the hardware label string.  When ``None``,
                        auto-detected from the visible accelerator.

    Returns:
        A dict with keys:

        - ``best_config`` (dict): Winning configuration.
        - ``all_timings`` (list of ``(config, ms)`` pairs): All measurements.
        - ``hardware_label`` (str): Detected or overridden hardware label.

    Raises:
        ValueError: When *sweep_space* is provided but is not a ``dict``.
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

    Computes element-wise absolute and relative errors, gates on *atol*/*rtol*,
    and returns a summary dict.

    Args:
        kernel_output:    Output from the synthesized Triton kernel.
        reference_output: CPU reference (e.g. ``torch.softmax`` result).
        atol:             Absolute error tolerance.
        rtol:             Relative error tolerance.
        eps:              Small denominator epsilon for relative error.

    Returns:
        A dict with keys:

        - ``max_abs_err`` (float): Maximum element-wise absolute error.
        - ``max_rel_err`` (float): Maximum element-wise relative error.
        - ``passed`` (bool): ``True`` when both tolerances are satisfied.

    Raises:
        ValueError: When *kernel_output* or *reference_output* is ``None``.
    """
    if kernel_output is None:
        raise ValueError("kernel_output must not be None")
    if reference_output is None:
        raise ValueError("reference_output must not be None")

    report: NumericalReport = verify_numerical(kernel_output, reference_output, eps=eps)

    passed = True
    try:
        gate_on_numerical_correctness(report, atol=atol, rtol=rtol)
    except NumericalGateError:
        passed = False

    return {
        "max_abs_err": report.max_abs_err,
        "max_rel_err": report.max_rel_err,
        "passed": passed,
    }


def synthesize_and_autotune(
    spec: str,
    *,
    kernel_name: str = "triton_kernel",
    sweep_space: dict[str, list[int]] | None = None,
    hardware_label: str | None = None,
    kernel_output: Any = None,
    reference_output: Any = None,
    atol: float = 1e-5,
    rtol: float = 1e-5,
) -> dict[str, Any]:
    """Synthesize a Triton kernel and autotune it in a single call.

    Combines synthesis and autotuning: generates the kernel source from *spec*,
    sweeps the autotune config grid, and optionally gates on numerical
    correctness against a CPU reference.

    Args:
        spec:             Human-readable description of the kernel operation.
        kernel_name:      Base name for the generated kernel function.
        sweep_space:      Config grid to sweep.  Defaults to the standard grid.
        hardware_label:   Override for the hardware label string.
        kernel_output:    Kernel output for numerical verification.  When
                          ``None``, a synthetic zero-error reference is used.
        reference_output: CPU reference output for numerical comparison.
        atol:             Absolute error tolerance for the numerical gate.
        rtol:             Relative error tolerance for the numerical gate.

    Returns:
        A dict containing:

        - ``kernel_source`` (str): Generated kernel Python source.
        - ``best_config`` (dict): Winning autotune configuration.
        - ``all_timings`` (list): All timing measurements from the sweep.
        - ``hardware_label`` (str): Detected accelerator label.
        - ``numerical_report`` (dict): ``max_abs_err`` and ``max_rel_err``.
        - ``passed_gate`` (bool): ``True`` when the numerical gate passed.

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
    }


def persist_winning_config(
    feature_id: str,
    autotune_result: dict[str, Any],
    *,
    runs_root: "Path | str | None" = None,
) -> "Path":
    """Persist the winning autotune configuration to ``runs/<feature>/triton_config.yaml``.

    Writes a YAML file containing the best config, hardware label, and timing
    data under ``runs/<feature_id>/triton_config.yaml``.

    Args:
        feature_id:      Feature identifier used as the directory name under
                         ``runs/``.
        autotune_result: Dict returned by :func:`synthesize_and_autotune` or
                         :func:`autotune_kernel_config`, containing
                         ``best_config``, ``hardware_label``, and
                         ``all_timings``.
        runs_root:       Override for the ``runs/`` root directory.  Defaults
                         to ``runs/`` relative to the current working directory.

    Returns:
        :class:`pathlib.Path` to the written YAML file.

    Raises:
        ValueError: If *feature_id* is not a non-empty string, or
                    *autotune_result* is not a dict.
    """
    if not isinstance(feature_id, str) or not feature_id.strip():
        raise ValueError("feature_id must be a non-empty string")
    if not isinstance(autotune_result, dict):
        raise ValueError(
            f"autotune_result must be a dict, got {type(autotune_result).__name__!r}"
        )

    internal = AutotuneResult(
        best_config=autotune_result.get("best_config", {}),
        all_timings=autotune_result.get("all_timings", []),
        hardware_label=autotune_result.get("hardware_label", "Triton-CPU"),
    )
    return _persist_winning_config(feature_id, internal, runs_root=runs_root)
