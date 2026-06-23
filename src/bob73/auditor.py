"""Canonical-ID auditor for bob73.

Exposes match_canonical_id — a thin wrapper around bob72.auditor.match_by_canonical_id
that provides the bob73.auditor.match_canonical_id symbol required by the
AC: Function defined: bob73.auditor.match_canonical_id.

Also re-exports the full bob72 auditor surface so callers that want
evaluate_canonical_carry, extract_canonical_ids, or required_feature_ids can
import from either bob72.auditor or bob73.auditor interchangeably.
"""

from __future__ import annotations

from typing import Any

from bob72.auditor import (
    BootstrapAuditError,
    evaluate_canonical_carry,
    extract_canonical_ids,
    match_by_canonical_id,
    required_feature_ids,
)

__all__ = [
    "BootstrapAuditError",
    "evaluate_canonical_carry",
    "extract_canonical_ids",
    "match_canonical_id",
    "match_by_canonical_id",
    "required_feature_ids",
]


def match_canonical_id(
    feature_entry: dict[str, Any],
    canonical_id: str,
) -> bool:
    """Return True if *canonical_id* appears anywhere in *feature_entry*.

    Delegates to bob72.auditor.match_by_canonical_id, using a compiled
    word-boundary regex so that F-R7-47 does not match inside F-R7-478.
    Detects the canonical ID even when the feature's 'id' field holds a
    sidecar alias (e.g. "bob27-feature") or a bare shortname.

    Args:
        feature_entry: A single feature dict with optional id/title/description
            keys. Non-mapping input raises ValueError.
        canonical_id: The canonical feature ID to search for, e.g. "F-R7-478".
            Must contain at least one letter and one digit; raises ValueError
            otherwise.

    Returns:
        True if canonical_id is found in any text field of feature_entry,
        False otherwise.

    Raises:
        ValueError: If feature_entry is not a dict, or canonical_id is empty,
            blank, or does not contain at least one letter and one digit.
    """
    return match_by_canonical_id(feature_entry, canonical_id)
