"""Backend-required check — exempt harness/test-infrastructure features.

Discovered building hippy/hipsci: the backend-required check false-failed a
"curated upstream test port + xfail taxonomy" feature — a TEST-INFRASTRUCTURE
feature that legitimately writes no device code but whose description mentions
GPU concepts. Requiring real backend usage from a harness feature is wrong and
wedges it at ``needs_human``. The inverse of F-R7-640: not every feature that
NAMES the backend must USE it.

Classification rules
--------------------
* A feature is *harness* when its text contains a harness/test-infrastructure
  marker (test port, upstream test, xfail, taxonomy, ratchet, conftest,
  anti-cheat, measurement protocol, benchmark report, coverage signal, import
  guard, pass-rate, tolerance policy, dispatch/protocol, array-api,
  get_array_module, ...). Harness features are EXEMPT from the backend
  requirement even if their text also contains compute keywords.
* A feature is *compute* (backend-required) only when it is NOT harness AND its
  text contains a *specific* compute marker (kernel, hiprtc, ufunc, matmul,
  gemm, linalg, fft, reduction, elementwise, device-memory, ...). The
  compute-marker set is deliberately specific: bare tokens like "hip" or
  "device" match any incidental mention and MUST NOT trigger the gate.

Classification consults the title first (unambiguous), then falls back to the
fuller description blob only when the title gives no signal — so an incidental
compute word in a harness feature's body does not mislabel it.

Feature 7cd64ec1 hardens the *file-scanning* half of the gate (F-R7-639): the
check MUST scope its source scan to the feature's OWN recently-modified files
(not the cumulative ``src/`` tree) AND FAIL on simulation-admission markers
even when a real backend reference is also present. That file-level logic lives
in :mod:`hippy.verifier`; this module re-exports it under the AC-named
:func:`check_backend_required` / :func:`detect_simulation_admission` symbols so
callers have one import surface.

Public API::

    from hippy.backend_required_check import (
        is_harness_feature,
        backend_required_check,
        check_backend_required,
        detect_simulation_admission,
    )
"""

from __future__ import annotations

import pathlib
from typing import Iterable, Optional

# Harness / test-infrastructure / bookkeeping markers. A feature carrying any
# of these legitimately writes no device code even when it mentions GPU
# concepts — exempt it from the backend-required gate.
HARNESS_MARKERS = (
    "test port", "upstream test", "xfail", "taxonomy", "ratchet",
    "conftest", "anti-cheat", "anticheat", "measurement protocol",
    "benchmark report", "coverage signal", "import guard", "pass-rate",
    "pass rate", "tolerance policy", "dispatch", "protocol", "array api",
    "array-api", "get_array_module",
)

# Specific compute markers that indicate real GPU/HIP compute intent.
# Deliberately specific — no bare "hip" / "device" which match any mention.
COMPUTE_MARKERS = (
    "kernel", "hiprtc", "ufunc", "matmul", "gemm", "linalg", "fft",
    "reduction", "elementwise", "device memory", "device-memory",
    "hipblas", "hipfft", "hipsolver", "hiprand", "hipsparse", "rocm",
    "convolution", "scatter", "gather",
)


def _validate_text(value: object, field: str) -> str:
    if value is None:
        raise ValueError(f"{field} must be a string, got None")
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string, got {type(value).__name__}")
    return value


def is_harness_feature(
    title: str, description: Optional[str] = None
) -> bool:
    """Return True if the feature is harness/test-infrastructure.

    Consults the title first; falls back to the description only when the title
    contains no harness marker. Raises ``ValueError`` on non-string input.
    """
    title = _validate_text(title, "title")
    if description is not None:
        description = _validate_text(description, "description")

    title_low = title.lower()
    if any(m in title_low for m in HARNESS_MARKERS):
        return True

    if description:
        blob = f"{title_low} {description.lower()}"
        if any(m in blob for m in HARNESS_MARKERS):
            return True

    return False


def backend_required_check(
    title: str, description: Optional[str] = None
) -> dict:
    """Classify a feature and decide whether the backend gate applies.

    Returns a dict with keys:
      * ``is_harness`` (bool) — feature is test-infrastructure/harness.
      * ``backend_required`` (bool) — the backend-required gate should be
        emitted for this feature.
      * ``reason`` (str) — human-readable explanation.

    A harness feature is always exempt (``backend_required`` False), even if it
    also names compute keywords. A non-harness feature is backend-required only
    when a specific compute marker is present. Raises ``ValueError`` on
    non-string input.
    """
    title = _validate_text(title, "title")
    if description is not None:
        description = _validate_text(description, "description")

    harness = is_harness_feature(title, description)
    if harness:
        return {
            "is_harness": True,
            "backend_required": False,
            "reason": (
                "Feature is harness/test-infrastructure (matches a harness "
                "marker); backend-required check is exempt even though it may "
                "mention GPU concepts."
            ),
        }

    title_low = title.lower()
    blob = title_low
    if description:
        blob = f"{title_low} {description.lower()}"
    is_compute = any(m in blob for m in COMPUTE_MARKERS)

    if is_compute:
        return {
            "is_harness": False,
            "backend_required": True,
            "reason": (
                "Feature contains a specific compute marker and is not "
                "classified as harness; real backend usage is required."
            ),
        }

    return {
        "is_harness": False,
        "backend_required": False,
        "reason": (
            "Feature is neither harness nor a specific-compute feature; "
            "incidental GPU-keyword mentions do not require backend usage."
        ),
    }


def has_real_call_site(source: str) -> bool:
    """Return True iff *source* contains a real backend CALL site.

    The import-but-simulate cheat (``import hipblas  # noqa: F401`` plus a
    docstring "dispatches to hipblasXgemm" while the code path is pure-Python
    CPU math) defeats import-only detection. A bare import or a prose mention
    of a backend symbol is NOT a call site — only a call-shaped occurrence
    (symbol immediately followed by ``(``) counts. Delegates to
    :func:`hippy.checks.backend_required_call_site.has_real_call_site`.

    Raises:
        ValueError: When *source* is not a ``str`` — invalid input must not
            silently succeed.
    """
    from hippy.checks.backend_required_call_site import (
        has_real_call_site as _impl,
    )

    return _impl(source)


def has_simulation_marker(source: str) -> bool:
    """Return True iff *source* admits it is a simulation / CPU fallback.

    Matches the import-but-simulate tells ("simulate hip", "on a live gpu",
    "cpu fallback", "pure-python compute", "emulate", …) case-insensitively.
    Delegates to
    :func:`hippy.checks.backend_required_call_site.has_simulation_marker`.

    Raises:
        ValueError: When *source* is not a ``str``.
    """
    from hippy.checks.backend_required_call_site import (
        has_simulation_marker as _impl,
    )

    return _impl(source)


def detect_simulation_admission(text: str) -> bool:
    """Return True when *text* admits a pure-Python simulation of GPU/HIP work.

    A simulation admission ("simulated device memory", "in a real GPU ... here
    it does not", "would wrap a hipStream", ...) marks a fake regardless of
    whether the same text also references the real backend. Delegates to the
    scoped implementation in :mod:`hippy.verifier`.

    Raises:
        ValueError: When *text* is not a ``str`` — invalid input must not
            silently succeed.
    """
    from hippy.verifier import has_simulation_admission

    return has_simulation_admission(text)


def check_backend_required(
    files: Iterable[pathlib.Path],
    feature_start_time: Optional[float] = None,
    is_harness: bool = False,
) -> dict:
    """Check a compute feature's OWN modified files for real HIP backend use.

    Scopes the scan to the feature's recently-modified files (keyed on
    *feature_start_time*, with a full-scan fallback when the window is empty)
    and FAILS when any file admits a simulation OR none reference the real
    backend. Harness/test-infra features (``is_harness=True``) are exempt.
    Delegates to :func:`hippy.verifier.backend_required_check`.

    Returns:
        ``{"passed": bool, "reason": str, "scanned": list[str]}``.

    Raises:
        ValueError: When *files* is ``None`` or not iterable — invalid input
            must not silently succeed.
    """
    from hippy.verifier import backend_required_check as _scoped_check

    return _scoped_check(
        files, feature_start_time=feature_start_time, is_harness=is_harness
    )
