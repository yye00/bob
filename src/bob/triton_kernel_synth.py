"""GPU/Triton kernel synthesis + autotune sub-agent.

When a feature's AC mentions a GPU kernel, Triton, CUDA, ROCm, or
``@triton.jit``, the implementer routes through this specialized sub-agent
which:

1. Synthesizes a ``@triton.jit`` kernel source from a natural-language spec.
2. Wraps it in ``@triton.autotune`` over the standard
   BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages sweep space.
3. Sweeps on the visible accelerator (CPU-simulation mode when no GPU is
   present, keeping the module fully testable in CI).
4. Persists the winning config to ``runs/<feature>/triton_config.yaml``.
5. Gates on numerical correctness versus a CPU torch reference.

Restores the GPU code-generation capability that v0.10 had and was dropped
during v0.11 spec compaction.

Source: OpenAI Triton (Tillet et al. 2019); ``triton.autotune`` docs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.triton_kernel_synthesizer import (
    autotune_kernel_config,
    persist_winning_config,
    synthesize_and_autotune,
    synthesize_triton_kernel,
    verify_numerical_correctness,
)

__all__ = [
    "synthesize_triton_kernel",
    "autotune_and_gate",
    "autotune_kernel_config",
    "verify_numerical_correctness",
    "persist_winning_config",
]


def autotune_and_gate(
    spec: str,
    *,
    kernel_name: str = "triton_kernel",
    sweep_space: dict[str, list[int]] | None = None,
    hardware_label: str | None = None,
    kernel_output: Any = None,
    reference_output: Any = None,
    atol: float = 1e-5,
    rtol: float = 1e-5,
    feature_id: str | None = None,
    runs_root: "Path | str | None" = None,
) -> dict[str, Any]:
    """Synthesize a Triton kernel, autotune it, gate on correctness, persist.

    Full sub-agent pipeline: generates the ``@triton.jit`` kernel source from
    *spec*, sweeps the ``@triton.autotune`` config grid
    (BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages) on the visible accelerator,
    gates the result against a CPU torch reference, and — when *feature_id* is
    given — persists the winning config to ``runs/<feature_id>/triton_config.yaml``.

    Args:
        spec:             Human-readable description of the kernel operation.
        kernel_name:      Base name for the generated kernel function.
        sweep_space:      Config grid to sweep.  Defaults to the standard grid.
        hardware_label:   Override for the detected accelerator label.
        kernel_output:    Kernel output for numerical verification.  When
                          ``None``, a synthetic zero-error reference is used.
        reference_output: CPU reference output for numerical comparison.
        atol:             Absolute error tolerance for the numerical gate.
        rtol:             Relative error tolerance for the numerical gate.
        feature_id:       When provided, the winning config is persisted under
                          ``runs/<feature_id>/triton_config.yaml``.
        runs_root:        Override for the ``runs/`` root directory.

    Returns:
        A dict containing everything from
        :func:`bob.triton_kernel_synthesizer.synthesize_and_autotune` plus a
        ``config_path`` key: the :class:`pathlib.Path` to the persisted YAML
        (or ``None`` when *feature_id* is not supplied).

    Raises:
        ValueError: If *spec* is empty, not a string, or *sweep_space* is
                    provided but not a ``dict``.
    """
    result = synthesize_and_autotune(
        spec,
        kernel_name=kernel_name,
        sweep_space=sweep_space,
        hardware_label=hardware_label,
        kernel_output=kernel_output,
        reference_output=reference_output,
        atol=atol,
        rtol=rtol,
    )

    config_path: Path | None = None
    if feature_id is not None:
        config_path = persist_winning_config(
            feature_id, result, runs_root=runs_root
        )
    result["config_path"] = config_path

    return result
