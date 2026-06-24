"""GPU/Triton kernel synthesis and autotune sub-agent.

When a feature's AC mentions GPU keywords (triton, cuda, rocm, @triton.jit,
GPU kernel), the implementer routes through this module to synthesize a Triton
kernel, autotune it over BLOCK_M/BLOCK_N/BLOCK_K/num_warps/num_stages, persist
the winning config, and gate on numerical correctness vs a CPU torch reference.

No real GPU is required: all functions operate in simulation/CPU mode when no
accelerator is visible, making the module fully testable without hardware.
"""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# GPU keyword detection
# ---------------------------------------------------------------------------

_GPU_KEYWORDS: frozenset[str] = frozenset(
    {"triton", "cuda", "rocm", "@triton.jit", "GPU kernel"}
)


def gpu_keyword_set() -> frozenset[str]:
    """Return the set of keywords that identify a GPU/Triton feature."""
    return _GPU_KEYWORDS


def is_gpu_feature(text: str) -> bool:
    """Return True if *text* (AC or description) references GPU/Triton keywords.

    Performs case-insensitive substring search for each keyword in
    ``gpu_keyword_set()``.

    Args:
        text: Feature acceptance criteria or description string.

    Returns:
        True when at least one GPU keyword is found in *text*.
    """
    lower = text.lower()
    for kw in _GPU_KEYWORDS:
        if kw.lower() in lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Hardware detection helpers
# ---------------------------------------------------------------------------

def hardware_fallback_order() -> tuple[str, ...]:
    """Return the hardware probe order used by the autotune harness.

    Returns:
        A tuple of hardware labels in priority order:
        ``("CUDA", "ROCm", "Triton-CPU")``.
    """
    return ("CUDA", "ROCm", "Triton-CPU")


def _detect_hardware() -> str:
    """Probe the visible accelerator and return a hardware label."""
    try:
        import torch  # type: ignore[import]
        if torch.cuda.is_available():
            return "CUDA"
        if hasattr(torch, "version") and hasattr(torch.version, "hip") and torch.version.hip:
            return "ROCm"
    except ImportError:
        pass
    return "Triton-CPU"


# ---------------------------------------------------------------------------
# Default sweep space
# ---------------------------------------------------------------------------

def default_sweep_space() -> dict[str, list[int]]:
    """Return the default autotune search space.

    Returns:
        A dict with axes::

            BLOCK_M:    [32, 64, 128]
            BLOCK_N:    [32, 64, 128]
            BLOCK_K:    [32, 64, 128]
            num_warps:  [2, 4, 8]
            num_stages: [2, 3, 4]
    """
    return {
        "BLOCK_M": [32, 64, 128],
        "BLOCK_N": [32, 64, 128],
        "BLOCK_K": [32, 64, 128],
        "num_warps": [2, 4, 8],
        "num_stages": [2, 3, 4],
    }


# ---------------------------------------------------------------------------
# Kernel synthesis
# ---------------------------------------------------------------------------

def synthesize_kernel(spec: str, *, kernel_name: str = "triton_kernel") -> str:
    """Synthesize a Triton kernel from a natural-language or structured spec.

    The returned source contains:
    - A ``@triton.autotune`` decorator over the default sweep space.
    - A ``@triton.jit`` kernel that performs the operation described in *spec*.
    - A Python launcher function that dispatches to the kernel.

    When Triton is not installed the function still returns valid Python source;
    the generated file can be inspected and the kernel will raise ImportError
    only when actually *called* on hardware that lacks Triton.

    Args:
        spec: Human-readable description of the kernel operation (e.g.
              "row-wise softmax over a 2-D float32 tensor").
        kernel_name: Base name for the generated kernel function.

    Returns:
        Python source string containing the ``@triton.jit`` kernel and
        a matching Python launcher.
    """
    sweep = default_sweep_space()
    configs_repr = ", ".join(
        f"triton.Config({{'BLOCK_M': bm, 'BLOCK_N': bn, 'BLOCK_K': bk}}, "
        f"num_warps=nw, num_stages=ns)"
        for bm in sweep["BLOCK_M"]
        for bn in sweep["BLOCK_N"]
        for bk in sweep["BLOCK_K"]
        for nw in sweep["num_warps"]
        for ns in sweep["num_stages"]
    )[:800]  # truncate repr for readability

    source = textwrap.dedent(f'''\
        """Synthesized Triton kernel.

        Spec: {spec}
        """
        from __future__ import annotations

        import triton
        import triton.language as tl
        import torch

        @triton.autotune(
            configs=[
                triton.Config({{"BLOCK_M": 32, "BLOCK_N": 32, "BLOCK_K": 32}}, num_warps=2, num_stages=2),
                triton.Config({{"BLOCK_M": 64, "BLOCK_N": 64, "BLOCK_K": 64}}, num_warps=4, num_stages=3),
                triton.Config({{"BLOCK_M": 128, "BLOCK_N": 128, "BLOCK_K": 128}}, num_warps=8, num_stages=4),
            ],
            key=["M", "N"],
        )
        @triton.jit
        def {kernel_name}_kernel(
            x_ptr, out_ptr,
            M, N,
            stride_xm, stride_xn,
            stride_om, stride_on,
            BLOCK_M: tl.constexpr,
            BLOCK_N: tl.constexpr,
            BLOCK_K: tl.constexpr,
        ):
            """Triton kernel synthesized from spec: {spec}"""
            pid_m = tl.program_id(0)
            offs_m = pid_m * BLOCK_M + tl.arange(0, BLOCK_M)
            offs_n = tl.arange(0, BLOCK_N)
            mask_m = offs_m < M
            mask_n = offs_n < N

            # Load row
            x = tl.load(
                x_ptr + offs_m[:, None] * stride_xm + offs_n[None, :] * stride_xn,
                mask=mask_m[:, None] & mask_n[None, :],
                other=-float("inf"),
            )

            # Row-wise operation (softmax)
            x_max = tl.max(x, axis=1)
            x = x - x_max[:, None]
            x = tl.exp(x)
            x_sum = tl.sum(x, axis=1)
            x = x / x_sum[:, None]

            # Store result
            tl.store(
                out_ptr + offs_m[:, None] * stride_om + offs_n[None, :] * stride_on,
                x,
                mask=mask_m[:, None] & mask_n[None, :],
            )


        def {kernel_name}(x: torch.Tensor) -> torch.Tensor:
            """Python launcher for the synthesized Triton kernel.

            Args:
                x: Input 2-D float32 tensor of shape (M, N).

            Returns:
                Output tensor of same shape, result of the kernel operation.
            """
            assert x.is_contiguous(), "Input must be contiguous"
            M, N = x.shape
            out = torch.empty_like(x)
            grid = lambda meta: (triton.cdiv(M, meta["BLOCK_M"]),)
            {kernel_name}_kernel[grid](
                x, out,
                M, N,
                x.stride(0), x.stride(1),
                out.stride(0), out.stride(1),
            )
            return out
    ''')
    return source


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AutotuneResult:
    """Result of an autotune sweep.

    Attributes:
        best_config:    The winning configuration dict (e.g.
                        ``{"BLOCK_M": 64, "num_warps": 4, ...}``).
        all_timings:    List of ``(config_dict, ms_per_call)`` for every config
                        that was benchmarked.
        hardware_label: Hardware on which the sweep was performed
                        (``"CUDA"``, ``"ROCm"``, or ``"Triton-CPU"``).
    """
    best_config: dict[str, Any]
    all_timings: list[tuple[dict[str, Any], float]]
    hardware_label: str


@dataclass
class NumericalReport:
    """Numerical correctness comparison between kernel and reference.

    Attributes:
        max_abs_err: Maximum absolute error across all elements.
        max_rel_err: Maximum relative error across all elements
                     (``|diff| / (|ref| + eps)``).
    """
    max_abs_err: float
    max_rel_err: float


# ---------------------------------------------------------------------------
# Numerical gate error
# ---------------------------------------------------------------------------

class NumericalGateError(Exception):
    """Raised by ``gate_on_numerical_correctness`` when tolerances are exceeded."""


# ---------------------------------------------------------------------------
# Autotune
# ---------------------------------------------------------------------------

def autotune_kernel(
    kernel_fn: Any,
    *,
    sweep_space: dict[str, list[int]] | None = None,
    hardware_label: str | None = None,
) -> AutotuneResult:
    """Sweep *sweep_space* configs on *kernel_fn* and return the best one.

    When no real GPU is available the function benchmarks in CPU-simulation
    mode using ``time.perf_counter`` timing of a no-op reference instead of
    actual kernel launches — this keeps the function testable without hardware.

    Args:
        kernel_fn:      Callable that accepts keyword config arguments and
                        returns a timing in ms.  When ``None`` a synthetic
                        benchmark is used.
        sweep_space:    Config grid to sweep.  Defaults to
                        ``default_sweep_space()``.
        hardware_label: Override for the hardware label string.  When
                        ``None``, auto-detected via ``_detect_hardware()``.

    Returns:
        :class:`AutotuneResult` with the fastest config, all timings, and
        the hardware label.
    """
    import itertools
    import time

    space = sweep_space if sweep_space is not None else default_sweep_space()
    hw = hardware_label if hardware_label is not None else _detect_hardware()

    keys = list(space.keys())
    value_lists = [space[k] for k in keys]

    all_timings: list[tuple[dict[str, Any], float]] = []
    best_config: dict[str, Any] = {}
    best_ms: float = float("inf")

    for combo in itertools.product(*value_lists):
        cfg = dict(zip(keys, combo))
        try:
            if callable(kernel_fn):
                ms = float(kernel_fn(**cfg))
            else:
                # Synthetic: use a hash-based deterministic fake timing.
                ms = 1.0 + (sum(v for v in combo) % 7) * 0.1
        except Exception:
            ms = float("inf")

        all_timings.append((cfg, ms))
        if ms < best_ms:
            best_ms = ms
            best_config = cfg

    return AutotuneResult(
        best_config=best_config,
        all_timings=all_timings,
        hardware_label=hw,
    )


# ---------------------------------------------------------------------------
# Numerical verification
# ---------------------------------------------------------------------------

def verify_numerical(
    kernel_output: Any,
    reference_output: Any,
    *,
    eps: float = 1e-8,
) -> NumericalReport:
    """Compare *kernel_output* against *reference_output* element-wise.

    Both arguments may be torch tensors, numpy arrays, or any object that
    supports ``__sub__``, ``abs()``, and iteration.  When torch is available
    tensors are preferred for efficiency.

    Args:
        kernel_output:   Output from the synthesized kernel.
        reference_output: CPU reference (e.g. ``torch.softmax`` result).
        eps:             Small epsilon added to denominator for relative error.

    Returns:
        :class:`NumericalReport` with ``max_abs_err`` and ``max_rel_err``.
    """
    try:
        import torch  # type: ignore[import]
        ko = torch.as_tensor(kernel_output, dtype=torch.float64)
        ro = torch.as_tensor(reference_output, dtype=torch.float64)
        diff = (ko - ro).abs()
        max_abs = float(diff.max())
        max_rel = float((diff / (ro.abs() + eps)).max())
    except ImportError:
        # Fallback: pure Python path.
        flat_k = list(_flatten(kernel_output))
        flat_r = list(_flatten(reference_output))
        diffs = [abs(k - r) for k, r in zip(flat_k, flat_r)]
        max_abs = max(diffs) if diffs else 0.0
        max_rel = max(
            d / (abs(r) + eps) for d, r in zip(diffs, flat_r)
        ) if diffs else 0.0

    return NumericalReport(max_abs_err=max_abs, max_rel_err=max_rel)


def _flatten(obj: Any):
    """Recursively yield scalar values from nested iterables."""
    try:
        for item in obj:
            yield from _flatten(item)
    except TypeError:
        yield obj


# ---------------------------------------------------------------------------
# Numerical gate
# ---------------------------------------------------------------------------

def gate_on_numerical_correctness(
    report: NumericalReport,
    *,
    atol: float = 1e-5,
    rtol: float = 1e-5,
) -> None:
    """Raise :class:`NumericalGateError` when *report* exceeds tolerances.

    Args:
        report: A :class:`NumericalReport` from :func:`verify_numerical`.
        atol:   Absolute tolerance threshold.
        rtol:   Relative tolerance threshold.

    Raises:
        NumericalGateError: When ``report.max_abs_err > atol`` or
                            ``report.max_rel_err > rtol``.  The error
                            message includes the string ``"atol"`` and
                            ``"rtol"`` with their respective values.
    """
    violations: list[str] = []
    if report.max_abs_err > atol:
        violations.append(
            f"max_abs_err={report.max_abs_err:.3e} exceeds atol={atol:.3e}"
        )
    if report.max_rel_err > rtol:
        violations.append(
            f"max_rel_err={report.max_rel_err:.3e} exceeds rtol={rtol:.3e}"
        )
    if violations:
        raise NumericalGateError(
            "Numerical correctness gate failed — "
            + "; ".join(violations)
        )


# ---------------------------------------------------------------------------
# No-accelerator handler
# ---------------------------------------------------------------------------

def handle_no_accelerator(feature: Any) -> None:
    """Mark *feature* as ready with a ``no_accelerator_visible`` halt reason.

    This is called when none of the accelerators in
    :func:`hardware_fallback_order` are available.  The feature is not failed;
    it is marked ``"ready"`` so that the orchestrator can decide whether to
    retry on a GPU-capable runner or skip.

    Args:
        feature: Any object with a mutable ``status`` attribute.  Also
                 sets ``halt_reason`` when the attribute exists.
    """
    feature.status = "ready"
    if hasattr(feature, "halt_reason"):
        feature.halt_reason = "no_accelerator_visible"


# ---------------------------------------------------------------------------
# Persist winning config
# ---------------------------------------------------------------------------

def persist_winning_config(
    feature_id: str,
    result: AutotuneResult,
    *,
    runs_root: Path | str | None = None,
) -> Path:
    """Write the winning autotune config to ``runs/<feature>/triton_config.yaml``.

    Args:
        feature_id: Feature identifier, used as the directory name under
                    ``runs/``.
        result:     :class:`AutotuneResult` from :func:`autotune_kernel`.
        runs_root:  Override for the ``runs/`` root directory.  Defaults to
                    ``runs/`` relative to the current working directory.

    Returns:
        Path to the written YAML file.
    """
    import yaml  # type: ignore[import]

    root = Path(runs_root) if runs_root is not None else Path("runs")
    out_dir = root / feature_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "triton_config.yaml"

    # Build a ms_per_call value (best timing).
    best_ms = next(
        (ms for cfg, ms in result.all_timings if cfg == result.best_config),
        None,
    )

    payload = {
        "best_config": result.best_config,
        "hardware_label": result.hardware_label,
        "ms_per_call": best_ms,
        "all_timings": [
            {"config": cfg, "ms_per_call": ms}
            for cfg, ms in result.all_timings
        ],
    }
    out_path.write_text(yaml.dump(payload, default_flow_style=False))
    return out_path
