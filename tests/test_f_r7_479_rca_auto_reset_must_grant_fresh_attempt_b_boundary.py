"""Boundary tests for F-R7-479: empty, zero, or minimum inputs return well-defined results.

Verifies that the should_grant_fresh_attempt function and related API do not raise
on edge-case inputs — boundary inputs produce deterministic, documented outputs.
"""

from __future__ import annotations

import pytest

from bob.rca import classify_verification_failure_cause, should_grant_fresh_attempt_budget
from bob.rca_classifier import classify_verification_failure, should_grant_fresh_attempt


# ---------------------------------------------------------------------------
# Boundary: classify_verification_failure_cause
# ---------------------------------------------------------------------------


def test_classify_empty_failed_acs_returns_spec_ambiguity():
    """Empty list → spec_ambiguity (well-defined, does not raise)."""
    result = classify_verification_failure_cause([])
    assert result == "spec_ambiguity"


def test_classify_single_empty_string_returns_spec_ambiguity():
    """List with a single empty string → spec_ambiguity (minimum non-None input)."""
    result = classify_verification_failure_cause([""])
    assert result == "spec_ambiguity"


def test_classify_whitespace_only_ac_returns_spec_ambiguity():
    """List with whitespace-only AC → spec_ambiguity (no prefix match)."""
    result = classify_verification_failure_cause(["   "])
    assert result == "spec_ambiguity"


def test_classify_single_behavior_ac_returns_code_emission_defect():
    """Single-element list with behavior prefix → code_emission_defect."""
    result = classify_verification_failure_cause(["behavior: foo returns bar"])
    assert result == "code_emission_defect"


def test_classify_single_pytest_ac_returns_code_emission_defect():
    """Single-element list with pytest prefix → code_emission_defect."""
    result = classify_verification_failure_cause(["pytest: tests/test_foo.py"])
    assert result == "code_emission_defect"


def test_classify_single_integration_ac_returns_code_emission_defect():
    """Single-element list with integration prefix → code_emission_defect."""
    result = classify_verification_failure_cause(["integration: bob.rca.fn works"])
    assert result == "code_emission_defect"


# ---------------------------------------------------------------------------
# Boundary: should_grant_fresh_attempt_budget
# ---------------------------------------------------------------------------


def test_grant_at_zero_refinement_attempts_code_defect():
    """refinement_attempts=0 is the minimum valid value — must not raise and must grant."""
    result = should_grant_fresh_attempt_budget("code_emission_defect", 0)
    assert result is True


def test_grant_at_one_refinement_attempt_code_defect():
    """refinement_attempts=1 → still within cap → grant."""
    result = should_grant_fresh_attempt_budget("code_emission_defect", 1)
    assert result is True


def test_grant_at_four_refinement_attempts_code_defect():
    """refinement_attempts=4 is just below the 5-cap → grant."""
    result = should_grant_fresh_attempt_budget("code_emission_defect", 4)
    assert result is True


def test_no_grant_at_five_refinement_attempts_code_defect():
    """refinement_attempts=5 is exactly at cap → no grant."""
    result = should_grant_fresh_attempt_budget("code_emission_defect", 5)
    assert result is False


def test_no_grant_at_six_refinement_attempts_code_defect():
    """refinement_attempts=6 exceeds cap → no grant (past-cap boundary)."""
    result = should_grant_fresh_attempt_budget("code_emission_defect", 6)
    assert result is False


def test_grant_infra_transient_at_cap():
    """infra_transient always grants even at refinement_attempts=5."""
    result = should_grant_fresh_attempt_budget("infra_transient", 5)
    assert result is True


def test_grant_infra_transient_at_zero():
    """infra_transient always grants at refinement_attempts=0."""
    result = should_grant_fresh_attempt_budget("infra_transient", 0)
    assert result is True


def test_no_grant_spec_ambiguity_at_zero():
    """spec_ambiguity never grants even at refinement_attempts=0."""
    result = should_grant_fresh_attempt_budget("spec_ambiguity", 0)
    assert result is False


def test_no_grant_spec_ambiguity_at_high_value():
    """spec_ambiguity never grants at any refinement count."""
    result = should_grant_fresh_attempt_budget("spec_ambiguity", 100)
    assert result is False


# ---------------------------------------------------------------------------
# Boundary: rca_classifier.should_grant_fresh_attempt (lower-level)
# ---------------------------------------------------------------------------


def test_rca_classifier_grant_at_zero_attempts():
    """Lower-level should_grant_fresh_attempt: code_emission_defect at 0 → True."""
    result = should_grant_fresh_attempt("code_emission_defect", 0)
    assert result is True


def test_rca_classifier_no_grant_at_cap():
    """Lower-level should_grant_fresh_attempt: code_emission_defect at 5 → False."""
    result = should_grant_fresh_attempt("code_emission_defect", 5)
    assert result is False


def test_rca_classifier_infra_at_zero():
    """Lower-level should_grant_fresh_attempt: infra_transient at 0 → True."""
    result = should_grant_fresh_attempt("infra_transient", 0)
    assert result is True
