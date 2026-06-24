"""Permanent-forward-carry auditor — bob3.audit_permanent_forward_carry module.

Provides match_by_canonical_id and resolve_feature_reference for canonical
F-R7-NNN ID matching, fixing the silent-drop defect (F-R7-554) where sidecar
renames or shortname drift caused required features to be missed by exact-string
comparison.

This module re-exports the carry_forward_matcher implementation so the
AC-required import path (bob3.audit_permanent_forward_carry) is satisfied.
"""

from __future__ import annotations

from bob3.auditor.carry_forward_matcher import (  # noqa: F401
    match_by_canonical_id,
    resolve_feature_reference,
)

__all__ = [
    "match_by_canonical_id",
    "resolve_feature_reference",
]
