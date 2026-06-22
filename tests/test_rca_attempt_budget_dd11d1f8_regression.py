"""Regression test for dd11d1f8-class failure.

Feature dd11d1f8 (Ownership-evidenced regression detection) NH'd at attempt 3
with 2 remaining budget slots unused. The root cause: verification_gate_failed on
a behavior/integration AC was classified terminal (not infra), so auto_reset_if_infra
never fired.

This test asserts that a dd11d1f8-shaped feature (verification gate failure on
plausible-fixable emission at attempt 3) is reopened to 'ready' rather than
NH-demoted.
"""

import pytest
from bob3.orchestrator.rca_attempt_budget import (
    classify_verification_failure,
    should_grant_fresh_attempt,
)
from bob3.orchestrator.rca_infra_recovery import auto_reset_if_infra


def _make_db_updates():
    """Return a list capturing db_update_fn calls."""
    calls = []

    def db_update_fn(feature_id, **kwargs):
        calls.append({"feature_id": feature_id, **kwargs})

    return calls, db_update_fn


def test_dd11d1f8_classify_as_code_emission_defect():
    """Ownership-detection failure ACs classify as code_emission_defect."""
    failed_acs = [
        "behavior: ownership_detection returns correct owner for regression commit",
        "integration: detect_regression routes through ownership resolution",
    ]
    classification = classify_verification_failure(failed_acs)
    assert classification == "code_emission_defect"


def test_dd11d1f8_grants_fresh_at_attempt_3():
    """code_emission_defect at attempts=3 grants fresh attempt."""
    classification = "code_emission_defect"
    result = should_grant_fresh_attempt(classification, refinement_attempts=3)
    assert result is True


def test_auto_reset_reopens_feature_on_code_emission_defect(tmp_path):
    """auto_reset_if_infra with code_emission_defect transitions feature to ready.

    This is the integration test: a feature with verification-gate failure on
    behavior ACs at attempt 3 must be reset to ready (not NH-demoted).
    """
    feature_id = "dd11d1f8-0000-0000-0000-000000000000"  # synthetic dd11d1f8-shaped ID

    failed_acs = [
        "behavior: ownership_detection returns correct owner for regression commit",
        "integration: detect_regression routes through ownership resolution",
    ]

    calls, db_update_fn = _make_db_updates()

    result = auto_reset_if_infra(
        feature_id=feature_id,
        project_id="test-project",
        db_update_fn=db_update_fn,
        workspace=str(tmp_path),
        failed_acs=failed_acs,
        refinement_attempts=3,
    )

    assert result is True, "auto_reset_if_infra must return True for code_emission_defect"
    assert len(calls) == 1, "db_update_fn must be called exactly once"
    update = calls[0]
    assert update["feature_id"] == feature_id
    assert update["status"] == "ready"
    # Attempts must NOT be reset to 0 — preserve budget accounting
    assert "refinement_attempts" not in update or update.get("refinement_attempts") is None, (
        "refinement_attempts must not be reset when granting fresh attempt for code defect"
    )


def test_auto_reset_logs_sentinel(tmp_path, caplog):
    """auto_reset_if_infra logs rca_granted_fresh_attempt sentinel."""
    import logging

    feature_id = "dd11d1f8-0000-0000-0000-000000000001"
    failed_acs = ["behavior: something does X"]

    _, db_update_fn = _make_db_updates()

    with caplog.at_level(logging.INFO):
        auto_reset_if_infra(
            feature_id=feature_id,
            project_id="test-project",
            db_update_fn=db_update_fn,
            workspace=str(tmp_path),
            failed_acs=failed_acs,
            refinement_attempts=2,
        )

    sentinel_found = any(
        "rca_granted_fresh_attempt" in record.message for record in caplog.records
    )
    assert sentinel_found, "Must log rca_granted_fresh_attempt sentinel"


def test_auto_reset_does_not_reopen_at_attempt_5(tmp_path):
    """At attempt=5 (cap), feature is NOT reopened for code_emission_defect."""
    feature_id = "dd11d1f8-0000-0000-0000-000000000002"
    failed_acs = ["behavior: something does X"]

    calls, db_update_fn = _make_db_updates()

    result = auto_reset_if_infra(
        feature_id=feature_id,
        project_id="test-project",
        db_update_fn=db_update_fn,
        workspace=str(tmp_path),
        failed_acs=failed_acs,
        refinement_attempts=5,
    )

    assert result is False, "At cap (attempts=5), must not grant fresh attempt"
    assert len(calls) == 0, "db_update_fn must not be called at cap"
