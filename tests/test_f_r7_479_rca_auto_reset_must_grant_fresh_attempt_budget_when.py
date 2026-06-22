"""Tests for F-R7-479: RCA auto-reset MUST grant fresh attempt when verification failure is code-fixable.

Verifies the primary function exported from the feature module and the core logic:
- code_emission_defect with refinement_attempts < 5 grants fresh attempt
- code_emission_defect at attempt cap (>= 5) does NOT grant
- spec_ambiguity does NOT grant
- infra_transient always grants
"""

from __future__ import annotations

import pytest

from bob3.f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when import (
    f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when,
)


def _make_db():
    calls: list[dict] = []

    def db_update_fn(feature_id: str, **kwargs):
        calls.append({"feature_id": feature_id, **kwargs})

    return calls, db_update_fn


def test_f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when():
    """Core: code_emission_defect with attempts < 5 grants fresh attempt and resets to ready."""
    calls, db_update_fn = _make_db()
    result = f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="test-feature-id",
        db_update_fn=db_update_fn,
        failed_acs=["pytest: tests/test_foo.py::test_something"],
        refinement_attempts=2,
    )
    assert result is True
    assert len(calls) == 1
    assert calls[0]["feature_id"] == "test-feature-id"
    assert calls[0]["status"] == "ready"


def test_f_r7_479_grants_for_behavior_ac():
    """behavior: AC prefix is treated as code_emission_defect."""
    calls, db_update_fn = _make_db()
    result = f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="feat-abc",
        db_update_fn=db_update_fn,
        failed_acs=["behavior: foo returns bar given baz"],
        refinement_attempts=0,
    )
    assert result is True
    assert calls[0]["status"] == "ready"


def test_f_r7_479_grants_for_integration_ac():
    """integration: AC prefix is treated as code_emission_defect."""
    calls, db_update_fn = _make_db()
    result = f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="feat-xyz",
        db_update_fn=db_update_fn,
        failed_acs=["integration: module.fn works end-to-end"],
        refinement_attempts=3,
    )
    assert result is True


def test_f_r7_479_does_not_grant_when_cap_reached():
    """code_emission_defect at 5 attempts does NOT grant."""
    calls, db_update_fn = _make_db()
    result = f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="feat-cap",
        db_update_fn=db_update_fn,
        failed_acs=["pytest: tests/test_foo.py"],
        refinement_attempts=5,
    )
    assert result is False
    assert len(calls) == 0


def test_f_r7_479_spec_ambiguity_does_not_grant():
    """spec_ambiguity failure is terminal — no fresh attempt granted."""
    calls, db_update_fn = _make_db()
    result = f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="feat-spec",
        db_update_fn=db_update_fn,
        failed_acs=["references undefined symbol XYZ"],
        refinement_attempts=1,
    )
    assert result is False
    assert len(calls) == 0


def test_f_r7_479_infra_transient_returns_false_defers_to_infra_path():
    """infra_transient: this function returns False, deferring to infra recovery path."""
    calls, db_update_fn = _make_db()
    result = f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="feat-infra",
        db_update_fn=db_update_fn,
        failed_acs=["OSError: [Errno 111] Connection refused"],
        refinement_attempts=0,
    )
    assert result is False
    assert len(calls) == 0


def test_f_r7_479_preserves_attempt_count_in_db_call():
    """DB update sets status=ready but does NOT reset refinement_attempts."""
    calls, db_update_fn = _make_db()
    f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="feat-budget",
        db_update_fn=db_update_fn,
        failed_acs=["pytest: tests/test_something.py::test_fn"],
        refinement_attempts=4,
    )
    assert calls[0]["status"] == "ready"
    # refinement_attempts must NOT be reset (budget accounting)
    assert "refinement_attempts" not in calls[0]
