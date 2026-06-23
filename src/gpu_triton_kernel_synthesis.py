"""GPU/Triton kernel synthesis + autotune module.

Top-level module providing four core functions:

- ``synthesize_triton_kernel``: generate a Triton kernel source from a spec.
- ``autotune_kernel_config``: sweep autotune configs and return the best one.
- ``synthesize_and_autotune``: combine synthesis + autotune in one call.
- ``route_to_triton_subagent``: detect GPU keywords and route to Triton synthesis.

When no GPU is present the module operates in CPU-simulation mode, making it
fully testable without hardware.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

# Import triton_kernel directly from its file path to avoid triggering
# bob3/__init__.py's circular import chain (bob3.__init__ → regression_attribution
# → verification.__init__ → verifier → blame_feature_charger → orchestrator.__init__
# → run_loop → blame_feature_charger, which is still partially initialised).
_TRITON_KERNEL_PATH = Path(__file__).parent / "bob3" / "implementers" / "triton_kernel.py"
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

    Combines :func:`synthesize_triton_kernel` and :func:`autotune_kernel_config`
    into one operation: generates the kernel source, sweeps the autotune grid,
    and optionally gates on numerical correctness against a CPU reference.

    Args:
        spec: Human-readable description of the kernel operation.
        kernel_name: Base name for the generated kernel function.
        sweep_space: Config grid to sweep. Defaults to the standard grid.
        hardware_label: Override for the hardware label string.
        kernel_output: Kernel output for numerical verification. When None,
                       a synthetic zero-error reference is used.
        reference_output: CPU reference output for numerical comparison.
        atol: Absolute error tolerance for the numerical gate.
        rtol: Relative error tolerance for the numerical gate.

    Returns:
        A dict containing:

        - ``kernel_source`` (str): Generated kernel Python source.
        - ``best_config`` (dict): Winning autotune configuration.
        - ``all_timings`` (list): All timing measurements from the sweep.
        - ``hardware_label`` (str): Detected accelerator label.
        - ``numerical_report`` (dict): ``max_abs_err`` and ``max_rel_err``.
        - ``passed_gate`` (bool): True when numerical gate passed.

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


def route_to_triton_subagent(
    feature_id: str,
    ac_text: str,
    spec: str,
    *,
    kernel_output: Any = None,
    reference_output: Any = None,
    atol: float = 1e-5,
    rtol: float = 1e-5,
    runs_root: Path | str | None = None,
) -> dict[str, Any]:
    """Detect GPU keywords in *ac_text* and route to Triton kernel synthesis.

    When *ac_text* references GPU/Triton keywords (triton, cuda, rocm,
    ``@triton.jit``, ``GPU kernel``), this function synthesizes a Triton kernel,
    autotuners it, persists the winning config, and gates on numerical
    correctness.  When no GPU keywords are found, returns ``{"routed": False}``.

    Args:
        feature_id: Feature UUID used for persistence paths.
        ac_text: Acceptance-criteria or description text to scan for GPU keywords.
        spec: Human-readable kernel operation description.
        kernel_output: Kernel output for numerical verification.
        reference_output: CPU reference output for numerical comparison.
        atol: Absolute error tolerance for the numerical gate.
        rtol: Relative error tolerance for the numerical gate.
        runs_root: Override for the ``runs/`` directory root.

    Returns:
        A dict containing:

        - ``routed`` (bool): True when GPU routing triggered.
        - ``kernel_source`` (str): Generated kernel Python source (when routed).
        - ``best_config`` (dict): Winning autotune configuration (when routed).
        - ``hardware_label`` (str): Detected accelerator label (when routed).
        - ``all_timings`` (list): All timing measurements (when routed).
        - ``numerical_report`` (dict): Error metrics (when routed).
        - ``passed_gate`` (bool): True when numerical gate passed (when routed).
        - ``config_path`` (str | None): Path to persisted config YAML (when routed).

        When ``routed`` is False, only that key is present.

    Raises:
        ValueError: If *feature_id* or *ac_text* is not a string.
    """
    if not isinstance(feature_id, str):
        raise ValueError(f"feature_id must be a string, got {type(feature_id).__name__!r}")
    if not isinstance(ac_text, str):
        raise ValueError(f"ac_text must be a string, got {type(ac_text).__name__!r}")

    if not is_gpu_feature(ac_text):
        return {"routed": False}

    kernel_source = synthesize_kernel(spec)
    autotune_result: AutotuneResult = autotune_kernel(None)

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
            feature_id,
            autotune_result,
            runs_root=runs_root,
        )
    except Exception:
        config_path = None

    return {
        "routed": True,
        "kernel_source": kernel_source,
        "best_config": autotune_result.best_config,
        "hardware_label": autotune_result.hardware_label,
        "all_timings": autotune_result.all_timings,
        "numerical_report": {
            "max_abs_err": numerical_report.max_abs_err,
            "max_rel_err": numerical_report.max_rel_err,
        },
        "passed_gate": passed_gate,
        "config_path": str(config_path) if config_path is not None else None,
    }
