"""Tests for classify_verification_failure — code_emission_defect classification."""

import pytest
from bob.orchestrator.rca_attempt_budget import classify_verification_failure


def test_behavior_ac_returns_code_emission_defect():
    """Behavior-type ACs → code_emission_defect."""
    failed_acs = ["behavior: foo does X when Y"]
    result = classify_verification_failure(failed_acs)
    assert result == "code_emission_defect"


def test_integration_ac_returns_code_emission_defect():
    """Integration-type ACs → code_emission_defect."""
    failed_acs = ["integration: auto_reset_if_infra calls should_grant_fresh_attempt"]
    result = classify_verification_failure(failed_acs)
    assert result == "code_emission_defect"


def test_pytest_ac_returns_code_emission_defect():
    """pytest-type ACs → code_emission_defect."""
    failed_acs = ["pytest: tests/test_something.py asserts foo returns True"]
    result = classify_verification_failure(failed_acs)
    assert result == "code_emission_defect"


def test_mixed_behavior_and_integration_returns_code_emission_defect():
    """Multiple behavior/integration ACs → code_emission_defect."""
    failed_acs = [
        "behavior: classify_verification_failure returns code_emission_defect",
        "integration: bob.orchestrator.rca_infra_recovery.auto_reset_if_infra extends",
    ]
    result = classify_verification_failure(failed_acs)
    assert result == "code_emission_defect"


def test_spec_ambiguity_returns_spec_ambiguity():
    """ACs with symbol references no code could satisfy → spec_ambiguity."""
    failed_acs = ["UndefinedSymbol123XYZ must return the value of NonExistentConstant999"]
    result = classify_verification_failure(failed_acs)
    assert result == "spec_ambiguity"


def test_subprocess_error_returns_infra_transient():
    """Subprocess/IO error patterns → infra_transient."""
    failed_acs = ["subprocess.CalledProcessError: Command returned non-zero exit status"]
    result = classify_verification_failure(failed_acs)
    assert result == "infra_transient"


def test_io_error_returns_infra_transient():
    """IOError/OSError patterns → infra_transient."""
    failed_acs = ["OSError: [Errno 111] Connection refused"]
    result = classify_verification_failure(failed_acs)
    assert result == "infra_transient"


def test_certificate_error_returns_infra_transient():
    """TLS/cert error patterns → infra_transient."""
    failed_acs = ["self signed certificate in certificate chain"]
    result = classify_verification_failure(failed_acs)
    assert result == "infra_transient"


def test_empty_failed_acs_returns_spec_ambiguity():
    """Empty failed ACs list → spec_ambiguity (can't determine)."""
    result = classify_verification_failure([])
    assert result == "spec_ambiguity"


def test_behavior_keyword_case_insensitive():
    """The 'behavior:' prefix is case-insensitive."""
    failed_acs = ["Behavior: SomeClass.some_method returns expected value"]
    result = classify_verification_failure(failed_acs)
    assert result == "code_emission_defect"
