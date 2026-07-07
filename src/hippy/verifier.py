"""hippy.verifier — backend-required check scoped to a feature's own files.

Feature 91fee1a2. The F-R7-639 backend-required check had two holes a
sub-agent exploited when building hippy/hipsci:

1. **Cumulative scan.** It scanned ALL of ``src/`` cumulatively, so once the
   real HIP facade existed, EVERY later compute feature passed trivially —
   even when its OWN new modules were pure-Python fakes — because the facade
   file (written by an earlier feature) still matched the backend markers.

2. **Docstring-only reference.** A module could reference the backend in a
   docstring/comment AND still be a simulation. One feature shipped a
   "4 GiB simulated device memory" pool and a ``Stream`` class admitting
   "in a real GPU implementation each Stream would wrap a hipStream_t; here
   [it does not]", which passed because *other* files in the blast radius
   used HIP.

Fix (spec-over-code): the backend-required check MUST (a) scope its source
scan to the feature's OWN recently-modified files — reuse the verifier's
recently-modified-files window keyed on ``feature_start_time``, NOT the
cumulative src tree — so each feature is judged on its own work; and (b) FAIL
on simulation-admission markers even when a real backend reference is also
present. Harness / test-infra features remain exempt (F-R7-641). The mtime
window falls back to a full scan only when it yields nothing (clock skew /
re-run).

Behaviour: WHEN a compute feature's own modified files contain a simulation
admission OR none of them reference the real backend THEN the check FAILS.
"""

from __future__ import annotations

import pathlib
import re
import time
from typing import Iterable

from hippy.baseline_gate import (  # noqa: F401 — integration: stable baseline gate
    BaselineResult,
    BaselineUnstableError,
    capture_baseline,
    collects_cleanly,
)

__all__ = [
    "backend_required_check",
    "has_simulation_admission",
    "scope_to_modified_files",
    "capture_baseline",
    "collects_cleanly",
    "BaselineResult",
    "BaselineUnstableError",
]


# Tokens that betray a pure-Python simulation masquerading as GPU code, even
# when a genuine backend reference is also present in the same file. Mirrors
# the marker set hardened in bob.superpowers over successive cheat rounds.
_SIMULATION_MARKERS: tuple[str, ...] = (
    "simulated device", "simulated gpu", "simulated on-device",
    "simulation of", "simulated device memory", "in a real gpu",
    "in a real hip", "in a real implementation", "would wrap a hipstream",
    "fake gpu", "mock gpu", "pretend", "not actually on the gpu",
    "no real device", "simulate hipblas", "simulate hipfft",
    "simulate hiprand", "simulate hip", "on a live gpu",
    "hip-backed simulation",
    "simulating device memory", "simulates device memory",
    "host bytearray", "simulating device", "in-memory device",
    "device memory simulation", "emulate", "emulation",
)

# A genuine GPU implementation CALLS a hip lib function or launches a kernel.
# Importing the lib and mentioning it in a docstring is NOT enough; this regex
# matches actual call sites.
_REAL_CALL_RE = re.compile(
    r"hipblas[A-Za-z]*[Gg]emm\s*\(|hipblasCreate\s*\(|"
    r"hipblas[SDCZ][A-Za-z]+\s*\(|"
    r"hipfftExec\w*\s*\(|hipfft(Make)?Plan\w*\s*\(|"
    r"hiprtcCompileProgram\s*\(|hiprtcCreateProgram\s*\(|"
    r"hipModuleLaunchKernel\s*\(|hipModuleLoadData\s*\(|"
    r"hipMalloc\s*\(|hipMemcpy\w*\s*\(|hipMemset\w*\s*\(|"
    r"hiprandGenerate\w*\s*\(|hiprandCreateGenerator\w*\s*\(|"
    r"hipsolver[A-Za-z]+\s*\(|hipsparse[A-Za-z]+\s*\(|"
    r"hipLaunchKernel\w*\s*\(|hip\.hip[A-Z]\w+\s*\("
)

# A weaker "references the backend at all" signal (import / docstring mention).
# On its own this does NOT pass the check, but its absence is a definite fail.
_BACKEND_REFERENCE_RE = re.compile(
    r"from\s+hip\b|import\s+hip\b|hippy\._hip|"
    r"hiprtc|hipblas|hipfft|hipsolver|hiprand|hipsparse|"
    r"hipMalloc|hipModule|__global__|offload-arch|hip_check",
    re.IGNORECASE,
)

# Default lookback when no feature_start_time is supplied (1 hour).
_DEFAULT_LOOKBACK_SECONDS = 3600.0


def has_simulation_admission(text: str) -> bool:
    """Return True if *text* admits a pure-Python simulation of GPU/HIP work.

    A simulation admission (e.g. "simulated device memory", "in a real GPU
    ... here it does not", "would wrap a hipStream") is a fake regardless of
    whether the same text also references the real backend.

    Args:
        text: The source text to scan.

    Returns:
        True when any simulation-admission marker is present, else False.

    Raises:
        ValueError: When *text* is not a ``str`` — invalid input must not
            silently succeed.
    """
    if not isinstance(text, str):
        raise ValueError(
            f"text must be a str, got {type(text).__name__!r}"
        )
    low = text.lower()
    return any(marker in low for marker in _SIMULATION_MARKERS)


def scope_to_modified_files(
    files: Iterable[pathlib.Path],
    feature_start_time: float | None = None,
) -> list[pathlib.Path]:
    """Return only the files modified within the feature's own build window.

    Reuses the recently-modified-files window keyed on *feature_start_time* so
    each feature is judged on its OWN work, not the cumulative src tree. When
    the window yields nothing (clock skew, a re-run, or unset start time), fall
    back to the full list so the check still has something to judge rather than
    silently passing on an empty set.

    Args:
        files: Candidate source paths.
        feature_start_time: Epoch seconds marking the start of this feature's
            build. ``None`` uses a default 1-hour lookback from now.

    Returns:
        The subset of *files* newer than the window start; or the full list
        (materialised) when the window selects nothing.

    Raises:
        ValueError: When *files* is ``None`` — invalid input must not silently
            succeed.
    """
    if files is None:
        raise ValueError("files must be an iterable of paths, not None")

    all_files = list(files)
    if feature_start_time is not None:
        window_start = float(feature_start_time)
    else:
        window_start = time.time() - _DEFAULT_LOOKBACK_SECONDS

    recent: list[pathlib.Path] = []
    for f in all_files:
        try:
            if f.stat().st_mtime > window_start:
                recent.append(f)
        except OSError:
            continue

    return recent if recent else all_files


def backend_required_check(
    files: Iterable[pathlib.Path],
    feature_start_time: float | None = None,
    is_harness: bool = False,
) -> dict:
    """Check that a compute feature's own files use a real HIP backend.

    Scopes to the feature's OWN recently-modified files (via
    :func:`scope_to_modified_files`) and then requires that:

    * none of those files contain a simulation admission (see
      :func:`has_simulation_admission`), even when a real backend reference is
      also present; AND
    * at least one of those files contains a real HIP backend CALL (an actual
      call site, not merely an import or docstring mention).

    When *is_harness* is True the feature is exempt (harness / test-infra
    features legitimately write no device code, F-R7-641) and the check passes
    unconditionally.

    Args:
        files: Source paths written/modified by the feature.
        feature_start_time: Epoch seconds for the recently-modified window.
        is_harness: When True, exempt the feature from the backend requirement.

    Returns:
        ``{"passed": bool, "reason": str, "scanned": list[str]}``.

    Raises:
        ValueError: When *files* is ``None`` or not iterable — invalid input
            must not silently succeed.
    """
    if files is None:
        raise ValueError("files must be an iterable of paths, not None")
    try:
        candidates = list(files)
    except TypeError as exc:
        raise ValueError(
            f"files must be an iterable of paths, got {type(files).__name__!r}"
        ) from exc

    if is_harness:
        return {
            "passed": True,
            "reason": "Harness/test-infra feature is exempt from the "
                      "backend-required check (F-R7-641).",
            "scanned": [],
        }

    scoped = scope_to_modified_files(candidates, feature_start_time)
    py_files = [p for p in scoped if p.suffix == ".py"]

    if not py_files:
        return {
            "passed": False,
            "reason": "No modified Python source files to judge; a compute "
                      "feature must write real HIP backend code.",
            "scanned": [],
        }

    scanned: list[str] = []
    sim_hit: str | None = None
    real_call_seen = False
    backend_referenced = False

    for f in py_files:
        try:
            txt = f.read_text()
        except OSError:
            continue
        scanned.append(f.name)
        if sim_hit is None and has_simulation_admission(txt):
            low = txt.lower()
            marker = next(m for m in _SIMULATION_MARKERS if m in low)
            sim_hit = f"{f.name}: {marker!r}"
        if _REAL_CALL_RE.search(txt):
            real_call_seen = True
        if _BACKEND_REFERENCE_RE.search(txt):
            backend_referenced = True

    if sim_hit is not None:
        return {
            "passed": False,
            "reason": (
                f"Pure-Python SIMULATION detected ({sim_hit}). A simulation "
                "admission fails the check even when a real backend reference "
                "is also present — implement real HIP/GPU code (real call "
                "site) via the facade or JIT engine."
            ),
            "scanned": scanned,
        }

    if not (real_call_seen or backend_referenced):
        return {
            "passed": False,
            "reason": (
                "None of this feature's own modified files reference the real "
                "HIP backend. Importing a vendor lib in a docstring is not "
                "enough — implement a real device call (hipMalloc(), "
                "hipblasXgemm(), hipModuleLaunchKernel(), etc.)."
            ),
            "scanned": scanned,
        }

    return {
        "passed": True,
        "reason": "Feature's own files reference the real HIP backend with no "
                  "simulation admission.",
        "scanned": scanned,
    }
