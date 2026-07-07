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

Public API::

    from hippy.backend_required_check import (
        is_harness_feature,
        backend_required_check,
    )
"""

from __future__ import annotations

from typing import Optional

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
