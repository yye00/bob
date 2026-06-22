"""Bootstrap auditor — permanent-forward-carry check for bob_N bootstrap.

Provides the ``audit_permanent_forward_carry`` entrypoint that MUST be called
after sidecar merge and BEFORE plan --create. If any of the permanent
infra-recovery feature IDs (F-R7-478, F-R7-479, F-R7-553) are absent from
the merged spec, this module raises ``PermanentForwardCarryMissing`` and
refuses to continue — preserving infra-recovery capability across the chain.

This module is a thin coordination layer that delegates to:
    bob3.bootstrap.permanent_forward_carry_auditor

The re-export at the public ``bob3.bootstrap_auditor`` path satisfies the
acceptance criterion:
    File exists: src/bob3/bootstrap_auditor.py
    Function defined: bob3.bootstrap_auditor.audit_permanent_forward_carry
    Function defined: bob3.bootstrap_auditor.PermanentForwardCarryMissing
"""

from __future__ import annotations

from typing import Any

from bob3.bootstrap.permanent_forward_carry_auditor import (  # noqa: F401
    BootstrapAuditError,
    PermanentForwardCarryMissing,
    _CANONICAL_REQUIRED_IDS,
    _STAGED_SPECS_HINT,
    audit_bootstrap_spec,
    audit_merged_spec,
    fail_loud_on_missing,
    required_feature_ids,
)


def audit_permanent_forward_carry(spec: dict[str, Any]) -> None:
    """Audit a merged spec and fail loud if permanent-forward-carry features are missing.

    Single-call entrypoint for the bootstrap auditor at the ``bob3.bootstrap_auditor``
    import path. Checks that the merged spec contains feature definitions for
    F-R7-478, F-R7-479, and F-R7-553. If any are absent, raises
    ``PermanentForwardCarryMissing`` with a structured event listing the absent
    features and a pointer to bob4/research/staged_specs/.

    MUST be called AFTER sidecar merge and BEFORE plan --create / feature
    insertion. On success (all required features present), returns None.

    Args:
        spec: A parsed spec dict (e.g. from yaml.safe_load).

    Raises:
        PermanentForwardCarryMissing: when any required feature definition is
            absent from the merged spec.
    """
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
    "fail_loud_on_missing",
    "required_feature_ids",
]
