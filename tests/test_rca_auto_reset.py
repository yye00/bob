"""Tests for bob3.rca.auto_reset_on_code_defect (F-R7-479 extension).

Verifies that a verification-gate failure on plausibly-fixable code ACs
grants a fresh attempt budget instead of NH-demoting, while spec_ambiguity
and cap-reached cases still NH.
"""

from __future__ import annotations

import logging

import pytest

from bob3.rca import (
    auto_reset_on_code_defect,
    classify_verification_failure_cause,
    should_grant_fresh_attempt_budget,
)
from bob3.rca_classifier import (
    Classification,
    classify_verification_failure,
    should_grant_fresh_attempt,
)


def _make_db():
    """Return (calls_list, db_update_fn) for capturing update calls."""
    calls: list[dict] = []

    def db_update_fn(feature_id: str, **kwargs):
        calls.append({"feature_id": feature_id, **kwargs})

    return calls, db_update_fn


# ---------------------------------------------------------------------------
# Unit: classify_verification_failure (re-export from rca_classifier)
# ---------------------------------------------------------------------------


def test_rca_classifier_behavior_ac_is_code_emission_defect():
    assert classify_verification_failure(["behavior: foo returns bar"]) == "code_emission_defect"


def test_rca_classifier_integration_ac_is_code_emission_defect():
    assert classify_verification_failure(["integration: module.fn works"]) == "code_emission_defect"


def test_rca_classifier_pytest_ac_is_code_emission_defect():
    assert classify_verification_failure(["pytest: tests/test_foo.py"]) == "code_emission_defect"


def test_rca_classifier_infra_pattern_is_infra_transient():
    assert classify_verification_failure(["OSError: [Errno 111]"]) == "infra_transient"


def test_rca_classifier_spec_ambiguity_fallback():
    assert classify_verification_failure(["SomeNonsenseThatIsNotCode"]) == "spec_ambiguity"


def test_rca_classifier_empty_list_is_spec_ambiguity():
    assert classify_verification_failure([]) == "spec_ambiguity"


# ---------------------------------------------------------------------------
# Unit: should_grant_fresh_attempt
# ---------------------------------------------------------------------------


def test_should_grant_code_emission_defect_below_cap():
    assert should_grant_fresh_attempt("code_emission_defect", 3) is True


def test_should_grant_code_emission_defect_at_cap_is_false():
    assert should_grant_fresh_attempt("code_emission_defect", 5) is False


def test_should_grant_infra_transient_always():
    assert should_grant_fresh_attempt("infra_transient", 5) is True


def test_should_not_grant_spec_ambiguity():
    assert should_grant_fresh_attempt("spec_ambiguity", 0) is False


# ---------------------------------------------------------------------------
# Unit: auto_reset_on_code_defect
# ---------------------------------------------------------------------------


def test_auto_reset_on_code_defect_resets_to_ready():
    """Behavior AC below cap → feature reset to ready."""
    calls, db_fn = _make_db()
    fid = "aaaabbbb-0000-0000-0000-000000000001"
    result = auto_reset_on_code_defect(
        feature_id=fid,
        db_update_fn=db_fn,
        failed_acs=["behavior: foo returns bar"],
        refinement_attempts=2,
    )
    assert result is True
    assert len(calls) == 1
    assert calls[0]["feature_id"] == fid
    assert calls[0]["status"] == "ready"


def test_auto_reset_on_code_defect_preserves_attempt_count():
    """Attempt count must NOT be reset to 0 — budget accounting must hold."""
    calls, db_fn = _make_db()
    auto_reset_on_code_defect(
        feature_id="aaaabbbb-0000-0000-0000-000000000002",
        db_update_fn=db_fn,
        failed_acs=["pytest: tests/test_something.py"],
        refinement_attempts=3,
    )
    assert len(calls) == 1
    assert calls[0].get("refinement_attempts") is None or "refinement_attempts" not in calls[0], (
        "auto_reset_on_code_defect must not reset refinement_attempts in the DB call"
    )


def test_auto_reset_on_code_defect_returns_false_at_cap():
    """At the 5-attempt cap, NH stands — no reset."""
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="aaaabbbb-0000-0000-0000-000000000003",
        db_update_fn=db_fn,
        failed_acs=["behavior: something does X"],
        refinement_attempts=5,
    )
    assert result is False
    assert len(calls) == 0


def test_auto_reset_on_code_defect_spec_ambiguity_nh_stands():
    """spec_ambiguity classification → False, no reset."""
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="aaaabbbb-0000-0000-0000-000000000004",
        db_update_fn=db_fn,
        failed_acs=["Completely undefined symbol XYZ9999"],
        refinement_attempts=1,
    )
    assert result is False
    assert len(calls) == 0


def test_auto_reset_on_code_defect_infra_returns_false():
    """infra_transient classification → False (deferred to infra path)."""
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="aaaabbbb-0000-0000-0000-000000000005",
        db_update_fn=db_fn,
        failed_acs=["subprocess.CalledProcessError: returned non-zero"],
        refinement_attempts=1,
    )
    assert result is False
    assert len(calls) == 0


def test_auto_reset_on_code_defect_logs_sentinel(caplog):
    """Successful reset must log the rca_granted_fresh_attempt sentinel."""
    _, db_fn = _make_db()
    with caplog.at_level(logging.INFO, logger="bob3.rca"):
        auto_reset_on_code_defect(
            feature_id="aaaabbbb-0000-0000-0000-000000000006",
            db_update_fn=db_fn,
            failed_acs=["integration: some.module.fn does thing"],
            refinement_attempts=1,
        )
    assert any("rca_granted_fresh_attempt" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Regression: dd11d1f8-class scenario (attempt 3, two budget slots unused)
# ---------------------------------------------------------------------------


def test_dd11d1f8_regression_attempt_3_grants_fresh():
    """Feature dd11d1f8 reproduced: attempt=3, behavior AC → fresh attempt granted."""
    calls, db_fn = _make_db()
    failed_acs = [
        "behavior: ownership_detection returns correct owner for regression commit",
        "integration: detect_regression routes through ownership resolution",
    ]
    result = auto_reset_on_code_defect(
        feature_id="dd11d1f8-0000-0000-0000-000000000000",
        db_update_fn=db_fn,
        failed_acs=failed_acs,
        refinement_attempts=3,
    )
    assert result is True, "Must grant fresh attempt at refinement_attempts=3"
    assert calls[0]["status"] == "ready"


def test_dd11d1f8_regression_attempt_4_still_grants():
    """Attempt=4 with behavior AC still has budget — must grant."""
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="dd11d1f8-0000-0000-0000-000000000001",
        db_update_fn=db_fn,
        failed_acs=["behavior: something does X"],
        refinement_attempts=4,
    )
    assert result is True


def test_dd11d1f8_regression_attempt_5_nh_stands():
    """Attempt=5 is the cap — NH must stand even for behavior ACs."""
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="dd11d1f8-0000-0000-0000-000000000002",
        db_update_fn=db_fn,
        failed_acs=["behavior: something does X"],
        refinement_attempts=5,
    )
    assert result is False
    assert len(calls) == 0


# ---------------------------------------------------------------------------
# F-R7-479 canonical function names: classify_verification_failure_cause
# and should_grant_fresh_attempt_budget (required by ACs)
# ---------------------------------------------------------------------------


def test_classify_verification_failure_cause_behavior_ac():
    """classify_verification_failure_cause: behavior AC → code_emission_defect."""
    assert classify_verification_failure_cause(["behavior: foo returns bar"]) == "code_emission_defect"


def test_classify_verification_failure_cause_pytest_ac():
    """classify_verification_failure_cause: pytest AC → code_emission_defect."""
    assert classify_verification_failure_cause(["pytest: tests/test_foo.py"]) == "code_emission_defect"


def test_classify_verification_failure_cause_integration_ac():
    """classify_verification_failure_cause: integration AC → code_emission_defect."""
    assert classify_verification_failure_cause(["integration: module.fn works"]) == "code_emission_defect"


def test_classify_verification_failure_cause_infra():
    """classify_verification_failure_cause: OSError → infra_transient."""
    assert classify_verification_failure_cause(["OSError: no such process"]) == "infra_transient"


def test_classify_verification_failure_cause_spec_ambiguity():
    """classify_verification_failure_cause: unknown → spec_ambiguity."""
    assert classify_verification_failure_cause(["undefined symbol XYZ"]) == "spec_ambiguity"


# Boundary case: empty list — must return well-defined result, not crash
def test_classify_verification_failure_cause_empty_list():
    """Boundary: empty list → spec_ambiguity (well-defined, does not crash)."""
    result = classify_verification_failure_cause([])
    assert result == "spec_ambiguity"


# Boundary case: zero input — list of empty string
def test_classify_verification_failure_cause_zero_input_empty_string():
    """Boundary: list with empty string → spec_ambiguity (well-defined, not crash)."""
    result = classify_verification_failure_cause([""])
    assert result == "spec_ambiguity"


# Invalid input: None → raises ValueError
def test_classify_verification_failure_cause_none_raises_value_error():
    """Invalid input None → ValueError, not silent success."""
    with pytest.raises(ValueError):
        classify_verification_failure_cause(None)  # type: ignore[arg-type]


# Invalid input: string instead of list → raises TypeError
def test_classify_verification_failure_cause_string_raises_type_error():
    """Invalid input (string) → TypeError, not silent success."""
    with pytest.raises(TypeError):
        classify_verification_failure_cause("behavior: foo")  # type: ignore[arg-type]


# Invalid input: int instead of list → raises TypeError
def test_classify_verification_failure_cause_int_raises_type_error():
    """Invalid input (int) → TypeError, not silent success."""
    with pytest.raises(TypeError):
        classify_verification_failure_cause(42)  # type: ignore[arg-type]


def test_should_grant_fresh_attempt_budget_code_defect_below_cap():
    """should_grant_fresh_attempt_budget: code_emission_defect below cap → True."""
    assert should_grant_fresh_attempt_budget("code_emission_defect", 3) is True


def test_should_grant_fresh_attempt_budget_code_defect_at_cap():
    """should_grant_fresh_attempt_budget: code_emission_defect at cap (5) → False."""
    assert should_grant_fresh_attempt_budget("code_emission_defect", 5) is False


def test_should_grant_fresh_attempt_budget_infra_always_grants():
    """should_grant_fresh_attempt_budget: infra_transient always grants."""
    assert should_grant_fresh_attempt_budget("infra_transient", 5) is True


def test_should_grant_fresh_attempt_budget_spec_ambiguity_never_grants():
    """should_grant_fresh_attempt_budget: spec_ambiguity never grants."""
    assert should_grant_fresh_attempt_budget("spec_ambiguity", 0) is False


# Boundary case: zero refinement_attempts → well-defined result, not crash
def test_should_grant_fresh_attempt_budget_zero_attempts():
    """Boundary: refinement_attempts=0 → True for code_emission_defect (first attempt)."""
    result = should_grant_fresh_attempt_budget("code_emission_defect", 0)
    assert result is True


# Invalid input: negative attempts → raises ValueError
def test_should_grant_fresh_attempt_budget_negative_attempts_raises():
    """Invalid input (negative attempts) → ValueError, not silent success."""
    with pytest.raises(ValueError):
        should_grant_fresh_attempt_budget("code_emission_defect", -1)


# Invalid input: string instead of int → raises TypeError
def test_should_grant_fresh_attempt_budget_string_attempts_raises():
    """Invalid input (string instead of int) → TypeError, not silent success."""
    with pytest.raises(TypeError):
        should_grant_fresh_attempt_budget("code_emission_defect", "3")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-required canonical test names (F-R7-479)
# ---------------------------------------------------------------------------


def test_code_emission_defect_grants_fresh_budget():
    """code_emission_defect below cap → fresh budget granted (feature reset to ready)."""
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="58bef098-0000-0000-0000-000000000001",
        db_update_fn=db_fn,
        failed_acs=["behavior: verify_gate returns correct result"],
        refinement_attempts=2,
    )
    assert result is True
    assert len(calls) == 1
    assert calls[0]["status"] == "ready"


def test_spec_ambiguity_does_not_grant_fresh_budget():
    """spec_ambiguity classification → NH stands, no fresh budget granted."""
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="58bef098-0000-0000-0000-000000000002",
        db_update_fn=db_fn,
        failed_acs=["Undefined symbol that no code could satisfy XYZ9999"],
        refinement_attempts=1,
    )
    assert result is False
    assert len(calls) == 0
