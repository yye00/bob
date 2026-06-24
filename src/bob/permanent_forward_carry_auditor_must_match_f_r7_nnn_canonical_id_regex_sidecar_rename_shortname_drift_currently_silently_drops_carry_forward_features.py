"""Permanent-forward-carry auditor MUST match by F-R7-NNN canonical ID regex.

Problem: F-R7-554 (bob26 sidecar) defines required_feature_ids as a frozen
set of literal strings. When a sidecar is renamed (bob26 → bob27 shuffle) or a
feature is referenced by shortname only, the auditor's exact-string id check
fails to detect the still-present feature. This produces false-positive missing
reports OR false-negative silent drops depending on the rename direction.

Fix: audit by scanning all textual fields (id, title, description) with the
canonical F-R7-NNN regex, not by exact id-string comparison. A required feature
counts as present if its canonical ID token appears anywhere in the feature
entry — regardless of what the 'id' field is named.

This module provides the AC-required function and re-exports the underlying
building blocks so callers can compose audits without importing the bootstrap
sub-package directly.
"""

from __future__ import annotations

import re
from typing import Any

from bob.bootstrap.permanent_forward_carry_auditor import (  # noqa: F401
    BootstrapAuditError,
    PermanentForwardCarryMissing,
    _CANONICAL_REQUIRED_IDS,
    _COMPILED_CANONICAL_PATTERN,
    _STAGED_SPECS_HINT,
    audit_bootstrap_spec,
    audit_merged_spec,
    canonical_feature_id_pattern,
    extract_canonical_ids,
    fail_loud_on_missing,
    required_feature_ids,
)

__all__ = [
    "BootstrapAuditError",
    "PermanentForwardCarryMissing",
    "_CANONICAL_REQUIRED_IDS",
    "_COMPILED_CANONICAL_PATTERN",
    "_STAGED_SPECS_HINT",
    "audit_bootstrap_spec",
    "audit_merged_spec",
    "canonical_feature_id_pattern",
    "extract_canonical_ids",
    "fail_loud_on_missing",
    "permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features",
    "required_feature_ids",
]


def permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
) -> frozenset[str]:
    """Audit a merged spec using canonical F-R7-NNN regex matching.

    Unlike an exact-string id check, this auditor scans each feature entry's
    id, title, and description fields for the F-R7-NNN pattern. A required
    feature ID is considered present if its token appears anywhere in that
    feature entry, even when the sidecar has been renamed or the feature is
    referenced by a shortname alias.

    The function returns the set of required IDs that could NOT be found in
    the spec via regex scan. An empty frozenset means all required features
    are present. Raises BootstrapAuditError if any required IDs are missing.

    Args:
        spec: A parsed spec dict (e.g. from yaml.safe_load on the merged spec
            YAML). Supports both list-of-dicts and dict-of-dicts features
            formats. An empty dict or a spec with no 'features' key is treated
            as all features missing.
        required: Optional override for the required ID set. Defaults to
            required_feature_ids() which reads the base set plus any IDs
            from the BOB_PERMANENT_CARRY_IDS env var.

    Returns:
        Frozenset of required feature IDs that are absent from the spec.
        An empty frozenset indicates the spec is compliant.

    Raises:
        BootstrapAuditError: when any required feature ID is absent from the
            merged spec after regex-based scanning. The exception carries a
            structured ``permanent_forward_carry_missing`` event message and
            lists the missing IDs.
    """
    required_ids = required if required is not None else required_feature_ids()
    found_ids = extract_canonical_ids(spec)
    missing = required_ids - found_ids
    if missing:
        fail_loud_on_missing(frozenset(missing))
    return frozenset(missing)
