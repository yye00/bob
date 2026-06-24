"""Tests for research_strategies_generator — canonical AC emitter with gate validation."""

from __future__ import annotations

import pytest

from research_strategies_generator import (
    ACGateResult,
    SYNTHESIS_BLOCKED_STATUS,
    emit_canonical_structured_acs,
    generate_with_gate,
    validate_acs_against_spec_quality_gate,
)


class TestEmitCanonicalStructuredAcs:
    def test_returns_list_of_strings(self):
        acs = emit_canonical_structured_acs("path_finding_retry")
        assert isinstance(acs, list)
        assert all(isinstance(ac, str) for ac in acs)

    def test_minimum_four_acs(self):
        acs = emit_canonical_structured_acs("my_feature")
        assert len(acs) >= 4

    def test_all_acs_are_canonical(self):
        acs = emit_canonical_structured_acs("path_finding_retry")
        result = validate_acs_against_spec_quality_gate(acs)
        assert result.non_canonical == [], (
            f"Non-canonical ACs found: {result.non_canonical}"
        )

    def test_negative_error_path_ac_included(self):
        """At least one AC must reference an error/failure path."""
        acs = emit_canonical_structured_acs("path_finding_retry")
        result = validate_acs_against_spec_quality_gate(acs)
        assert result.has_negative_path_ac, (
            "emit_canonical_structured_acs must include at least one negative/error-path AC"
        )

    def test_gate_passes_for_generated_acs(self):
        acs = emit_canonical_structured_acs("my_feature")
        result = validate_acs_against_spec_quality_gate(acs)
        assert result.passed

    def test_includes_pytest_ac(self):
        acs = emit_canonical_structured_acs("my_feature")
        assert any(ac.lower().startswith("pytest:") for ac in acs)

    def test_includes_function_defined_ac(self):
        acs = emit_canonical_structured_acs("my_feature")
        assert any(ac.lower().startswith("function defined:") for ac in acs)

    def test_includes_file_exists_ac(self):
        acs = emit_canonical_structured_acs("my_feature")
        assert any(ac.lower().startswith("file exists:") for ac in acs)

    def test_raises_value_error_for_empty_topic(self):
        with pytest.raises(ValueError, match="topic"):
            emit_canonical_structured_acs("")

    def test_raises_value_error_for_whitespace_topic(self):
        with pytest.raises(ValueError, match="topic"):
            emit_canonical_structured_acs("   ")

    def test_raises_type_error_for_none_topic(self):
        with pytest.raises((TypeError, ValueError)):
            emit_canonical_structured_acs(None)  # type: ignore[arg-type]

    def test_raises_type_error_for_int_topic(self):
        with pytest.raises((TypeError, ValueError)):
            emit_canonical_structured_acs(42)  # type: ignore[arg-type]


class TestValidateAcsAgainstSpecQualityGate:
    def test_returns_ac_gate_result(self):
        result = validate_acs_against_spec_quality_gate(["pytest: tests/test_foo.py"])
        assert isinstance(result, ACGateResult)

    def test_passes_all_canonical_with_error_ac(self):
        acs = [
            "pytest: tests/test_foo.py",
            "Function defined: foo.bar",
            "behavior: bar raises ValueError when input is invalid",
        ]
        result = validate_acs_against_spec_quality_gate(acs)
        assert result.passed
        assert result.non_canonical == []
        assert result.has_negative_path_ac

    def test_fails_when_prose_ac_present(self):
        acs = [
            "pytest: tests/test_foo.py",
            "The system should handle errors gracefully",
        ]
        result = validate_acs_against_spec_quality_gate(acs)
        assert not result.passed
        assert "The system should handle errors gracefully" in result.non_canonical

    def test_fails_empty_list(self):
        result = validate_acs_against_spec_quality_gate([])
        assert not result.passed

    def test_fails_without_negative_path_ac(self):
        acs = [
            "pytest: tests/test_foo.py",
            "Function defined: foo.bar",
            "File exists: src/foo.py",
        ]
        result = validate_acs_against_spec_quality_gate(acs)
        assert not result.passed
        assert not result.has_negative_path_ac

    def test_raises_type_error_for_string_input(self):
        with pytest.raises(TypeError):
            validate_acs_against_spec_quality_gate("not a list")  # type: ignore[arg-type]

    def test_raises_type_error_for_none_input(self):
        with pytest.raises(TypeError):
            validate_acs_against_spec_quality_gate(None)  # type: ignore[arg-type]

    def test_raises_value_error_for_non_string_element(self):
        with pytest.raises((TypeError, ValueError)):
            validate_acs_against_spec_quality_gate([None])  # type: ignore[arg-type]

    def test_errors_list_populated_on_failure(self):
        acs = ["The system handles errors gracefully"]
        result = validate_acs_against_spec_quality_gate(acs)
        assert not result.passed
        assert len(result.errors) > 0

    def test_non_canonical_list_accurate(self):
        prose = "All things should work"
        canonical = "pytest: tests/test_bar.py"
        result = validate_acs_against_spec_quality_gate([prose, canonical])
        assert prose in result.non_canonical
        assert canonical not in result.non_canonical


class TestGenerateWithGate:
    def test_returns_dict_with_expected_keys(self):
        result = generate_with_gate("my_feature")
        assert "status" in result
        assert "acceptance_criteria" in result
        assert "attempts" in result
        assert "non_canonical" in result

    def test_status_ok_for_valid_topic(self):
        result = generate_with_gate("path_finding_retry")
        assert result["status"] == "ok"

    def test_acceptance_criteria_are_canonical(self):
        result = generate_with_gate("path_finding_retry")
        assert result["status"] == "ok"
        gate_result = validate_acs_against_spec_quality_gate(result["acceptance_criteria"])
        assert gate_result.passed

    def test_attempts_is_positive(self):
        result = generate_with_gate("my_feature")
        assert result["attempts"] >= 1

    def test_non_canonical_empty_on_success(self):
        result = generate_with_gate("my_feature")
        assert result["status"] == "ok"
        assert result["non_canonical"] == []

    def test_raises_type_error_for_non_string_topic(self):
        with pytest.raises(TypeError):
            generate_with_gate(42)  # type: ignore[arg-type]

    def test_raises_value_error_for_empty_topic(self):
        with pytest.raises(ValueError):
            generate_with_gate("")

    def test_custom_max_retries_respected(self):
        result = generate_with_gate("my_feature", max_retries=1)
        assert result["attempts"] >= 1
        assert result["attempts"] <= 1

    def test_synthesis_blocked_status_constant(self):
        assert SYNTHESIS_BLOCKED_STATUS == "synthesis_blocked_invalid_acs"
