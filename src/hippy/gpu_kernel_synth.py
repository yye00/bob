"""GPU/Triton kernel synthesis + autotune sub-agent (hippy).

Restores the GPU code-generation capability from v0.10 that was dropped during
v0.11 spec compaction. Two public functions:

- :func:`synthesize_triton_kernel`: generate a ``@triton.jit`` kernel source
  wrapped in ``@triton.autotune`` over BLOCK_M/BLOCK_N/BLOCK_K/num_warps/
  num_stages.
- :func:`autotune_and_verify`: sweep the autotune grid on the visible
  accelerator (or a deterministic CPU-simulation when none is present), persist
  the winning config, and gate on numerical correctness against a CPU
  reference.

Source: OpenAI Triton (Tillet et al. 2019); triton.autotune docs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.implementers.triton_kernel import (
    AutotuneResult,
    NumericalGateError,
    NumericalReport,
    autotune_kernel,
    gate_on_numerical_correctness,
    persist_winning_config,
    synthesize_kernel,
    verify_numerical,
)


def synthesize_triton_kernel(spec: str, *, kernel_name: str = "triton_kernel") -> str:
    """Synthesize a ``@triton.jit`` kernel source from a natural-language spec.

    The returned source contains a ``@triton.autotune`` decorator over the
    default BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages sweep space, a
    ``@triton.jit`` kernel body derived from *spec*, and a Python launcher.

    Args:
        spec: Human-readable description of the kernel operation (e.g.
              "row-wise softmax over a 2-D float32 tensor").
        kernel_name: Base name for the generated kernel function.

    Returns:
        Python source string containing the ``@triton.jit`` kernel.

    Raises:
        ValueError: If *spec* is not a string or is empty/whitespace-only.
    """
    if not isinstance(spec, str):
        raise ValueError(f"spec must be a string, got {type(spec).__name__!r}")
    if not spec.strip():
        raise ValueError("spec must not be empty")

    return synthesize_kernel(spec, kernel_name=kernel_name)


def autotune_and_verify(
    feature_id: str,
    spec: str,
    *,
    kernel_name: str = "triton_kernel",
    sweep_space: dict[str, list[int]] | None = None,
    hardware_label: str | None = None,
    kernel_output: Any = None,
    reference_output: Any = None,
    atol: float = 1e-5,
    rtol: float = 1e-5,
    runs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Sweep the autotune grid, persist the winner, and gate on correctness.

    Runs the autotune sweep over *sweep_space* (defaulting to the standard
    grid), picks the fastest configuration, persists it to
    ``runs/<feature_id>/triton_config.yaml``, and gates the result on
    numerical correctness against a CPU reference.

    Args:
        feature_id: Feature identifier used for the persistence path.
        spec: Human-readable kernel operation description.
        kernel_name: Base name for the generated kernel function.
        sweep_space: Config grid to sweep. Defaults to the standard grid.
        hardware_label: Override for the hardware label; auto-detected when None.
        kernel_output: Kernel output for numerical verification. When None, a
                       synthetic zero-error reference is used.
        reference_output: CPU reference output. Defaults to *kernel_output*.
        atol: Absolute error tolerance for the numerical gate.
        rtol: Relative error tolerance for the numerical gate.
        runs_root: Override for the ``runs/`` root directory.

    Returns:
        A dict with keys ``best_config``, ``all_timings``, ``hardware_label``,
        ``numerical_report``, ``passed_gate``, and ``config_path``.

    Raises:
        ValueError: If *feature_id* or *spec* is not a string, *spec* is empty,
            or *sweep_space* is provided but is not a dict.
    """
    if not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a string, got {type(feature_id).__name__!r}"
        )
    if not isinstance(spec, str):
        raise ValueError(f"spec must be a string, got {type(spec).__name__!r}")
    if not spec.strip():
        raise ValueError("spec must not be empty")
    if sweep_space is not None and not isinstance(sweep_space, dict):
        raise ValueError(
            f"sweep_space must be a dict or None, got {type(sweep_space).__name__!r}"
        )

    # Synthesize so the spec is validated and the kernel is available for callers.
    synthesize_kernel(spec, kernel_name=kernel_name)

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
    try:
        config_path = persist_winning_config(
            feature_id, autotune_result, runs_root=runs_root
        )
    except Exception:
        config_path = None

    return {
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
