"""Permanent-carry allowlist for the spec quality score gate.

Exposes ``is_exempt_from_threshold`` as the canonical entry point for
callers that need to decide whether a feature bypasses the 0.85
spec_quality_score gate.  Delegates to the existing allowlist logic in
``spec_quality_gate.allowlist``.

Usage::

    from spec_quality_gate.permanent_carry_allowlist import is_exempt_from_threshold

    if is_exempt_from_threshold(feature_id=fid, feature_name=name, spec_slot=slot):
        promotable_ids.append(fid)
    else:
        allowed, block_msg = gate_for_ready(quality_report)
"""

from __future__ import annotations

from typing import Any

from spec_quality_gate.allowlist import is_feature_allowlisted


def is_exempt_from_threshold(
    feature: Any = None,
    *,
    feature_id: str | None = None,
    feature_name: str | None = None,
    spec_slot: str | None = None,
    permanent_forward_carry: bool = False,
) -> bool:
    """Return True when a feature is exempt from the spec_quality_score gate.

    Thin wrapper around :func:`spec_quality_gate.allowlist.is_feature_allowlisted`
    that uses the canonical name expected by the AC.

    A feature is exempt when ANY of the following hold:

    1. ``permanent_forward_carry`` is True (explicit DB flag or kwarg).
    2. ``spec_slot`` contains any allowlisted pattern as a substring.
    3. ``feature_name`` contains any allowlisted pattern as a substring.

    The default allowlist covers three canonical infra slots:
    F-R7-478 (unlimited spawn retry), F-R7-479 (RCA-layer NH auto-reset),
    F-R7-481 (slopsquatting local-module exclusion). Extend via the
    ``BOB_ALLOWLIST_PATTERNS`` env var (comma-separated additional patterns).

    Parameters
    ----------
    feature:
        Optional feature object with ``permanent_forward_carry``, ``spec_slot``,
        and ``name`` attributes. Must not be a primitive type.
    feature_id:
        Optional feature UUID string (reserved for future UUID-based exemptions).
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
        When *feature* is a primitive type (int, str, dict, etc.) rather than a
        Feature model instance.
    """
    return is_feature_allowlisted(
        feature,
        feature_id=feature_id,
        feature_name=feature_name,
        spec_slot=spec_slot,
        permanent_forward_carry=permanent_forward_carry,
    )
