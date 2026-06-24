"""Tests for should_grant_fresh_attempt — boundary at attempts=5."""

import pytest
from bob.orchestrator.rca_attempt_budget import should_grant_fresh_attempt


def test_code_emission_defect_at_5_returns_false():
    """code_emission_defect at attempts=5 → False (at cap)."""
    assert should_grant_fresh_attempt("code_emission_defect", refinement_attempts=5) is False


def test_code_emission_defect_above_5_returns_false():
    """code_emission_defect at attempts=6 → False (beyond cap)."""
    assert should_grant_fresh_attempt("code_emission_defect", refinement_attempts=6) is False


def test_infra_transient_at_5_still_grants():
    """infra_transient at attempts=5 → True (no cap for infra)."""
    assert should_grant_fresh_attempt("infra_transient", refinement_attempts=5) is True


def test_infra_transient_at_10_still_grants():
    """infra_transient at attempts=10 → True (no cap for infra)."""
    assert should_grant_fresh_attempt("infra_transient", refinement_attempts=10) is True


def test_spec_ambiguity_at_0_returns_false():
    """spec_ambiguity at attempts=0 → False (always terminal)."""
    assert should_grant_fresh_attempt("spec_ambiguity", refinement_attempts=0) is False


def test_boundary_4_grants_code_defect():
    """code_emission_defect at attempts=4 → True (one below cap)."""
    assert should_grant_fresh_attempt("code_emission_defect", refinement_attempts=4) is True
