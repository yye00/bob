"""hippy implementer — GPU/Triton feature routing.

Integration point (``integration: hippy.implementer``): when a feature's
acceptance criteria mention GPU kernel / Triton / CUDA / ROCm / ``@triton.jit``,
:func:`maybe_route_gpu_feature` routes the work through the specialized Triton
kernel synthesis + autotune sub-agent instead of the generic implementer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.implementers.triton_kernel import is_gpu_feature

from hippy.gpu_kernel_synth import autotune_and_verify, synthesize_triton_kernel


def maybe_route_gpu_feature(
    feature_id: str,
    ac_text: str,
    spec: str,
    *,
    kernel_name: str = "triton_kernel",
    sweep_space: dict[str, list[int]] | None = None,
    kernel_output: Any = None,
    reference_output: Any = None,
    atol: float = 1e-5,
    rtol: float = 1e-5,
    runs_root: Path | str | None = None,
) -> dict[str, Any] | None:
    """Route a GPU/Triton feature to the kernel-synthesis sub-agent.

    Scans *ac_text* for GPU keywords (triton, cuda, rocm, ``@triton.jit``,
    "GPU kernel"). When found, synthesizes a Triton kernel, autotunes it,
    persists the winning config, and gates on numerical correctness. When no
    GPU keywords are present, returns ``None`` so the caller falls back to the
    generic implementer.

    Args:
        feature_id: Feature identifier used for persistence paths.
        ac_text: Acceptance-criteria / description text to scan for GPU keywords.
        spec: Human-readable kernel operation description.
        kernel_name: Base name for the generated kernel function.
        sweep_space: Config grid to sweep. Defaults to the standard grid.
        kernel_output: Kernel output for numerical verification.
        reference_output: CPU reference output for numerical comparison.
        atol: Absolute error tolerance for the numerical gate.
        rtol: Relative error tolerance for the numerical gate.
        runs_root: Override for the ``runs/`` root directory.

    Returns:
        A dict with ``routed`` True plus ``kernel_source`` and all
        :func:`~hippy.gpu_kernel_synth.autotune_and_verify` result keys when
        routing triggers; ``None`` when *ac_text* has no GPU keywords.

    Raises:
        ValueError: If *feature_id*, *ac_text*, or *spec* is not a string.
    """
    if not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a string, got {type(feature_id).__name__!r}"
        )
    if not isinstance(ac_text, str):
        raise ValueError(f"ac_text must be a string, got {type(ac_text).__name__!r}")
    if not isinstance(spec, str):
        raise ValueError(f"spec must be a string, got {type(spec).__name__!r}")

    if not is_gpu_feature(ac_text):
        return None

    kernel_source = synthesize_triton_kernel(spec, kernel_name=kernel_name)
    result = autotune_and_verify(
        feature_id,
        spec,
        kernel_name=kernel_name,
        sweep_space=sweep_space,
        kernel_output=kernel_output,
        reference_output=reference_output,
        atol=atol,
        rtol=rtol,
        runs_root=runs_root,
    )

    return {"routed": True, "kernel_source": kernel_source, **result}
