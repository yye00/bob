"""Permanent-forward-carry auditor — bob.auditors public entry point.

Provides audit_permanent_forward_carry, the canonical bootstrap auditor
that MUST run after sidecar merge and BEFORE plan --create. If any of the
permanent infra-recovery feature IDs (F-R7-478, F-R7-479, F-R7-553) are
absent from the merged spec, the auditor raises BootstrapAuditError with a
structured permanent_forward_carry_missing event and refuses to proceed.

This module re-exports the implementation from
bob.bootstrap.permanent_forward_carry_auditor so that the AC-required
import path (bob.auditors.permanent_forward_carry) is satisfied without
duplicating logic.
"""

from __future__ import annotations

from typing import Any

from bob.bootstrap.permanent_forward_carry_auditor import (  # noqa: F401
    BootstrapAuditError,
    PermanentForwardCarryMissing,
    _CANONICAL_REQUIRED_IDS,
    _STAGED_SPECS_HINT,
    audit_bootstrap_spec,
    audit_merged_spec,
    canonical_feature_id_pattern,
    check_required_features,
    extract_canonical_ids,
    fail_loud_on_missing,
    required_feature_ids,
)


def audit_permanent_forward_carry(spec: dict[str, Any]) -> None:
    """Audit a merged spec and fail loud if permanent-forward-carry features are missing.

    Primary bootstrap entry point at the bob.auditors.permanent_forward_carry
    import path. Checks that the merged spec contains feature definitions for the
    permanent infra-recovery set (F-R7-478, F-R7-479, F-R7-553). If any are
    absent, raises BootstrapAuditError with a structured
    permanent_forward_carry_missing event listing the absent features and a
    pointer to bob4/research/staged_specs/. Refuses to proceed.

    MUST be called AFTER sidecar merge and BEFORE plan --create / feature
    insertion. On success (all required features present), returns None.

    Args:
        spec: A parsed spec dict (e.g. from yaml.safe_load).

    Raises:
        BootstrapAuditError: with a structured permanent_forward_carry_missing
            event when any required feature definition is absent from the
            merged spec.
        ValueError: If spec is not a dict.
    """
    if not isinstance(spec, dict):
        raise ValueError(f"spec must be a dict, got {type(spec).__name__!r}")
    missing = audit_merged_spec(spec)
    fail_loud_on_missing(missing)


__all__ = [
    "BootstrapAuditError",
    "PermanentForwardCarryMissing",
    "_CANONICAL_REQUIRED_IDS",
    "_STAGED_SPECS_HINT",
    "audit_bootstrap_spec",
    "audit_merged_spec",
    "audit_permanent_forward_carry",
    "canonical_feature_id_pattern",
    "check_required_features",
    "extract_canonical_ids",
    "fail_loud_on_missing",
    "required_feature_ids",
]
