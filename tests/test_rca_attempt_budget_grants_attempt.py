"""Tests for should_grant_fresh_attempt — grant logic."""

import pytest
from bob3.orchestrator.rca_attempt_budget import should_grant_fresh_attempt


def test_code_emission_defect_at_attempt_3_grants_fresh():
    """code_emission_defect at attempts=3 → True (primary use case)."""
    assert should_grant_fresh_attempt("code_emission_defect", refinement_attempts=3) is True


def test_code_emission_defect_at_attempt_1_grants_fresh():
    """code_emission_defect at attempts=1 → True."""
    assert should_grant_fresh_attempt("code_emission_defect", refinement_attempts=1) is True


def test_code_emission_defect_at_attempt_4_grants_fresh():
    """code_emission_defect at attempts=4 → True (still under cap of 5)."""
    assert should_grant_fresh_attempt("code_emission_defect", refinement_attempts=4) is True


def test_infra_transient_grants_regardless_of_attempt_count():
    """infra_transient → True regardless of attempt count."""
    assert should_grant_fresh_attempt("infra_transient", refinement_attempts=0) is True
    assert should_grant_fresh_attempt("infra_transient", refinement_attempts=3) is True
    assert should_grant_fresh_attempt("infra_transient", refinement_attempts=4) is True


def test_spec_ambiguity_never_grants():
    """spec_ambiguity → always False (genuinely terminal)."""
    assert should_grant_fresh_attempt("spec_ambiguity", refinement_attempts=0) is False
    assert should_grant_fresh_attempt("spec_ambiguity", refinement_attempts=3) is False
    assert should_grant_fresh_attempt("spec_ambiguity", refinement_attempts=10) is False


def test_unknown_classification_does_not_grant():
    """Unknown classification → False (safe default)."""
    assert should_grant_fresh_attempt("unknown_classification", refinement_attempts=2) is False
