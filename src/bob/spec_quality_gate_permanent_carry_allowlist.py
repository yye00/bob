"""Permanent-carry allowlist that exempts forward-carried infra features from the 0.85 gate.

The 0.85 spec_quality_score gate (F-R7-481-class) is the right policy for newly
synthesized features, but blocks permanent forward-carry infrastructure features
(F-R7-478 unlimited spawn retry, F-R7-479 RCA-layer NH auto-reset, F-R7-481
slopsquatting local-module exclusion) whose ACs are intentionally terse and score
in the 0.6-0.75 range.

A prior generation blocked feature 0ab56ae2 (F-R7-478-equivalent) at score=0.6375
despite being a MUST-CARRY-FORWARD feature per user directive. This module exposes
the two AC-required entry-points:

- :func:`is_permanent_forward_carry` — is the feature on the allowlist?
- :func:`bypass_quality_gate` — should the feature skip the 0.85 gate?

Both delegate to the shared allowlist logic in :mod:`bob.spec_quality_allowlist`,
after validating that a real Feature-shaped object (not None or a bare primitive)
was supplied.

Integration with :mod:`bob.spec_quality_gate`::

    from bob.spec_quality_gate import bypass_quality_threshold
    from bob.spec_quality_gate_permanent_carry_allowlist import bypass_quality_gate
    assert bypass_quality_gate(feature) == bypass_quality_threshold(feature)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bob.spec_quality_allowlist import (
    is_permanent_forward_carry as _is_permanent_forward_carry,
    load_allowlist_patterns,
)

if TYPE_CHECKING:
    from bob.models import Feature

__all__ = [
    "bypass_quality_gate",
    "is_permanent_forward_carry",
    "load_allowlist_patterns",
]

# Primitive types that can never carry the Feature attributes the allowlist inspects.
# Passing one of these is a programming error, not a "feature that is not exempt".
_PRIMITIVE_TYPES = (bool, int, float, complex, str, bytes, list, tuple, set, frozenset, dict)


def _validate_feature(feature: "Feature") -> None:
    """Raise ValueError when *feature* is None or a bare primitive.

    A Feature model exposes ``permanent_forward_carry``, ``spec_slot`` and
    ``name``. Passing None or a primitive (int, str, dict, ...) is an input
    error that must surface loudly rather than silently returning False.
    """
    if feature is None:
        raise ValueError(
            "feature must not be None; provide a Feature model instance."
        )
    if isinstance(feature, _PRIMITIVE_TYPES):
        raise ValueError(
            f"feature must be a Feature model instance, not a primitive "
            f"{type(feature).__name__!r}."
        )


def is_permanent_forward_carry(feature: "Feature") -> bool:
    """Return True when *feature* is on the permanent forward-carry allowlist.

    A feature is exempt when ANY of the following hold:

    1. ``feature.permanent_forward_carry`` is True (explicit DB flag).
    2. ``feature.spec_slot`` contains any allowlisted pattern as a substring.
    3. ``feature.name`` contains any allowlisted pattern as a substring.

    The default allowlist covers F-R7-478, F-R7-479, F-R7-481; additional
    patterns may be injected via ``BOB_ALLOWLIST_PATTERNS`` (comma-separated).

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None or a bare primitive.

    Returns
    -------
    bool
        True when the feature is on the permanent forward-carry allowlist.

    Raises
    ------
    ValueError
        When *feature* is None or a bare primitive (int, str, dict, ...).
    """
    _validate_feature(feature)
    return bool(_is_permanent_forward_carry(feature))


def bypass_quality_gate(feature: "Feature") -> bool:
    """Return True when *feature* should bypass the 0.85 spec_quality_score gate.

    Permanent forward-carry infrastructure features skip the gate entirely.
    This is the canonical AC-required entry-point; it delegates to
    :func:`is_permanent_forward_carry`.

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None or a bare primitive.

    Returns
    -------
    bool
        True when the feature should bypass the 0.85 quality gate.

    Raises
    ------
    ValueError
        When *feature* is None or a bare primitive (int, str, dict, ...).
    """
    return is_permanent_forward_carry(feature)
