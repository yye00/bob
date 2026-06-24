"""Threshold resolver for the spec-quality gate.

Reads BOB_SPEC_QUALITY_THRESHOLD from the environment on every call so that
operator changes (e.g. lowering the bar to unstick blocked features) take
effect on the next gate evaluation without requiring a process restart.

Escape hatch: set BOB_SPEC_QUALITY_THRESHOLD_FROZEN=<value> to pin the
threshold for the lifetime of the interpreter (useful in tests that need a
deterministic threshold regardless of the ambient env).
"""

from __future__ import annotations

import os

_DEFAULT = 0.85
_frozen_value: float | None = None
_frozen_initialized: bool = False


def resolve_spec_quality_threshold() -> float:
    """Return the minimum spec_quality_score required to promote a feature to 'ready'.

    Reads BOB_SPEC_QUALITY_THRESHOLD from the environment on every call
    (unless BOB_SPEC_QUALITY_THRESHOLD_FROZEN is set, in which case the
    frozen value is returned on all subsequent calls after the first).

    The returned value is clamped to the closed interval [0.0, 1.0].
    Unparseable or absent BOB_SPEC_QUALITY_THRESHOLD fall back to 0.85.

    Returns
    -------
    float
        Threshold in [0.0, 1.0].
    """
    global _frozen_value, _frozen_initialized

    frozen_raw = os.environ.get("BOB_SPEC_QUALITY_THRESHOLD_FROZEN")
    if frozen_raw is not None:
        if not _frozen_initialized:
            try:
                v = float(frozen_raw)
            except (TypeError, ValueError):
                v = _DEFAULT
            _frozen_value = max(0.0, min(1.0, v))
            _frozen_initialized = True
        return _frozen_value  # type: ignore[return-value]

    # Reset frozen state when FROZEN var is no longer set (env change between calls)
    if _frozen_initialized:
        _frozen_value = None
        _frozen_initialized = False

    raw = os.environ.get("BOB_SPEC_QUALITY_THRESHOLD")
    if not raw:
        return _DEFAULT
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT
    return max(0.0, min(1.0, v))
