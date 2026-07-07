"""C++/GPU characterization harness with numeric tolerance (extends BF-6).

BF-6 (:mod:`bob.acceptance.kinds`) captures characterization snapshots by
importing a *Python* target and diffing its stdout / return value. That is
useless for a compiled C++ collective (e.g. an RCCL all-reduce): there is no
Python object to import, and a **bitwise** diff of a GPU reduction is
meaningless — floating-point reductions on device legitimately produce results
that differ in the low bits between runs and between hardware.

This harness adds a GPU-aware characterization flow:

* **Observer phase** — :func:`capture_gpu_golden` builds and runs a small
  driver (or an existing ``rccl-tests`` binary) against fixed inputs and stores
  a *golden artifact* under the feature's ``snapshot_dir``. The golden records,
  for **correctness**, the reduced-buffer contents and the validation pass/fail
  plus the observed error bound.
* **Verifier phase** — :func:`verify_gpu_golden` rebuilds after the edit,
  re-runs, and compares against the golden using a numeric **tolerance** rather
  than an exact byte diff. It fails if correctness regresses (validation flips
  to fail), if the reduced buffer drifts outside the allowed tolerance, or if
  the observed error bound exceeds ``max_error_bound``.

Both phases tie into the existing dispatch-coupled anti-cheat
(:mod:`hippy.dispatch_facade`): a run only counts if the collective actually
**dispatched a device kernel**. The launch ledger is sampled around each run,
so a host-side shortcut that never launches a kernel cannot fake a passing
golden or a passing verification.

Goldens are stored as JSON under ``workspace / spec.snapshot_dir`` so the
disk-reconciler treats them as satisfaction artifacts, exactly like the BF-6
``.txt`` snapshots.

Public API
----------
GpuGoldenSpec
    Frozen description of what to characterize (name, snapshot_dir, tolerance).
GpuRunResult
    What a GPU runner returns for one fixed input (reduced buffer, validation
    pass/fail, error bound).
capture_gpu_golden(spec, runner, workspace) -> CaptureResult
    Observer phase: run the collective and write the golden artifact.
verify_gpu_golden(spec, runner, workspace) -> VerifyResult
    Verifier phase: re-run and compare against the golden within tolerance.

integration: bob.acceptance.characterization
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable

# integration: bob.acceptance.characterization — this GPU harness is the
# C++/GPU counterpart of the BF-6 Python characterization AC kind; keeping the
# import here documents (and enforces) that the two live in the same subsystem.
import bob.acceptance.characterization  # noqa: F401
from hippy.dispatch_facade import get_launch_count

__all__ = [
    "GpuGoldenSpec",
    "GpuRunResult",
    "CaptureResult",
    "VerifyResult",
    "capture_gpu_golden",
    "verify_gpu_golden",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GpuGoldenSpec:
    """What to characterize for a C++/GPU collective.

    Attributes:
        name:            Stable identifier for this collective/input pair; used
                         as the golden filename stem.
        snapshot_dir:    Workspace-relative directory where the golden artifact
                         is stored (so the disk-reconciler counts it).
        tolerance:       Absolute+relative numeric tolerance for comparing
                         reduced-buffer elements (>= 0). ``0.0`` requires an
                         exact match.
        max_error_bound: Optional cap on the collective's own reported error
                         bound; a verify run whose error bound exceeds this
                         fails even if the buffer matches. ``None`` disables it.
    """

    name: str
    snapshot_dir: str
    tolerance: float = 1e-5
    max_error_bound: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("GpuGoldenSpec.name must be a non-empty string")
        if not isinstance(self.snapshot_dir, str) or not self.snapshot_dir.strip():
            raise ValueError("GpuGoldenSpec.snapshot_dir must be a non-empty string")
        if not isinstance(self.tolerance, (int, float)) or isinstance(self.tolerance, bool):
            raise ValueError("GpuGoldenSpec.tolerance must be a number")
        if self.tolerance < 0:
            raise ValueError("GpuGoldenSpec.tolerance must be non-negative")
        if self.max_error_bound is not None:
            if (
                not isinstance(self.max_error_bound, (int, float))
                or isinstance(self.max_error_bound, bool)
                or self.max_error_bound < 0
            ):
                raise ValueError("GpuGoldenSpec.max_error_bound must be a non-negative number or None")


@dataclass(frozen=True)
class GpuRunResult:
    """One fixed-input run of a C++/GPU collective.

    Attributes:
        reduced_buffer:    The device-reduced output buffer, as host floats.
        validation_passed: Whether the collective's own validation harness
                           (e.g. rccl-tests) reported a correct result.
        error_bound:       The maximum observed absolute error the collective
                           reported for this run (0.0 if it reports none).
    """

    reduced_buffer: list[float]
    validation_passed: bool = True
    error_bound: float = 0.0


@dataclass
class CaptureResult:
    """Outcome of the observer phase."""

    success: bool
    golden_path: pathlib.Path
    details: str


@dataclass
class VerifyResult:
    """Outcome of the verifier phase."""

    passed: bool
    details: str
    max_abs_diff: float = 0.0
    diffs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_call(spec: Any, runner: Any) -> None:
    if not isinstance(spec, GpuGoldenSpec):
        raise ValueError(f"spec must be a GpuGoldenSpec, got {type(spec).__name__}")
    if not callable(runner):
        raise ValueError("runner must be a callable returning a GpuRunResult")


def _run_with_dispatch_evidence(runner: Callable[[], Any]) -> tuple[GpuRunResult, int]:
    """Invoke *runner*, returning its result and the number of device dispatches.

    The launch ledger is sampled before and after the run; the delta is the
    number of real device kernel dispatches observed for this run. Because the
    ledger is advanced ONLY by :func:`hippy.dispatch_facade.dispatch_launch`
    (never by host code), a host-side shortcut yields a delta of zero.
    """
    before = get_launch_count()
    result = runner()
    after = get_launch_count()

    if not isinstance(result, GpuRunResult):
        raise ValueError(
            f"runner must return a GpuRunResult, got {type(result).__name__}"
        )
    return result, after - before


def _golden_path(spec: GpuGoldenSpec, workspace: pathlib.Path) -> pathlib.Path:
    slug = "".join(c if c.isalnum() or c in "_-" else "_" for c in spec.name)
    return workspace / spec.snapshot_dir / f"gpu_golden_{slug}.json"


def _within_tolerance(baseline: list[float], current: list[float], tol: float) -> tuple[bool, float, list[str]]:
    """Compare two buffers element-wise with a combined abs+rel tolerance."""
    diffs: list[str] = []
    if len(baseline) != len(current):
        diffs.append(
            f"buffer length changed: golden={len(baseline)} current={len(current)}"
        )
        return False, math.inf, diffs

    max_abs = 0.0
    ok = True
    for i, (b, c) in enumerate(zip(baseline, current)):
        abs_diff = abs(float(c) - float(b))
        max_abs = max(max_abs, abs_diff)
        allowed = tol + tol * abs(float(b))
        if abs_diff > allowed:
            ok = False
            diffs.append(f"index {i}: golden={b} current={c} abs_diff={abs_diff} > allowed={allowed}")
    return ok, max_abs, diffs


# ---------------------------------------------------------------------------
# Observer phase
# ---------------------------------------------------------------------------


def capture_gpu_golden(
    spec: GpuGoldenSpec,
    runner: Callable[[], GpuRunResult],
    workspace: pathlib.Path | str,
) -> CaptureResult:
    """Observer phase: run the collective and write the golden artifact.

    Runs *runner* (which builds/launches the C++/GPU collective against fixed
    inputs) and persists a golden JSON artifact under ``spec.snapshot_dir``. The
    capture only SUCCEEDS if the run actually dispatched a device kernel — a
    host-only run advances no launch evidence and is rejected, so a fake golden
    cannot be captured.

    Args:
        spec:      The :class:`GpuGoldenSpec` describing what to characterize.
        runner:    A zero-arg callable returning a :class:`GpuRunResult`. It must
                   route its device work through ``dispatch_launch`` so launch
                   evidence is observable.
        workspace: Project workspace root (path or string).

    Returns:
        A :class:`CaptureResult`.

    Raises:
        ValueError: If *spec* is not a :class:`GpuGoldenSpec`, *runner* is not
                    callable, or *runner* does not return a :class:`GpuRunResult`.
    """
    _validate_call(spec, runner)
    ws = pathlib.Path(workspace)
    golden_path = _golden_path(spec, ws)

    result, dispatches = _run_with_dispatch_evidence(runner)

    if dispatches <= 0:
        return CaptureResult(
            success=False,
            golden_path=golden_path,
            details=(
                "observer run dispatched no device kernel; cannot capture a GPU "
                "golden from a host-side shortcut (launch evidence not advanced)"
            ),
        )

    payload = {
        "name": spec.name,
        "tolerance": spec.tolerance,
        "max_error_bound": spec.max_error_bound,
        "reduced_buffer": [float(x) for x in result.reduced_buffer],
        "validation_passed": bool(result.validation_passed),
        "error_bound": float(result.error_bound),
        "dispatches": dispatches,
    }

    golden_path.parent.mkdir(parents=True, exist_ok=True)
    golden_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    return CaptureResult(
        success=True,
        golden_path=golden_path,
        details=f"captured GPU golden for {spec.name!r} ({dispatches} dispatch(es))",
    )


# ---------------------------------------------------------------------------
# Verifier phase
# ---------------------------------------------------------------------------


def verify_gpu_golden(
    spec: GpuGoldenSpec,
    runner: Callable[[], GpuRunResult],
    workspace: pathlib.Path | str,
) -> VerifyResult:
    """Verifier phase: rebuild, re-run, and compare against the golden.

    Fails when any of the following hold:

    * the golden artifact is missing (observer phase never ran);
    * the re-run dispatched **no** device kernel (a host-side shortcut cannot
      fake a passing verification — the dispatch-coupled anti-cheat);
    * correctness regressed (validation flipped from pass to fail);
    * the reduced buffer drifted outside ``spec.tolerance``; or
    * the observed error bound exceeds ``spec.max_error_bound`` (when set).

    Args:
        spec:      The :class:`GpuGoldenSpec` describing what to characterize.
        runner:    A zero-arg callable returning a :class:`GpuRunResult`.
        workspace: Project workspace root (path or string).

    Returns:
        A :class:`VerifyResult`.

    Raises:
        ValueError: If *spec* is not a :class:`GpuGoldenSpec`, *runner* is not
                    callable, or *runner* does not return a :class:`GpuRunResult`.
    """
    _validate_call(spec, runner)
    ws = pathlib.Path(workspace)
    golden_path = _golden_path(spec, ws)

    if not golden_path.exists():
        return VerifyResult(
            passed=False,
            details=(
                f"golden artifact missing: {golden_path}. Run the observer phase "
                "(capture_gpu_golden) first."
            ),
        )

    golden = json.loads(golden_path.read_text(encoding="utf-8"))

    result, dispatches = _run_with_dispatch_evidence(runner)

    if dispatches <= 0:
        return VerifyResult(
            passed=False,
            details=(
                "verifier run dispatched no device kernel; a host-side shortcut "
                "cannot satisfy the dispatch-coupled GPU characterization"
            ),
        )

    # Correctness regression: validation flipped to fail.
    if golden.get("validation_passed", True) and not result.validation_passed:
        return VerifyResult(
            passed=False,
            details="correctness regressed: collective validation now fails against fixed inputs",
        )

    # Numeric tolerance on the reduced buffer.
    ok, max_abs, diffs = _within_tolerance(
        [float(x) for x in golden.get("reduced_buffer", [])],
        [float(x) for x in result.reduced_buffer],
        spec.tolerance,
    )
    if not ok:
        return VerifyResult(
            passed=False,
            details=(
                f"reduced buffer drifted outside tolerance {spec.tolerance} "
                f"(max abs diff {max_abs})"
            ),
            max_abs_diff=max_abs,
            diffs=diffs,
        )

    # Error-bound cap.
    if spec.max_error_bound is not None and result.error_bound > spec.max_error_bound:
        return VerifyResult(
            passed=False,
            details=(
                f"observed error bound {result.error_bound} exceeds allowed maximum "
                f"{spec.max_error_bound}"
            ),
            max_abs_diff=max_abs,
        )

    return VerifyResult(
        passed=True,
        details=(
            f"GPU golden for {spec.name!r} verified within tolerance {spec.tolerance} "
            f"(max abs diff {max_abs}, {dispatches} dispatch(es))"
        ),
        max_abs_diff=max_abs,
    )
