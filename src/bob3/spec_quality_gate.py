"""Spec quality gate — permanent-carry allowlist exempts forward-carried infra features.

The 0.85 spec_quality_score gate is the right policy for newly synthesized features,
but blocks permanent forward-carry infrastructure features (F-R7-478, F-R7-479,
F-R7-481) whose ACs are intentionally terse and score in the 0.6-0.75 range.

A prior generation blocked feature 0ab56ae2 (F-R7-478-equivalent) at score=0.6375
despite being a MUST-CARRY-FORWARD feature per user directive. This module provides
``bypass_quality_threshold`` as the canonical entry-point to check whether a feature
should skip the quality gate.

Usage::

    from bob3.spec_quality_gate import bypass_quality_threshold

    if bypass_quality_threshold(feature):
        # skip the 0.85 spec_quality gate — MUST-CARRY-FORWARD feature
        promotable_ids.append(fid)
    else:
        allowed, block_msg = gate_for_ready(quality_report)
        ...

Integration with bob3.synthesizer::

    from bob3.spec_quality_gate import bypass_quality_threshold
    import bob3.synthesizer  # synthesizer uses bob3.spec_quality_gate internally
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Union

from bob3.spec_quality_allowlist import is_permanent_forward_carry, load_allowlist_patterns
from bob3.spec_quality_score import (
    compute_quality_score,
    generate_remediation_report,
)

if TYPE_CHECKING:
    from bob3.models import Feature

__all__ = [
    "bypass_quality_threshold",
    "check_allowlist",
    "check_permanent_carry_allowlist",
    "check_permanent_forward_carry_allowlist",
    "check_permanent_forward_carry_exemption",
    "check_quality_gate_exemption",
    "check_quality_gate_with_allowlist",
    "check_quality_score_gate",
    "compute_quality_score",
    "generate_remediation_report",
    "get_allowlist_config",
    "is_exempt_from_gate",
    "is_feature_exempted",
    "is_permanent_forward_carry",
    "load_allowlist",
    "load_allowlist_patterns",
    "should_bypass_quality_threshold",
]


def bypass_quality_threshold(feature: "Feature") -> bool:
    """Return True when *feature* should bypass the 0.85 spec_quality_score gate.

    A feature bypasses the gate when ANY of the following hold:

    1. ``feature.permanent_forward_carry`` is True (explicit DB flag).
    2. ``feature.spec_slot`` contains any allowlisted pattern as a substring.
    3. ``feature.name`` contains any allowlisted pattern as a substring.

    The default allowlist covers the three canonical infra slots:
    F-R7-478 (unlimited spawn retry), F-R7-479 (RCA-layer NH auto-reset),
    F-R7-481 (slopsquatting local-module exclusion).

    Additional patterns can be injected via ``BOB3_ALLOWLIST_PATTERNS``
    (comma-separated, e.g. ``"F-R7-478,F-R7-479"``).

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None and must have
        ``permanent_forward_carry``, ``spec_slot``, and ``name`` attributes.

    Returns
    -------
    bool
        True when the feature is exempt from the quality gate.

    Raises
    ------
    ValueError
        When *feature* is None.
    AttributeError
        When *feature* lacks required Feature model attributes.
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

    return bool(is_permanent_forward_carry(feature))


def should_bypass_quality_threshold(feature: "Feature") -> bool:
    """Return True when *feature* should bypass the 0.85 spec_quality_score gate.

    This is the canonical AC-required entry-point for feature e8fb54fe.
    Delegates to :func:`bypass_quality_threshold`.

    Permanent forward-carry infrastructure features (F-R7-478, F-R7-479, F-R7-481)
    whose ACs are intentionally terse and score in the 0.6-0.75 range are exempt
    from the standard 0.85 threshold. A prior generation blocked feature 0ab56ae2
    (F-R7-478-equivalent) at score=0.6375 despite being a MUST-CARRY-FORWARD feature.

    Integration with bob3.feature_reset: when a feature reset occurs (e.g. RCA
    infra-only verdict), the reset path may call this function to determine whether
    the feature should skip the quality gate on the next dispatch attempt. Callers in
    ``bob3.feature_reset`` can import and call this function directly.

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None and must have
        ``permanent_forward_carry``, ``spec_slot``, and ``name`` attributes.

    Returns
    -------
    bool
        True when the feature should bypass the 0.85 quality gate.

    Raises
    ------
    ValueError
        When *feature* is None.
    AttributeError
        When *feature* lacks required Feature model attributes.
    """
    return bypass_quality_threshold(feature)


# Alias: check_allowlist mirrors the bob72 interface and is used by orchestrator integrations.
check_allowlist = bypass_quality_threshold

# Alias: check_permanent_carry_allowlist is the canonical name for the AC-required function.
check_permanent_carry_allowlist = bypass_quality_threshold

# Alias: check_permanent_forward_carry_allowlist is the AC-required function name for feature 0bd45c0b.
check_permanent_forward_carry_allowlist = bypass_quality_threshold

# Alias: check_quality_gate_exemption is the function required by AC "Function defined: bob3.spec_quality_gate.check_quality_gate_exemption".
check_quality_gate_exemption = bypass_quality_threshold

# Alias: check_permanent_forward_carry_exemption is the AC-required function for feature a7cbafdc.
check_permanent_forward_carry_exemption = bypass_quality_threshold


def is_exempt_from_gate(feature: "Feature") -> bool:
    """Return True when *feature* is exempt from the spec_quality_score gate.

    This is the canonical AC-required entry-point for feature 3f732534.
    Delegates to :func:`bypass_quality_threshold`.

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None.

    Returns
    -------
    bool
        True when the feature should bypass the 0.85 quality gate.

    Raises
    ------
    ValueError
        When *feature* is None.
    AttributeError
        When *feature* lacks required Feature model attributes.
    """
    return bypass_quality_threshold(feature)


def load_allowlist() -> list[str]:
    """Return the list of allowlisted spec_slot patterns.

    This is the canonical AC-required entry-point for feature 3f732534.
    Delegates to :func:`load_allowlist_patterns` from bob3.spec_quality_allowlist.

    Returns
    -------
    list[str]
        Deduplicated list of pattern strings to match against feature spec_slot or name.
        Reads from ``BOB3_ALLOWLIST_PATTERNS`` env var if set; falls back to defaults
        (F-R7-478, F-R7-479, F-R7-481).
    """
    return load_allowlist_patterns()


def get_allowlist_config() -> dict[str, object]:
    """Return the current allowlist configuration as a dict.

    Returns a snapshot of the active allowlist state, including the list of
    patterns and the source (environment variable override or hardcoded defaults).
    This is the canonical AC-required entry-point for feature 3e6d1285.

    Returns
    -------
    dict[str, object]
        A dict with keys:
        - ``"patterns"``: list[str] — active allowlist patterns
        - ``"source"``: str — ``"env"`` when overridden via BOB3_ALLOWLIST_PATTERNS,
          otherwise ``"defaults"``
        - ``"threshold_bypass_score_range"``: tuple[float, float] — the score range
          (0.6, 0.75) where permanent-carry features typically land
        - ``"gate_threshold"``: float — the standard gate threshold (0.85)
    """
    import os as _os
    patterns = load_allowlist_patterns()
    source = "env" if _os.environ.get("BOB3_ALLOWLIST_PATTERNS", "").strip() else "defaults"
    return {
        "patterns": patterns,
        "source": source,
        "threshold_bypass_score_range": (0.6, 0.75),
        "gate_threshold": 0.85,
    }


def is_feature_exempted(feature: "Feature") -> bool:
    """Return True when *feature* is exempt from the spec_quality_score gate.

    This is the canonical AC-required entry-point for feature 3e6d1285.
    Delegates to :func:`bypass_quality_threshold`.

    A feature is exempt when ANY of the following hold:

    1. ``feature.permanent_forward_carry`` is True (explicit DB flag).
    2. ``feature.spec_slot`` contains any allowlisted pattern as a substring.
    3. ``feature.name`` contains any allowlisted pattern as a substring.

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None.

    Returns
    -------
    bool
        True when the feature should bypass the 0.85 quality gate.

    Raises
    ------
    ValueError
        When *feature* is None.
    AttributeError
        When *feature* lacks required Feature model attributes.
    """
    return bypass_quality_threshold(feature)


def check_quality_score_gate(feature: "Feature", quality_score: float, threshold: float = 0.85) -> bool:
    """Check whether a feature passes the spec quality score gate, with permanent-carry exemption.

    This is the canonical AC-required entry-point for feature e36fa467.
    Features on the permanent-carry allowlist bypass the threshold entirely.
    All other features must meet or exceed the threshold to pass.

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None and must have
        ``permanent_forward_carry``, ``spec_slot``, and ``name`` attributes.
    quality_score:
        The feature's computed spec_quality_score (0.0–1.0).
    threshold:
        Minimum score required to pass the gate (default 0.85).

    Returns
    -------
    bool
        True when the feature is allowed through the gate (either via allowlist
        exemption or by meeting/exceeding the quality_score threshold).

    Raises
    ------
    ValueError
        When *feature* is None or *quality_score* is not a float in [0.0, 1.0].
    AttributeError
        When *feature* lacks required Feature model attributes.
    """
    if feature is None:
        raise ValueError(
            "feature must not be None; provide a Feature model instance."
        )
    if not isinstance(quality_score, (int, float)) or not (0.0 <= float(quality_score) <= 1.0):
        raise ValueError(
            f"quality_score must be a float in [0.0, 1.0]; got {quality_score!r}."
        )
    if bypass_quality_threshold(feature):
        return True
    return float(quality_score) >= float(threshold)


def check_quality_gate_with_allowlist(feature: "Feature", quality_score: float, threshold: float = 0.85) -> bool:
    """Check whether a feature passes the spec quality gate, accounting for the permanent-carry allowlist.

    If the feature is on the permanent-carry allowlist (via flag or spec_slot/name pattern),
    the quality gate is bypassed and this function returns True (feature is promotable).
    Otherwise, returns True only when quality_score >= threshold.

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None and must have
        ``permanent_forward_carry``, ``spec_slot``, and ``name`` attributes.
    quality_score:
        The feature's computed spec_quality_score (0.0–1.0).
    threshold:
        Minimum score required to pass the gate (default 0.85).

    Returns
    -------
    bool
        True when the feature is allowed through the gate (either via allowlist
        exemption or by meeting/exceeding the quality_score threshold).

    Raises
    ------
    ValueError
        When *feature* is None or *quality_score* is not a finite float in [0.0, 1.0].
    AttributeError
        When *feature* lacks required Feature model attributes.
    """
    if feature is None:
        raise ValueError(
            "feature must not be None; provide a Feature model instance."
        )
    if not isinstance(quality_score, (int, float)) or not (0.0 <= quality_score <= 1.0):
        raise ValueError(
            f"quality_score must be a float in [0.0, 1.0]; got {quality_score!r}."
        )
    if bypass_quality_threshold(feature):
        return True
    return float(quality_score) >= float(threshold)
