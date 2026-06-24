"""Alias module: short-name import for the canonical-ID-regex carry auditor.

Re-exports the primary function under the abbreviated module path
bob.permanent_forward_carry_auditor_must_match_f_r7_nnn so that callers
referencing the AC-required short path get the same implementation.
"""

from bob.permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features import (  # noqa: F401, E501
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
    permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features,
    required_feature_ids,
)

permanent_forward_carry_auditor_must_match_f_r7_nnn = (
    permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features
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
    "permanent_forward_carry_auditor_must_match_f_r7_nnn",
    "permanent_forward_carry_auditor_must_match_f_r7_nnn_canonical_id_regex_sidecar_rename_shortname_drift_currently_silently_drops_carry_forward_features",
    "required_feature_ids",
]
