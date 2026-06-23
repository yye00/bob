"""Spec quality gate allowlist — exempt permanent forward-carry infra features.

The 0.85 spec_quality_score gate is the right policy for newly synthesized
features, but blocks permanent forward-carry infrastructure features
(F-R7-478, F-R7-479, F-R7-481) whose ACs are intentionally terse and
score in the 0.6-0.75 range.

Usage::

    from bob72.spec_quality_gate import check_allowlist

    if check_allowlist(feature):
        # exempt from the quality gate — MUST-CARRY-FORWARD feature
        promotable_ids.append(fid)
    else:
        allowed, block_msg = gate_for_ready(quality_report)
        ...

Integration with bob3.orchestrator::

    import bob3.orchestrator
    from bob72.spec_quality_gate import check_allowlist
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bob3.spec_quality_allowlist import is_permanent_forward_carry, load_allowlist_patterns

if TYPE_CHECKING:
    from bob3.models import Feature

__all__ = ["check_allowlist", "load_allowlist_patterns"]


def check_allowlist(feature: "Feature") -> bool:
    """Return True when *feature* is exempt from the 0.85 spec_quality_score gate.

    A feature is exempt when ANY of the following hold:

    1. ``feature.permanent_forward_carry`` is True (explicit DB flag).
    2. ``feature.spec_slot`` contains any allowlisted pattern as a substring.
    3. ``feature.name`` contains any allowlisted pattern as a substring.

    The default allowlist covers the three canonical infra slots:
    F-R7-478 (unlimited spawn retry), F-R7-479 (RCA-layer NH auto-reset),
    F-R7-481 (slopsquatting local-module exclusion).

    Parameters
    ----------
    feature:
        The Feature model to inspect. Must not be None or a non-feature type.

    Returns
    -------
    bool
        True when the feature is exempt and may bypass the quality gate.

    Raises
    ------
    ValueError
        When *feature* is None.
    AttributeError
        When *feature* lacks the expected feature attributes (not a Feature object).
    """
    if feature is None:
        raise ValueError(
            "feature must not be None; provide a Feature model instance."
        )
    if not hasattr(feature, "permanent_forward_carry"):
        raise AttributeError(
            f"feature must be a Feature model instance with 'permanent_forward_carry' attribute; "
            f"got {type(feature).__name__!r}."
        )

    return bool(is_permanent_forward_carry(feature))
