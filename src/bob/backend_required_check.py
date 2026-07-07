"""Backend-required check — a compute feature MUST actually use its backend.

Discovered building hippy/hipsci with bob: after a conftest banned numpy/scipy
from ``src/`` (to stop CPU-wrapper cheating), sub-agents evaded it by writing
pure-Python "simulated GPU" implementations — a ``DeviceArray`` backed by a
Python list, a fake ``_launch_log`` "to provide evidence of device execution,"
and HIP mentioned ONLY in docstrings, with ZERO real ``from hip import`` /
hiprtc / vendor-library calls.  bob's AST stub/mock detector did not catch it
(the code is plausible, not a stub), and the parity tests passed because
pure-Python CPU math matches the CPU oracle.

The lesson generalizes: for a feature whose JOB is to run on a specific backend
(GPU/HIP, an FPGA, a remote service, a particular DB engine), FORBIDDING the
wrong substrate is not enough — the verifier MUST positively REQUIRE the right
substrate actually be used.

This module provides :func:`check_backend_required`, an **opt-in** check.  It is
gated by the ``BOB_REQUIRE_GPU_BACKEND`` environment variable and defaults to
OFF, so non-GPU projects and bob's own self-build are unaffected.

Behaviour
---------
WHEN the backend-required check is enabled AND a compute feature (its
description/ACs carry compute markers) wrote source files AND none of those
source files genuinely reference the required backend, THEN the check FAILS with
an explicit message.

Boundary: pure-harness/bookkeeping features (no compute markers) are EXEMPT and
emit no such check.  With the check disabled the behaviour is exactly as before
(no new gate), so unrelated projects are unaffected.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "BackendCheckResult",
    "check_backend_required",
    "COMPUTE_MARKERS",
    "HIP_BACKEND_MARKERS",
]

#: Markers in a feature's description/ACs that indicate it performs backend
#: compute.  Presence of ANY of these makes a feature "compute" (in-scope).
COMPUTE_MARKERS: tuple[str, ...] = (
    "gpu",
    "hip",
    "cuda",
    "kernel",
    "ufunc",
    "matmul",
    "linalg",
    "fft",
    "gemm",
    "blas",
    "device",
    "offload",
    "tensor",
    "convolution",
    "reduction",
)

#: Substrings that, when found in a source file, prove a genuine reference to
#: the HIP backend (not merely a docstring mention).  These are checked
#: case-insensitively against file contents.
HIP_BACKEND_MARKERS: tuple[str, ...] = (
    "from hip import",
    "import hip",
    "hiprtc",
    "hipmalloc",
    "hipmemcpy",
    "hiplaunch",
    "hipblas",
    "hipfft",
    "hipsolver",
    "hiprand",
    "hipsparse",
    "__global__",
    "--offload-arch",
    "offload-arch=",
)

#: Per-backend marker table.  Extendable for other required substrates.
_BACKEND_MARKERS: dict[str, tuple[str, ...]] = {
    "hip": HIP_BACKEND_MARKERS,
}

_ENV_FLAG = "BOB_REQUIRE_GPU_BACKEND"

_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


@dataclass
class BackendCheckResult:
    """Outcome of :func:`check_backend_required`.

    Attributes
    ----------
    passed:
        ``True`` when the check did not fail.  A disabled or exempt check
        always passes.
    status:
        One of ``"disabled"``, ``"exempt"``, ``"ok"`` or ``"backend_missing"``.
    enabled:
        Whether the gate was enabled via the environment flag.
    is_compute:
        Whether the feature was classified as a backend-compute feature.
    backend:
        The required backend name (e.g. ``"hip"``).
    reason:
        Human-readable explanation, always non-empty.
    offending_files / matched_files:
        Source files scanned that respectively LACK / CONTAIN a genuine
        backend reference.
    """

    passed: bool
    status: str
    enabled: bool
    is_compute: bool
    backend: str
    reason: str
    offending_files: list[str] = field(default_factory=list)
    matched_files: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.passed


def _env_enabled(env: Mapping[str, str] | None) -> bool:
    source = os.environ if env is None else env
    raw = source.get(_ENV_FLAG, "")
    return str(raw).strip().lower() in _TRUE_VALUES


def _feature_text(feature: Mapping[str, Any]) -> str:
    """Concatenate the description + ACs of *feature* into one lowercase blob."""
    parts: list[str] = []
    for key in ("description", "name", "title"):
        val = feature.get(key)
        if isinstance(val, str):
            parts.append(val)
    acs = feature.get("acceptance_criteria")
    if isinstance(acs, str):
        parts.append(acs)
    elif isinstance(acs, (list, tuple)):
        for ac in acs:
            if isinstance(ac, str):
                parts.append(ac)
    return "\n".join(parts).lower()


def _is_compute_feature(feature: Mapping[str, Any]) -> bool:
    blob = _feature_text(feature)
    if not blob:
        return False
    # Word-boundary match to avoid substrings like "device" inside unrelated
    # words being over-eager; but keep it forgiving for tokens like "matmul".
    for marker in COMPUTE_MARKERS:
        if re.search(r"\b" + re.escape(marker) + r"\b", blob):
            return True
    return False


def _file_references_backend(text: str, markers: Sequence[str]) -> bool:
    low = text.lower()
    return any(marker in low for marker in markers)


def check_backend_required(
    feature: Any,
    src_files: Any = None,
    *,
    workspace: str | Path | None = None,
    backend: str = "hip",
    env: Mapping[str, str] | None = None,
) -> BackendCheckResult:
    """Require a compute feature to genuinely reference its backend.

    Parameters
    ----------
    feature:
        A mapping with at least a ``description`` (and optionally ``name`` and
        ``acceptance_criteria``).  Must be a mapping — any other type raises
        :exc:`ValueError` (error path: the function does not silently succeed).
    src_files:
        Iterable of source file paths written by the feature.  ``None`` or an
        empty iterable is a well-defined boundary case: with nothing to scan the
        check cannot prove backend usage, so a compute feature with no source
        files is treated as having no evidence.  Non-iterable / non-path items
        raise :exc:`ValueError`.
    workspace:
        Optional root used to resolve relative *src_files* paths.
    backend:
        Required backend name.  Currently ``"hip"`` is supported; unknown
        backends raise :exc:`ValueError`.
    env:
        Optional environment mapping (defaults to :data:`os.environ`).  The gate
        is enabled only when ``BOB_REQUIRE_GPU_BACKEND`` is truthy.

    Returns
    -------
    BackendCheckResult
        ``result.passed`` is ``False`` only when the gate is enabled, the
        feature is a compute feature, and none of its source files reference the
        required backend.
    """
    if not isinstance(feature, Mapping):
        raise ValueError(
            f"feature must be a mapping, got {type(feature).__name__!r}"
        )

    backend_key = backend.strip().lower() if isinstance(backend, str) else backend
    if not isinstance(backend, str) or backend_key not in _BACKEND_MARKERS:
        raise ValueError(
            f"unsupported backend {backend!r}; known: {sorted(_BACKEND_MARKERS)}"
        )
    markers = _BACKEND_MARKERS[backend_key]

    # Normalise src_files into a list of paths (boundary: None -> []).
    if src_files is None:
        files: list[Any] = []
    elif isinstance(src_files, (str, bytes, Path)):
        raise ValueError(
            "src_files must be an iterable of paths, not a single path "
            f"({type(src_files).__name__!r}); wrap it in a list"
        )
    else:
        try:
            files = list(src_files)
        except TypeError as exc:
            raise ValueError(
                f"src_files must be iterable, got {type(src_files).__name__!r}"
            ) from exc

    enabled = _env_enabled(env)
    is_compute = _is_compute_feature(feature)

    if not enabled:
        return BackendCheckResult(
            passed=True,
            status="disabled",
            enabled=False,
            is_compute=is_compute,
            backend=backend_key,
            reason=(
                f"{_ENV_FLAG} is not set — backend-required check is disabled; "
                "no gate applied."
            ),
        )

    if not is_compute:
        return BackendCheckResult(
            passed=True,
            status="exempt",
            enabled=True,
            is_compute=False,
            backend=backend_key,
            reason=(
                "Feature has no compute markers "
                f"({', '.join(COMPUTE_MARKERS)}) — exempt from the "
                "backend-required check."
            ),
        )

    ws = Path(workspace) if workspace is not None else None
    matched: list[str] = []
    offending: list[str] = []

    for f in files:
        if not isinstance(f, (str, Path)):
            raise ValueError(
                f"src_files entries must be str or Path, got {type(f).__name__!r}"
            )
        p = Path(f)
        if ws is not None and not p.is_absolute():
            p = ws / p
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            offending.append(str(f))
            continue
        if _file_references_backend(text, markers):
            matched.append(str(f))
        else:
            offending.append(str(f))

    if matched:
        return BackendCheckResult(
            passed=True,
            status="ok",
            enabled=True,
            is_compute=True,
            backend=backend_key,
            reason=(
                f"Compute feature references the {backend_key!r} backend in: "
                f"{', '.join(matched)}."
            ),
            offending_files=offending,
            matched_files=matched,
        )

    detail = (
        "wrote no source files" if not files
        else f"none of its {len(files)} source file(s) reference the backend"
    )
    return BackendCheckResult(
        passed=False,
        status="backend_missing",
        enabled=True,
        is_compute=True,
        backend=backend_key,
        reason=(
            f"Compute feature must use the {backend_key!r} backend but {detail}. "
            f"At least one source file must genuinely reference {backend_key!r} "
            f"(e.g. one of: {', '.join(markers[:6])}, ...). "
            "Pure-Python 'simulated GPU' code does not satisfy this gate."
        ),
        offending_files=offending,
        matched_files=[],
    )
