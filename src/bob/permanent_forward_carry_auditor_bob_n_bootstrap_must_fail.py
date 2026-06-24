"""Permanent-forward-carry auditor — bob_N bootstrap MUST fail when
F-R7-478/479 + slopsquatting protections absent from merged spec.

This module provides the primary entrypoint function named identically to the
module, satisfying the AC:

  Function defined:
    bob.permanent_forward_carry_auditor_bob_n_bootstrap_must_fail.\
permanent_forward_carry_auditor_bob_n_bootstrap_must_fail

Background: audit 2026-05-28 found F-R7-478 missing from bob17/18/19/24
sidecars, F-R7-479 missing from bob17-25 sidecars, and F-R7-553 (slopsquatting
wall) never instantiated as a full feature definition in any sidecar. The
sidecar-merge process silently drops permanent infra-recovery features when they
are not explicitly re-added, causing capabilities to degrade as the chain
advances.

Fix: this auditor MUST run after sidecar merge and BEFORE plan --create. It
checks the merged spec for the permanent-forward-carry set {F-R7-478, F-R7-479,
F-R7-553}. If any are missing, it raises BootstrapAuditError with a structured
``permanent_forward_carry_missing`` event and refuses to start the run.
"""

from __future__ import annotations

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
    "permanent_forward_carry_auditor_bob_n_bootstrap_must_fail",
    "required_feature_ids",
]


def permanent_forward_carry_auditor_bob_n_bootstrap_must_fail(
    spec: dict[str, Any],
) -> None:
    """Audit a merged spec and fail loud if permanent-forward-carry features are missing.

    Checks the merged spec for the mandatory permanent-forward-carry feature
    set: F-R7-478 (unlimited spawn retry), F-R7-479 (RCA-layer NH auto-reset),
    and F-R7-553 (slopsquatting whitelist / wall). If any of these are absent,
    raises BootstrapAuditError with a structured
    ``permanent_forward_carry_missing`` event, listing the absent feature IDs
    and pointing to bob4/research/staged_specs/ as the correction location.

    This function MUST be called after sidecar merge and BEFORE plan --create
    or any feature insertion, so that infra-recovery capabilities are preserved
    across the chain. Silence from this auditor means all three protections are
    present; an exception means the bootstrap MUST NOT proceed.

    Args:
        spec: A parsed spec dict (e.g. from yaml.safe_load on the merged spec
            YAML). Supports both list-of-dicts and dict-of-dicts features
            formats. An empty dict or a dict with no 'features' key is treated
            as all features missing.

    Raises:
        BootstrapAuditError: when any required feature definition is absent
            from the merged spec. The exception message includes:
            - the literal event token ``permanent_forward_carry_missing``
            - a sorted list of the absent feature IDs
            - a pointer to ``bob4/research/staged_specs/``
            The ``.missing`` attribute holds the frozenset of absent IDs.
    """
    audit_bootstrap_spec(spec)
