"""Permanent-carry allowlist — exempt forward-carried infra features from the spec quality gate.

The 0.85 spec_quality_score gate is right for newly synthesized features, but blocks
permanent forward-carry infrastructure features (F-R7-478 unlimited spawn retry,
F-R7-479 RCA-layer NH auto-reset, F-R7-481 slopsquatting local-module exclusion)
whose ACs are intentionally terse and score in the 0.6-0.75 range.

A prior generation incident: feature 0ab56ae2 (F-R7-478-equivalent) was blocked at
score=0.6375 despite being a MUST-CARRY-FORWARD feature per user directive.

Usage::

    from spec_quality_gate.allowlist import is_feature_allowlisted

    if is_feature_allowlisted(feature_id, feature_name, spec_slot, permanent_forward_carry):
        # skip spec_quality gate — this is a MUST-CARRY-FORWARD feature
        promotable_ids.append(fid)
    else:
        allowed, block_msg = gate_for_ready(quality_report)

Alternatively, with a feature object::

    from spec_quality_gate.allowlist import is_feature_allowlisted

    if is_feature_allowlisted(feature=feature_obj):
        promotable_ids.append(feature_obj.id)
"""

from __future__ import annotations

import os
from typing import Any

_DEFAULT_ALLOWLIST_PATTERNS: list[str] = [
    "F-R7-478",  # unlimited spawn retry
    "F-R7-479",  # RCA-layer NH auto-reset
    "F-R7-481",  # slopsquatting local-module exclusion
]


def load_allowlist_patterns() -> list[str]:
    """Return the list of allowlisted spec_slot patterns.

    Reads from ``BOB3_ALLOWLIST_PATTERNS`` environment variable when set.
    The variable is a comma-separated list of additional patterns. An empty
    string falls back to the hardcoded defaults.

    Returns
    -------
    list[str]
        Deduplicated list of pattern strings to match against feature spec_slot or name.
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


def is_feature_allowlisted(
    feature: Any = None,
    *,
    feature_id: str | None = None,
    feature_name: str | None = None,
    spec_slot: str | None = None,
    permanent_forward_carry: bool = False,
) -> bool:
    """Return True when a feature is exempt from the spec_quality_score gate.

    Accepts either a feature object (first positional argument) or explicit
    keyword arguments for each field. When a feature object is provided, its
    attributes take precedence over keyword arguments.

    A feature is exempt when ANY of the following hold:

    1. ``permanent_forward_carry`` is True (explicit DB flag or kwarg).
    2. ``spec_slot`` contains any allowlisted pattern as a substring.
    3. ``feature_name`` contains any allowlisted pattern as a substring.

    The default allowlist covers three canonical infra slots:
    F-R7-478 (unlimited spawn retry), F-R7-479 (RCA-layer NH auto-reset),
    F-R7-481 (slopsquatting local-module exclusion). Extend via the
    ``BOB3_ALLOWLIST_PATTERNS`` env var (comma-separated additional patterns).

    Parameters
    ----------
    feature:
        Optional feature object with ``permanent_forward_carry``, ``spec_slot``,
        and ``name`` attributes. Must not be None when provided as a positional arg
        without keyword arguments.
    feature_id:
        Optional feature UUID string (not currently matched against allowlist patterns,
        reserved for future UUID-based exemptions).
    feature_name:
        Feature name string. Used for pattern matching when no feature object is given.
    spec_slot:
        Spec slot identifier (e.g. ``"F-R7-478"``). Used for pattern matching.
    permanent_forward_carry:
        Explicit flag to mark a feature as permanently exempt regardless of patterns.

    Returns
    -------
    bool
        True when the feature is exempt and may bypass the quality gate.

    Raises
    ------
    ValueError
        When *feature* is not a valid feature object (None passed without other args,
        or a primitive type like int/str/dict that cannot carry feature attributes).
    """
    if feature is not None:
        # Validate that the feature argument is a proper object, not a primitive
        if isinstance(feature, (int, float, str, bytes, dict, list, tuple, set, frozenset)):
            raise ValueError(
                f"feature must be a Feature model instance, not a primitive "
                f"{type(feature).__name__!r}. Pass a Feature object or use keyword arguments."
            )
        # Extract attributes from the feature object
        _permanent_forward_carry = bool(getattr(feature, "permanent_forward_carry", False))
        _spec_slot = getattr(feature, "spec_slot", None) or ""
        _feature_name = getattr(feature, "name", None) or ""
    elif feature is None and feature_id is None and feature_name is None and spec_slot is None and not permanent_forward_carry:
        # All args are default/None — treat as a call with no positional feature arg
        # This is the boundary case: return False without raising
        _permanent_forward_carry = False
        _spec_slot = ""
        _feature_name = ""
    else:
        _permanent_forward_carry = permanent_forward_carry
        _spec_slot = spec_slot or ""
        _feature_name = feature_name or ""

    if _permanent_forward_carry:
        return True

    patterns = load_allowlist_patterns()
    if not patterns:
        return False

    for pattern in patterns:
        if pattern in _spec_slot or pattern in _feature_name:
            return True

    return False


def is_permanent_forward_carry(feature: Any) -> bool:
    """Return True if *feature* is exempt from the spec_quality_score gate.

    A feature is exempt when ANY of the following hold:

    1. ``feature.permanent_forward_carry`` is True (explicit DB flag).
    2. ``feature.spec_slot`` contains any allowlisted pattern as a substring.
    3. ``feature.name`` contains any allowlisted pattern as a substring.

    This is the canonical single-argument form of :func:`is_feature_allowlisted`
    for callers that always have a feature object.

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None or a primitive.

    Returns
    -------
    bool
        True when the feature is exempt from the quality gate.

    Raises
    ------
    ValueError
        When *feature* is None or a primitive type that cannot carry feature attributes.
    """
    if feature is None:
        raise ValueError(
            "feature must not be None; provide a Feature model instance."
        )
    return is_feature_allowlisted(feature)
