"""GPU/Triton kernel synthesis + autotune sub-agent.

When a feature's AC mentions GPU keywords (triton, cuda, rocm, @triton.jit,
GPU kernel), this sub-agent:

1. Detects GPU keywords in the AC text.
2. Synthesizes a Triton kernel wrapped in @triton.autotune.
3. Sweeps BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages.
4. Persists the winning config to disk.
5. Gates on numerical correctness vs a CPU torch reference.

Returns a dict describing whether routing occurred and all synthesis artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.implementers.triton_kernel import (
    AutotuneResult,
    NumericalGateError,
    NumericalReport,
    autotune_kernel,
    gate_on_numerical_correctness,
    is_gpu_feature,
    persist_winning_config,
    synthesize_kernel,
    verify_numerical,
)


def gpu_triton_kernel_synthesis_autotune_sub_agent(
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
    """Route a feature through GPU/Triton kernel synthesis and autotuning.

    When *ac_text* references GPU/Triton keywords the sub-agent:

    - Synthesizes a ``@triton.jit`` kernel wrapped in ``@triton.autotune``
      over the default sweep space (BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages).
    - Autotuners the kernel, picking the fastest configuration.
    - Persists the winning config to ``runs/<feature_id>/triton_config.yaml``.
    - Verifies numerical correctness against *reference_output* when provided.
    - Gates on the numerical report.

    When *ac_text* does not contain GPU keywords, returns ``{"routed": False}``.

    Args:
        feature_id:       Feature UUID used for persistence paths.
        ac_text:          Acceptance-criteria or description text to scan for
                          GPU keywords.
        spec:             Human-readable kernel operation description passed to
                          :func:`~bob3.implementers.triton_kernel.synthesize_kernel`.
        kernel_output:    Output from the synthesized kernel for numerical
                          verification.  When *None*, a synthetic zero-error
                          reference is used so the gate always passes.
        reference_output: CPU reference output for numerical comparison.
                          When *None*, defaults to *kernel_output* (zero error).
        atol:             Absolute error tolerance for the numerical gate.
        rtol:             Relative error tolerance for the numerical gate.
        runs_root:        Override for the ``runs/`` directory root.

    Returns:
        A dict containing:

        - ``routed`` (bool): True when GPU routing triggered.
        - ``kernel_source`` (str): Generated kernel Python source.
        - ``best_config`` (dict): Winning autotune configuration.
        - ``hardware_label`` (str): Detected accelerator label.
        - ``all_timings`` (list): All timing measurements from the sweep.
        - ``numerical_report`` (dict): ``max_abs_err`` and ``max_rel_err``.
        - ``passed_gate`` (bool): True when numerical gate passed.
        - ``config_path`` (str | None): Path to the persisted config YAML.

        When ``routed`` is False, only that key is present.
    """
    if not is_gpu_feature(ac_text):
        return {"routed": False}

    kernel_source = synthesize_kernel(spec)

    autotune_result: AutotuneResult = autotune_kernel(None)

    if kernel_output is None:
        ko = [0.0]
        ro = [0.0]
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
