"""Forward-carry auditor — canonical F-R7-NNN regex matching.

Addresses the silent-drop defect from F-R7-554: exact-string matching on
feature IDs breaks when sidecars are renamed or features are referenced by
shortname only. This module audits by scanning all textual fields with the
canonical F-R7-NNN regex, so a required feature is detected regardless of
what the 'id' field holds.

Exports audit_forward_carry_by_canonical_id as the primary public entry point.
"""

from __future__ import annotations

from typing import Any

from bob.auditor.carry_forward_matcher import match_by_canonical_id, resolve_feature_reference
from bob72.auditor import (
    evaluate_canonical_carry,
    extract_canonical_ids,
    required_feature_ids,
)

__all__ = [
    "audit_forward_carry_by_canonical_id",
    "evaluate_canonical_carry",
    "extract_canonical_ids",
    "match_by_canonical_id",
    "required_feature_ids",
    "resolve_feature_reference",
]


def audit_forward_carry_by_canonical_id(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
    raise_on_missing: bool = False,
) -> frozenset[str]:
    """Return the set of required canonical IDs missing from spec.

    Audits by scanning each feature entry's id, title, and description fields
    with the canonical F-R7-NNN regex rather than doing an exact-string id
    comparison. This correctly handles sidecar renames and shortname aliases
    that would otherwise silently drop carry-forward features.

    Args:
        spec: Parsed spec dict (e.g. from yaml.safe_load). An empty dict or a
            spec without a 'features' key is treated as all-features-missing.
        required: Optional override for the required ID set. Defaults to
            required_feature_ids() (base set + BOB_PERMANENT_CARRY_IDS env).
        raise_on_missing: If True, raises ValueError listing the missing IDs
            when any required feature is absent. Defaults to False.

    Returns:
        Frozenset of required F-R7-NNN IDs not found in the spec. An empty
        frozenset means all required features are present.

    Raises:
        ValueError: If spec is not a dict, or if raise_on_missing is True and
            any required feature ID is absent.
    """
    if not isinstance(spec, dict):
        raise ValueError(
            f"spec must be a dict, got {type(spec).__name__!r}"
        )

    missing = evaluate_canonical_carry(spec, required=required)

    if raise_on_missing and missing:
        sorted_missing = sorted(missing)
        raise ValueError(
            f"Carry-forward audit failed: required feature IDs not found in spec "
            f"via canonical regex scan: {sorted_missing}"
        )

    return missing
