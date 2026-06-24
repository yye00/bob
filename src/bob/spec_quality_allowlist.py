"""Allowlist of permanent forward-carry infrastructure features exempt from the 0.85 spec_quality_score gate.

Some infra features (F-R7-478 unlimited spawn retry, F-R7-479 RCA-layer NH auto-reset,
F-R7-481 slopsquatting local-module exclusion) have intentionally terse ACs that score
in the 0.6-0.75 range. These are MUST-CARRY-FORWARD features per user directive and must
not be blocked by the quality gate.

Usage::

    from bob.spec_quality_allowlist import is_permanent_forward_carry, load_allowlist_patterns

    if is_permanent_forward_carry(feature):
        # skip spec_quality gate
        promotable_ids.append(fid)
    else:
        allowed, block_msg = gate_for_ready(quality_report)
        ...
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bob.models import Feature

# Default set of spec_slot patterns whose features are permanently exempt from the quality gate.
# These correspond to known infra features that carry forward across generations by user directive.
_DEFAULT_ALLOWLIST_PATTERNS: list[str] = [
    "F-R7-478",  # unlimited spawn retry
    "F-R7-479",  # RCA-layer NH auto-reset
    "F-R7-481",  # slopsquatting local-module exclusion
]


def load_allowlist_patterns() -> list[str]:
    """Return the list of allowlisted spec_slot patterns.

    Reads from the ``BOB_ALLOWLIST_PATTERNS`` environment variable if set.
    The variable is a comma-separated list of patterns (e.g. ``"F-R7-478,F-R7-479"``).
    An empty string falls back to the hardcoded defaults.

    Returns
    -------
    list[str]
        Deduplicated list of pattern strings to match against feature spec_slot or name.
    """
    env_val = os.environ.get("BOB_ALLOWLIST_PATTERNS", "")
    if env_val.strip():
        raw = [p.strip() for p in env_val.split(",")]
        # Deduplicate while preserving order
        seen: set[str] = set()
        patterns: list[str] = []
        for p in raw:
            if p and p not in seen:
                seen.add(p)
                patterns.append(p)
        return patterns
    # Deduplicate defaults (they are already unique, but be defensive)
    return list(dict.fromkeys(_DEFAULT_ALLOWLIST_PATTERNS))


def is_permanent_forward_carry(feature: "Feature") -> bool:
    """Return True if *feature* is exempt from the spec_quality_score gate.

    A feature is exempt when ANY of the following hold:

    1. ``feature.permanent_forward_carry`` is True (explicit DB flag).
    2. ``feature.spec_slot`` contains any allowlisted pattern as a substring.
    3. ``feature.name`` contains any allowlisted pattern as a substring.

    This function is pure — it does not modify *feature* or any external state.

    Parameters
    ----------
    feature:
        The Feature model to inspect.

    Returns
    -------
    bool
        True when the feature is exempt from the quality gate.
    """
    # Explicit flag takes highest priority
    if getattr(feature, "permanent_forward_carry", False):
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
