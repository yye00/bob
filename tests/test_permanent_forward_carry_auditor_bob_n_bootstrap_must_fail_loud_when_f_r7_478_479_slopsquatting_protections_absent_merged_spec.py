"""Tests for the permanent-forward-carry bootstrap auditor (long-name AC module).

Verifies the primary entrypoint function:
  permanent_forward_carry_auditor_bob_n_bootstrap_must_fail_loud_when_
  f_r7_478_479_slopsquatting_protections_absent_merged_spec()

Covers the key AC behaviours:
- Passes silently when F-R7-478, F-R7-479, and F-R7-553 are all present
- Raises BootstrapAuditError with permanent_forward_carry_missing event when
  any of the three required IDs is absent
- Error message lists the missing ID(s) and points to staged_specs/
- The .missing attribute on the exception holds the frozenset of absent IDs
"""

from __future__ import annotations

import pytest

from bob3.permanent_forward_carry_auditor_bob_n_bootstrap_must_fail_loud_when_f_r7_478_479_slopsquatting_protections_absent_merged_spec import (
    BootstrapAuditError,
    permanent_forward_carry_auditor_bob_n_bootstrap_must_fail_loud_when_f_r7_478_479_slopsquatting_protections_absent_merged_spec as auditor_fn,
)


def _spec(*ids: str) -> dict:
    return {
        "features": [
            {"id": fid, "title": f"Feature {fid}", "description": "test"}
            for fid in ids
        ]
    }


def test_permanent_forward_carry_auditor_bob_n_bootstrap_must_fail_loud_when_f_r7_478_479_slopsquatting_protections_absent_merged_spec():
    """Primary AC test: function exists, passes on full spec, raises on missing."""
    # Passes silently when all three required features are present
    auditor_fn(_spec("F-R7-478", "F-R7-479", "F-R7-553"))

    # Raises when F-R7-478 is absent
    with pytest.raises(BootstrapAuditError) as exc_info:
        auditor_fn(_spec("F-R7-479", "F-R7-553"))
    err = str(exc_info.value)
    assert "F-R7-478" in err
    assert "permanent_forward_carry_missing" in err
    assert "bob4/research/staged_specs/" in err
    assert exc_info.value.missing == frozenset({"F-R7-478"})

    # Raises when F-R7-479 is absent
    with pytest.raises(BootstrapAuditError) as exc_info:
        auditor_fn(_spec("F-R7-478", "F-R7-553"))
    assert "F-R7-479" in str(exc_info.value)

    # Raises when F-R7-553 (slopsquatting wall) is absent
    with pytest.raises(BootstrapAuditError) as exc_info:
        auditor_fn(_spec("F-R7-478", "F-R7-479"))
    assert "F-R7-553" in str(exc_info.value)

    # Raises with all three missing on empty spec
    with pytest.raises(BootstrapAuditError) as exc_info:
        auditor_fn({})
    missing = exc_info.value.missing
    assert "F-R7-478" in missing
    assert "F-R7-479" in missing
    assert "F-R7-553" in missing
