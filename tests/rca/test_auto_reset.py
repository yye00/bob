"""Tests for bob.rca.auto_reset — F-R7-479.

Verifies that:
- ``should_grant_fresh_attempt`` is importable from ``bob.rca.auto_reset``
- The function satisfies the core grant/deny rules for all classification values
- ``auto_reset_on_code_defect`` is callable from this submodule
"""

from __future__ import annotations

import pytest

from bob.rca.auto_reset import (
    auto_reset_on_code_defect,
    classify_verification_failure,
    should_grant_fresh_attempt,
)


# ---------------------------------------------------------------------------
# should_grant_fresh_attempt — core rules
# ---------------------------------------------------------------------------


def test_should_grant_code_defect_below_cap():
    assert should_grant_fresh_attempt("code_emission_defect", 0) is True
    assert should_grant_fresh_attempt("code_emission_defect", 1) is True
    assert should_grant_fresh_attempt("code_emission_defect", 4) is True


def test_should_not_grant_code_defect_at_cap():
    assert should_grant_fresh_attempt("code_emission_defect", 5) is False


def test_should_not_grant_code_defect_past_cap():
    assert should_grant_fresh_attempt("code_emission_defect", 6) is False


def test_should_grant_infra_transient_always():
    assert should_grant_fresh_attempt("infra_transient", 0) is True
    assert should_grant_fresh_attempt("infra_transient", 5) is True
    assert should_grant_fresh_attempt("infra_transient", 100) is True


def test_should_not_grant_spec_ambiguity():
    assert should_grant_fresh_attempt("spec_ambiguity", 0) is False
    assert should_grant_fresh_attempt("spec_ambiguity", 1) is False


def test_should_not_grant_unknown_classification():
    assert should_grant_fresh_attempt("unknown_classification", 0) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# classify_verification_failure — accessible from this submodule
# ---------------------------------------------------------------------------


def test_classify_pytest_ac_returns_code_emission_defect():
    result = classify_verification_failure(["pytest: tests/test_foo.py"])
    assert result == "code_emission_defect"


def test_classify_empty_returns_spec_ambiguity():
    result = classify_verification_failure([])
    assert result == "spec_ambiguity"


def test_classify_infra_pattern_returns_infra_transient():
    result = classify_verification_failure(["OSError: [Errno 111] Connection refused"])
    assert result == "infra_transient"


# ---------------------------------------------------------------------------
# auto_reset_on_code_defect — callable from bob.rca.auto_reset
# ---------------------------------------------------------------------------


def _make_db():
    calls: list[dict] = []

    def db_update_fn(feature_id: str, **kwargs):
        calls.append({"feature_id": feature_id, **kwargs})

    return calls, db_update_fn


def test_auto_reset_grants_for_pytest_ac():
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="test-feat-id",
        db_update_fn=db_fn,
        failed_acs=["pytest: tests/test_something.py"],
        refinement_attempts=2,
    )
    assert result is True
    assert len(calls) == 1
    assert calls[0]["status"] == "ready"


def test_auto_reset_does_not_grant_at_cap():
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="test-feat-cap",
        db_update_fn=db_fn,
        failed_acs=["pytest: tests/test_something.py"],
        refinement_attempts=5,
    )
    assert result is False
    assert len(calls) == 0


def test_auto_reset_does_not_grant_spec_ambiguity():
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="test-feat-spec",
        db_update_fn=db_fn,
        failed_acs=["references undefined symbol XYZ"],
        refinement_attempts=1,
    )
    assert result is False
    assert len(calls) == 0


def test_auto_reset_does_not_grant_infra_transient():
    calls, db_fn = _make_db()
    result = auto_reset_on_code_defect(
        feature_id="test-feat-infra",
        db_update_fn=db_fn,
        failed_acs=["OSError: [Errno 111] Connection refused"],
        refinement_attempts=0,
    )
    assert result is False
    assert len(calls) == 0


def test_auto_reset_preserves_attempt_count():
    calls, db_fn = _make_db()
    auto_reset_on_code_defect(
        feature_id="test-feat-budget",
        db_update_fn=db_fn,
        failed_acs=["behavior: foo returns bar"],
        refinement_attempts=3,
    )
    assert calls[0]["status"] == "ready"
    assert "refinement_attempts" not in calls[0]
