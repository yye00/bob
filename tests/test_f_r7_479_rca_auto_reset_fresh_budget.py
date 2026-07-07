"""F-R7-479: RCA auto-reset grants fresh attempt budget for code-fixable failures.

Core behavior tests for the facade module
``bob.f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when``:

- ``classify_verification_gate_cause`` — maps failed ACs to a cause.
- ``should_reset_attempt_budget`` — decides whether to grant a fresh attempt.
- ``f_r7_479_...`` entry point — resets the feature to ``ready`` on a code defect
  and leaves NH standing on spec_ambiguity / infra / cap-reached.

Regression driver: feature dd11d1f8 NH'd at refinement_attempts=3 with two
unused budget attempts because the verification-gate failure was classified as
terminal even though it was a plausibly-fixable code emission defect.
"""

from __future__ import annotations

import pytest

from bob.f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when import (
    classify_verification_gate_cause,
    f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when,
    should_reset_attempt_budget,
)


class _RecordingDB:
    """Minimal db_update_fn stand-in that records update calls."""

    def __init__(self):
        self.calls = []

    def __call__(self, feature_id, **kwargs):
        self.calls.append((feature_id, kwargs))


# ---------------------------------------------------------------------------
# classify_verification_gate_cause
# ---------------------------------------------------------------------------


def test_classify_behavior_ac_is_code_emission_defect():
    assert (
        classify_verification_gate_cause(["behavior: fn returns X"])
        == "code_emission_defect"
    )


def test_classify_integration_ac_is_code_emission_defect():
    assert (
        classify_verification_gate_cause(["integration: bob.mod importable"])
        == "code_emission_defect"
    )


def test_classify_pytest_ac_is_code_emission_defect():
    assert (
        classify_verification_gate_cause(["pytest: tests/test_x.py"])
        == "code_emission_defect"
    )


def test_classify_infra_error_is_infra_transient():
    assert (
        classify_verification_gate_cause(["ConnectionResetError: ECONNRESET"])
        == "infra_transient"
    )


def test_classify_unmatched_ac_is_spec_ambiguity():
    assert (
        classify_verification_gate_cause(["something with no known prefix"])
        == "spec_ambiguity"
    )


def test_classify_infra_takes_precedence_over_code():
    # An infra pattern anywhere wins over a code-fixable prefix.
    result = classify_verification_gate_cause(
        ["behavior: fn returns X", "OSError: disk full"]
    )
    assert result == "infra_transient"


# ---------------------------------------------------------------------------
# should_reset_attempt_budget
# ---------------------------------------------------------------------------


def test_reset_granted_for_code_defect_below_cap():
    # The core regression: dd11d1f8 NH'd at attempt 3 — must grant here.
    assert should_reset_attempt_budget(["behavior: fn returns X"], 3) is True


def test_reset_granted_for_code_defect_at_zero():
    assert should_reset_attempt_budget(["pytest: tests/test_x.py"], 0) is True


def test_reset_denied_for_code_defect_at_cap():
    assert should_reset_attempt_budget(["behavior: fn returns X"], 5) is False


def test_reset_denied_for_spec_ambiguity():
    assert should_reset_attempt_budget(["no known prefix"], 0) is False


def test_reset_denied_for_infra_transient():
    # Infra resets are owned by the dedicated infra-recovery path.
    assert should_reset_attempt_budget(["ECONNRESET"], 0) is False


# ---------------------------------------------------------------------------
# f_r7_479_... entry point (side-effecting reset)
# ---------------------------------------------------------------------------


def test_entry_point_resets_to_ready_on_code_defect():
    db = _RecordingDB()
    granted = f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="dd11d1f8-0000-0000-0000-000000000000",
        db_update_fn=db,
        failed_acs=["behavior: fn returns X"],
        refinement_attempts=3,
    )
    assert granted is True
    assert db.calls == [
        ("dd11d1f8-0000-0000-0000-000000000000", {"status": "ready"})
    ]


def test_entry_point_no_reset_at_cap():
    db = _RecordingDB()
    granted = f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="dd11d1f8-0000-0000-0000-000000000000",
        db_update_fn=db,
        failed_acs=["behavior: fn returns X"],
        refinement_attempts=5,
    )
    assert granted is False
    assert db.calls == []


def test_entry_point_no_reset_on_spec_ambiguity():
    db = _RecordingDB()
    granted = f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="dd11d1f8-0000-0000-0000-000000000000",
        db_update_fn=db,
        failed_acs=["no known prefix"],
        refinement_attempts=0,
    )
    assert granted is False
    assert db.calls == []


def test_entry_point_no_reset_on_infra():
    db = _RecordingDB()
    granted = f_r7_479_rca_auto_reset_must_grant_fresh_attempt_budget_when(
        feature_id="dd11d1f8-0000-0000-0000-000000000000",
        db_update_fn=db,
        failed_acs=["ETIMEDOUT"],
        refinement_attempts=0,
    )
    assert granted is False
    assert db.calls == []
