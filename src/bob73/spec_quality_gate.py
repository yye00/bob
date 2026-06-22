"""Spec quality gate — permanent-carry allowlist for bob73.

Exposes ``is_permanent_forward_carry`` to check whether a feature is exempt
from the 0.85 spec_quality_score gate.

The 0.85 gate is correct policy for newly synthesized features. Permanent
forward-carry infra features (F-R7-478, F-R7-479, F-R7-481) have intentionally
terse ACs that score 0.6-0.75 and must not be blocked.

Usage::

    from bob73.spec_quality_gate import is_permanent_forward_carry

    if is_permanent_forward_carry(feature):
        # skip the quality gate — MUST-CARRY-FORWARD feature
        promotable_ids.append(fid)
    else:
        allowed, block_msg = gate_for_ready(quality_report)
        ...

Integration with bob3.spec_synthesizer::

    from bob73.spec_quality_gate import is_permanent_forward_carry
    import bob3.spec_synthesizer  # synthesizer uses bob3.spec_quality_allowlist internally
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob3.models import Feature

# Default allowlisted spec_slot patterns — permanent infra features exempt from quality gate.
_DEFAULT_ALLOWLIST_PATTERNS: list[str] = [
    "F-R7-478",  # unlimited spawn retry
    "F-R7-479",  # RCA-layer NH auto-reset
    "F-R7-481",  # slopsquatting local-module exclusion
]

__all__ = ["is_permanent_forward_carry", "load_allowlist_patterns"]


def load_allowlist_patterns() -> list[str]:
    """Return the list of allowlisted spec_slot patterns.

    Reads ``BOB3_ALLOWLIST_PATTERNS`` env var if set (comma-separated).
    Falls back to the hardcoded defaults when the var is absent or empty.
    """
    env_val = os.environ.get("BOB3_ALLOWLIST_PATTERNS", "")
    if env_val.strip():
        raw = [p.strip() for p in env_val.split(",")]
        seen: set[str] = set()
        patterns: list[str] = []
        for p in raw:
            if p and p not in seen:
                seen.add(p)
                patterns.append(p)
        return patterns
    return list(dict.fromkeys(_DEFAULT_ALLOWLIST_PATTERNS))


def is_permanent_forward_carry(feature: "Feature") -> bool:
    """Return True when *feature* is exempt from the 0.85 spec_quality_score gate.

    A feature is exempt when ANY of the following hold:

    1. ``feature.permanent_forward_carry`` is True (explicit DB flag).
    2. ``feature.spec_slot`` contains any allowlisted pattern as a substring.
    3. ``feature.name`` contains any allowlisted pattern as a substring.

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None and must have
        ``permanent_forward_carry``, ``spec_slot``, and ``name`` attributes.

    Returns
    -------
    bool
        True when the feature is exempt and may bypass the quality gate.

    Raises
    ------
    ValueError
        When *feature* is None.
    AttributeError
        When *feature* lacks required feature attributes.
    """
    if feature is None:
        raise ValueError(
            "feature must not be None; provide a Feature model instance."
        )
    if not hasattr(feature, "permanent_forward_carry"):
        raise AttributeError(
            f"feature must be a Feature model instance with 'permanent_forward_carry' "
            f"attribute; got {type(feature).__name__!r}."
        )

    if feature.permanent_forward_carry:
        return True

    patterns = load_allowlist_patterns()
    if not patterns:
        return False

    spec_slot = getattr(feature, "spec_slot", None) or ""
    name = getattr(feature, "name", None) or ""

    for pattern in patterns:
        if pattern in spec_slot or pattern in name:
            return True

    return False
