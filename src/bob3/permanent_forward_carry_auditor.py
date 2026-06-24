"""Permanent-forward-carry auditor — public module for bob3.permanent_forward_carry_auditor.

Re-exports the canonical implementation from bob3.bootstrap.permanent_forward_carry_auditor
so that `from bob3.permanent_forward_carry_auditor import audit_merged_spec` works as
specified by the acceptance criterion.

The actual implementation lives in bob3.bootstrap.permanent_forward_carry_auditor.
Both import paths resolve to the same objects.

Also exports match_by_canonical_id and resolve_shortname_to_canonical from
bob3.auditor.carry_forward_matcher to fix the silent-drop defect (F-R7-554):
when a sidecar is renamed or a feature is referenced by shortname only, the
regex-based matcher detects the still-present feature regardless of the 'id'
field value.

audit_canonical_feature_ids is the AC-required entry point that wraps
extract_canonical_ids with a required-set check and raises BootstrapAuditError
on any missing IDs. It uses regex scanning (not exact-string id comparison)
so sidecar renames and shortname drift are correctly detected.
"""

from __future__ import annotations

from typing import Any

from bob3.auditor.carry_forward_matcher import (  # noqa: F401
    match_by_canonical_id,
    resolve_feature_reference,
    resolve_feature_reference as resolve_shortname_to_canonical,
)
from bob3.bootstrap.permanent_forward_carry_auditor import (  # noqa: F401
    BootstrapAuditError,
    PermanentForwardCarryMissing,
    _CANONICAL_REQUIRED_IDS,
    _COMPILED_CANONICAL_PATTERN,
    _STAGED_SPECS_HINT,
    audit_bootstrap_spec,
    audit_bootstrap_spec as audit_permanent_forward_carry,
    audit_merged_spec,
    canonical_feature_id_pattern,
    check_required_features,
    extract_canonical_ids,
    fail_loud_on_missing,
    required_feature_ids,
)

# AC-required alias: emit_permanent_forward_carry_missing is the public event-emission
# entry point. Delegates to fail_loud_on_missing which raises BootstrapAuditError with
# the structured permanent_forward_carry_missing event when missing set is non-empty.
emit_permanent_forward_carry_missing = fail_loud_on_missing

__all__ = [
    "BootstrapAuditError",
    "PermanentForwardCarryMissing",
    "_CANONICAL_REQUIRED_IDS",
    "_COMPILED_CANONICAL_PATTERN",
    "_STAGED_SPECS_HINT",
    "audit_bootstrap_spec",
    "audit_by_canonical_id",
    "audit_canonical_feature_ids",
    "audit_carry_forward_features",
    "audit_merged_spec",
    "audit_permanent_forward_carry",
    "audit_required_features",
    "canonical_feature_id_pattern",
    "emit_permanent_forward_carry_missing",
    "extract_canonical_ids",
    "fail_loud_on_missing",
    "match_by_canonical_id",
    "match_feature_by_canonical_id",
    "normalize_feature_id",
    "required_feature_ids",
    "resolve_feature_reference",
    "resolve_shortname_to_canonical",
    "validate_permanent_features",
]


def audit_canonical_feature_ids(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
) -> frozenset[str]:
    """Audit a merged spec using canonical F-R7-NNN regex matching.

    Unlike exact-string id comparison, this function scans each feature
    entry's id, title, and description fields for the F-R7-NNN token.
    A required feature ID is considered present if its canonical token
    appears anywhere in any field of the feature entry — regardless of
    whether the 'id' field uses a sidecar alias or shortname.

    This fixes the silent-drop defect from F-R7-554: when a sidecar is
    renamed (bob26 → bob27 shuffle) or referenced by shortname only, the
    regex scan still detects the still-present feature.

    Args:
        spec: Parsed spec dict (yaml.safe_load output or equivalent).
            Supports both list-of-dicts and dict-of-dicts features formats.
            An empty dict or a spec with no 'features' key is treated as
            all features missing.
        required: Optional override for the required ID set. Defaults to
            required_feature_ids() (base set + BOB3_PERMANENT_CARRY_IDS env).

    Returns:
        Frozenset of required IDs absent from the spec. An empty frozenset
        means all required features are present.

    Raises:
        BootstrapAuditError: When any required canonical feature ID is absent
            from the merged spec after regex-based scanning. The error message
            contains the 'permanent_forward_carry_missing' event token and
            lists the missing IDs.
    """
    required_ids = required if required is not None else required_feature_ids()
    found_ids = extract_canonical_ids(spec)
    missing = frozenset(required_ids - found_ids)
    if missing:
        fail_loud_on_missing(missing)
    return missing


def audit_by_canonical_id(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
) -> frozenset[str]:
    """Audit a merged spec by matching required features using the F-R7-NNN canonical ID regex.

    This is the primary AC-required entry point for the canonical-ID-regex auditing
    strategy. Unlike exact-string 'id' field comparison, this function scans each
    feature entry's id, title, and description fields for the F-R7-NNN token using
    match_by_canonical_id. A required feature is considered present if its canonical
    token appears anywhere in any field of any feature entry — regardless of whether
    the 'id' field holds a sidecar alias or shortname.

    This fixes the silent-drop defect from F-R7-554: when a sidecar is renamed
    (e.g. bob26 → bob27 shuffle) or referenced by shortname only, the old
    exact-string id check silently drops the carry-forward feature. The regex scan
    correctly detects the still-present feature regardless of rename direction.

    Args:
        spec: Parsed spec dict (yaml.safe_load output or equivalent).
            Supports both list-of-dicts and dict-of-dicts features formats.
            An empty dict or a spec with no 'features' key is treated as
            all features missing.
        required: Optional override for the required ID set. Defaults to
            required_feature_ids() (base set + BOB3_PERMANENT_CARRY_IDS env).

    Returns:
        Frozenset of required IDs absent from the spec after regex scanning.
        An empty frozenset means all required features are present.

    Raises:
        BootstrapAuditError: When any required canonical feature ID is absent
            from the merged spec after regex-based scanning. The error message
            contains the 'permanent_forward_carry_missing' event token and
            lists the missing IDs.
    """
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be a dict, got {type(spec).__name__!r}")

    required_ids = required if required is not None else required_feature_ids()
    features = spec.get("features") or []

    present: set[str] = set()
    if isinstance(features, dict):
        feature_list = list(features.values())
    elif isinstance(features, list):
        feature_list = features
    else:
        feature_list = []

    for feature_entry in feature_list:
        if not isinstance(feature_entry, dict):
            continue
        for req_id in required_ids:
            if req_id not in present and match_by_canonical_id(feature_entry, req_id):
                present.add(req_id)

    missing = frozenset(required_ids - present)
    if missing:
        fail_loud_on_missing(missing)
    return missing


def normalize_feature_id(feature_id: str) -> str:
    """Normalize a feature reference to its canonical F-R7-NNN form.

    Extracts the first canonical F-R7-NNN token from a reference string that
    may be a shortname, sidecar alias, or an ID embedding the canonical token.
    If no canonical token is found, returns the original reference stripped of
    whitespace.

    This is the AC-required public entry point that delegates to
    resolve_shortname_to_canonical (resolve_feature_reference from
    bob3.auditor.carry_forward_matcher).

    Args:
        feature_id: A string that may contain a canonical feature ID token,
            e.g. "my-sidecar (F-R7-478)", "F-R7-478", or a bare shortname.
            Must be a non-empty string.

    Returns:
        The first F-R7-NNN token found in the reference, or the stripped
        reference if no canonical token is present.

    Raises:
        ValueError: If feature_id is not a non-empty string.
    """
    return resolve_shortname_to_canonical(feature_id)


def audit_carry_forward_features(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
) -> frozenset[str]:
    """Audit carry-forward features in a merged spec using canonical F-R7-NNN regex matching.

    This is the AC-required public entry point for carry-forward feature auditing.
    Unlike exact-string id comparison, this function scans each feature entry's id,
    title, and description fields for the F-R7-NNN token. A required feature ID is
    considered present if its canonical token appears anywhere in any field — regardless
    of whether the 'id' field uses a sidecar alias or shortname.

    This fixes the silent-drop defect from F-R7-554: when a sidecar is renamed or
    referenced by shortname only, the regex scan still detects the still-present feature.

    Args:
        spec: Parsed spec dict. Supports both list-of-dicts and dict-of-dicts formats.
            An empty dict or a spec with no 'features' key is treated as all missing.
        required: Optional override for the required ID set. Defaults to
            required_feature_ids() (base set + BOB3_PERMANENT_CARRY_IDS env).

    Returns:
        Frozenset of required IDs absent from the spec. An empty frozenset means
        all required features are present.

    Raises:
        BootstrapAuditError: When any required canonical feature ID is absent from
            the merged spec after regex-based scanning.
    """
    return audit_canonical_feature_ids(spec, required=required)


def match_feature_by_canonical_id(
    feature_entry: dict[str, Any],
    canonical_id: str,
) -> bool:
    """Return True if canonical_id token appears in any text field of feature_entry.

    AC-required entry point that delegates to match_by_canonical_id from
    bob3.auditor.carry_forward_matcher. Uses regex matching to detect the
    canonical F-R7-NNN token in any of the id, title, or description fields,
    regardless of sidecar rename or shortname drift (fixes F-R7-554 silent drop).

    Args:
        feature_entry: A single feature dict. Must be a mapping; non-mapping raises ValueError.
        canonical_id: The canonical feature ID to search for, e.g. "F-R7-478".
            Must be a non-empty, non-blank string containing at least one letter and digit.

    Returns:
        True if canonical_id token is found in any text field, False otherwise.

    Raises:
        ValueError: If feature_entry is not a dict, or canonical_id is not a valid token.
    """
    return match_by_canonical_id(feature_entry, canonical_id)


def audit_required_features(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
) -> frozenset[str]:
    """Audit a merged spec for required permanent carry-forward features.

    AC-required entry point that returns the set of required canonical IDs
    absent from the spec after regex-based scanning. Unlike exact-string id
    lookup, scans each feature entry's id, title, and description fields for
    F-R7-NNN tokens, so renamed sidecars and shortname drift are correctly
    detected (fixes the F-R7-554 silent-drop defect).

    This function does NOT raise on missing features — it returns the missing
    set as a frozenset for the caller to handle. To raise BootstrapAuditError
    on any missing ID, use audit_canonical_feature_ids instead.

    Args:
        spec: Parsed spec dict. Supports both list-of-dicts and dict-of-dicts formats.
            An empty dict or a spec with no 'features' key returns all required IDs.
        required: Optional override for the required ID set. Defaults to
            required_feature_ids() (base set + BOB3_PERMANENT_CARRY_IDS env).

    Returns:
        Frozenset of required IDs absent from the spec. Empty means all present.

    Raises:
        ValueError: If spec is not a dict.
    """
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be a dict, got {type(spec).__name__!r}")
    required_ids = required if required is not None else required_feature_ids()
    found_ids = extract_canonical_ids(spec)
    return frozenset(required_ids - found_ids)


def validate_permanent_features(
    spec: dict[str, Any],
    *,
    required: frozenset[str] | None = None,
) -> None:
    """Validate that all permanent-forward-carry features are present in the merged spec.

    Primary integration entry point called by the bob_N bootstrap AFTER sidecar
    merge and BEFORE plan --create. Performs canonical F-R7-NNN regex scanning
    across feature id, title, and description fields, then raises BootstrapAuditError
    listing any absent features and refuses to proceed.

    Args:
        spec: Parsed merged spec dict (e.g. from yaml.safe_load).
            Supports both list-of-dicts and dict-of-dicts features formats.
        required: Optional override for the required ID set. Defaults to
            required_feature_ids() (base set + BOB3_PERMANENT_CARRY_IDS env).

    Raises:
        BootstrapAuditError: with a structured permanent_forward_carry_missing
            event when any required feature definition is absent from the spec.
        ValueError: If spec is not a dict.
    """
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be a dict, got {type(spec).__name__!r}")
    audit_canonical_feature_ids(spec, required=required)
