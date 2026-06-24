"""Tests for the short-name alias module permanent_forward_carry_auditor_must_match_f_r7_nnn.

AC: pytest: tests/test_permanent_forward_carry_auditor_must_match_f_r7_nnn.py::test_permanent_forward_carry_auditor_must_match_f_r7_nnn
"""

from __future__ import annotations

import pytest

import bob3.permanent_forward_carry_auditor_must_match_f_r7_nnn as auditor_module
from bob3.permanent_forward_carry_auditor_must_match_f_r7_nnn import (
    BootstrapAuditError,
    _CANONICAL_REQUIRED_IDS,
    extract_canonical_ids,
    permanent_forward_carry_auditor_must_match_f_r7_nnn as audit_fn,
    required_feature_ids,
)


def _spec(*ids: str) -> dict:
    return {
        "features": [
            {"id": fid, "title": f"Feature {fid}", "description": "test"}
            for fid in ids
        ]
    }


def _spec_renamed(canonical_id: str, sidecar_name: str) -> dict:
    return {
        "features": [
            {
                "id": sidecar_name,
                "title": f"{canonical_id} Permanent carry feature",
                "description": f"Implements {canonical_id}",
            }
        ]
    }


def test_permanent_forward_carry_auditor_must_match_f_r7_nnn():
    """AC entry-point: verifies all core behaviours of the short-name alias module.

    Covers:
      1. Module exports the function under the required name.
      2. All-present spec returns empty frozenset (no missing IDs).
      3. Missing required ID raises BootstrapAuditError.
      4. Renamed sidecar (canonical ID in title) is detected — regex not exact-string.
      5. Shortname-only (no canonical token anywhere) is correctly flagged missing.
      6. extract_canonical_ids finds tokens in any text field.
      7. required_feature_ids returns the base permanent set.
    """
    # 1. Function is exported with the required name
    assert hasattr(auditor_module, "permanent_forward_carry_auditor_must_match_f_r7_nnn")
    assert callable(audit_fn)

    # 2. Spec with all required IDs present — no missing, returns empty frozenset
    all_ids = list(required_feature_ids())
    full_spec = _spec(*all_ids)
    result = audit_fn(full_spec, required=required_feature_ids())
    assert result == frozenset(), f"Expected empty frozenset, got {result}"

    # 3. Empty spec raises BootstrapAuditError for all required IDs
    with pytest.raises(BootstrapAuditError) as exc_info:
        audit_fn({}, required=frozenset({"F-R7-478"}))
    assert "F-R7-478" in str(exc_info.value)

    # 4. Renamed sidecar: canonical ID in title, not in 'id' field — must be detected
    renamed_spec = _spec_renamed("F-R7-478", "bob27-unlimited-spawn-retry")
    ids_found = extract_canonical_ids(renamed_spec)
    assert "F-R7-478" in ids_found, "Regex scan should find canonical ID in title"

    # Audit with just F-R7-478 required — renamed sidecar should satisfy it
    result2 = audit_fn(renamed_spec, required=frozenset({"F-R7-478"}))
    assert result2 == frozenset()

    # 5. Shortname-only — no canonical token anywhere — must be flagged missing
    shortname_spec = {
        "features": [
            {"id": "unlimited-spawn-retry", "title": "Spawn retry", "description": "retry"}
        ]
    }
    with pytest.raises(BootstrapAuditError):
        audit_fn(shortname_spec, required=frozenset({"F-R7-478"}))

    # 6. extract_canonical_ids finds tokens in description too
    desc_spec = {
        "features": [
            {"id": "some-alias", "title": "Some feature", "description": "See F-R7-479 for details"}
        ]
    }
    assert "F-R7-479" in extract_canonical_ids(desc_spec)

    # 7. required_feature_ids contains the base permanent set
    base = required_feature_ids()
    assert "F-R7-478" in base
    assert "F-R7-479" in base
    assert "F-R7-553" in base
    assert isinstance(base, frozenset)
