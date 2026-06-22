"""Carry-forward auditor — regex-based canonical ID matching for bob3.

Exposes match_feature_by_canonical_id so the carry-forward auditor matches
feature entries by F-R7-NNN canonical ID regex rather than exact string
comparison. This fixes the silent-drop defect (F-R7-554) where sidecar
renames or shortname drift caused the old exact-string check to miss
still-present features.

The canonical implementation lives in bob72.auditor; this module re-exports
the public API so imports from bob3.carry_forward_auditor work as specified
by the acceptance criteria.
"""

from __future__ import annotations

from typing import Any

from bob72.auditor import (  # noqa: F401
    BootstrapAuditError,
    evaluate_canonical_carry,
    extract_canonical_ids,
    match_by_canonical_id,
    required_feature_ids,
)
from bob3.auditor.carry_forward_matcher import resolve_feature_reference  # noqa: F401

# AC-required alias: match_feature_by_canonical_id is the public name exposed
# by this module; match_by_canonical_id is the implementation name in bob72.
match_feature_by_canonical_id = match_by_canonical_id


def audit_permanent_forward_carry(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
) -> frozenset[str]:
    """Audit a spec for permanent-forward-carry features using canonical ID regex.

    Scans each feature entry's id, title, and description fields for F-R7-NNN
    tokens. A required feature counts as present if its canonical ID token
    appears anywhere in the entry — regardless of sidecar rename or shortname
    drift. Returns the set of required IDs absent from the spec; raises
    BootstrapAuditError if any are missing.

    Args:
        spec: Parsed spec dict (e.g. from yaml.safe_load).
        required: Override the required ID set. Defaults to required_feature_ids().

    Returns:
        Frozenset of required IDs absent from the spec (empty = compliant).

    Raises:
        BootstrapAuditError: when any required feature ID is absent.
        ValueError: when spec is not a dict.
    """
    return evaluate_canonical_carry(spec, required=required or required_feature_ids())


__all__ = [
    "BootstrapAuditError",
    "audit_permanent_forward_carry",
    "evaluate_canonical_carry",
    "extract_canonical_ids",
    "match_by_canonical_id",
    "match_feature_by_canonical_id",
    "required_feature_ids",
    "resolve_feature_reference",
]
