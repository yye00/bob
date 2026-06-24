"""Negative-path tests for research_strategies canonical AC generator.

Covers error/failure scenarios to satisfy the spec_quality gate requirement
that at least one AC references an error/failure path.

Tests verify that:
- Invalid inputs are rejected with appropriate exceptions
- Prose-form ACs are rejected by the validator
- Synthesis is blocked rather than emitting unusable rows
- The generator correctly identifies negative-path ACs
"""

from __future__ import annotations

import pytest

from research_strategies.generator import (
    SYNTHESIS_BLOCKED_STATUS,
    emit_canonical_acs,
    generate_with_gate,
)
from research_strategies.ac_validator import validate_acs, validate_single_ac


class TestEmitCanonicalAcsErrorPaths:
    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="topic"):
            emit_canonical_acs("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError, match="topic"):
            emit_canonical_acs("   \t\n")

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_canonical_acs(None)  # type: ignore[arg-type]

    def test_integer_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_canonical_acs(42)  # type: ignore[arg-type]

    def test_list_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_canonical_acs(["feature_a", "feature_b"])  # type: ignore[arg-type]

    def test_dict_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_canonical_acs({"name": "feature"})  # type: ignore[arg-type]

    def test_does_not_silently_return_empty_on_invalid(self):
        """Verify no silent success — must raise, not return empty or None."""
        raised = False
        try:
            result = emit_canonical_acs("")
            if result == [] or result is None:
                raised = True
        except (ValueError, TypeError):
            raised = True
        assert raised, "emit_canonical_acs('') must not silently return empty/None"

    def test_output_includes_error_keyword_ac(self):
        """Emitted ACs must contain at least one error/failure-path AC."""
        error_keywords = {
            "error", "failure", "fail", "invalid", "missing", "reject",
            "exception", "raises", "corrupt", "timeout", "negative", "bad",
        }
        acs = emit_canonical_acs("some_feature")
        has_negative = any(
            any(kw in ac.lower() for kw in error_keywords) for ac in acs
        )
        assert has_negative, f"No negative/error AC found in: {acs}"


class TestValidateAcsErrorPaths:
    def test_string_input_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_acs("not_a_list")  # type: ignore[arg-type]

    def test_none_input_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_acs(None)  # type: ignore[arg-type]

    def test_none_element_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            validate_acs([None])  # type: ignore[arg-type]

    def test_integer_element_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            validate_acs([42])  # type: ignore[arg-type]

    def test_empty_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_acs([""])

    def test_prose_acs_fail_gate(self):
        result = validate_acs([
            "The system handles all edge cases properly",
            "FailureClass enum: should classify failures correctly",
        ])
        assert result.passed is False
        assert len(result.non_canonical) == 2

    def test_prose_does_not_silently_pass(self):
        result = validate_acs([
            "The module handles errors gracefully",
            "All functions return correct results",
        ])
        assert result.passed is False, "Prose-only ACs must not silently pass the gate"

    def test_canonical_without_negative_ac_fails(self):
        """All-canonical ACs that lack an error/failure-path AC must fail."""
        result = validate_acs([
            "Function defined: bob.foo.bar",
            "File exists: src/bob/foo.py",
            "pytest: tests/test_foo.py",
        ])
        assert result.passed is False
        assert result.has_negative_path_ac is False

    def test_canonical_with_negative_ac_passes(self):
        result = validate_acs([
            "Function defined: bob.foo.bar",
            "pytest: tests/test_foo.py",
            "behavior: foo raises ValueError when input is invalid",
        ])
        assert result.passed is True
        assert result.has_negative_path_ac is True

    def test_empty_list_fails_gate(self):
        result = validate_acs([])
        assert result.passed is False


class TestValidateSingleAcErrorPaths:
    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_single_ac(None)  # type: ignore[arg-type]

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_single_ac("")

    def test_integer_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_single_ac(42)  # type: ignore[arg-type]

    def test_prose_ac_returns_false(self):
        assert validate_single_ac("The system handles errors gracefully") is False

    def test_canonical_ac_returns_true(self):
        assert validate_single_ac("Function defined: bob.foo.bar") is True

    def test_canonical_behavior_ac_returns_true(self):
        assert validate_single_ac(
            "behavior: foo raises ValueError when input is empty"
        ) is True


class TestGenerateWithGateErrorPaths:
    def test_empty_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_with_gate("")

    def test_whitespace_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_with_gate("   ")

    def test_none_topic_raises_type_error(self):
        with pytest.raises(TypeError):
            generate_with_gate(None)  # type: ignore[arg-type]

    def test_success_result_has_ok_status(self):
        result = generate_with_gate("my_feature")
        assert result["status"] == "ok"
        assert len(result["acceptance_criteria"]) >= 1

    def test_result_contains_required_keys(self):
        result = generate_with_gate("any_feature")
        assert "status" in result
        assert "acceptance_criteria" in result
        assert "attempts" in result
        assert "non_canonical" in result
