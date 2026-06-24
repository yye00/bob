"""Tests for canonical AC forms emitted by bob3.research_strategies.

Covers:
- validate_ac_structure validates a single AC and returns structured result
- emit_canonical_acs produces all canonical-form ACs
- All canonical prefix forms are recognised
- Prose-form ACs are rejected
- At least one negative/error-path AC is required
"""

from __future__ import annotations

import re

import pytest

from bob3.research_strategies import (
    emit_canonical_acs,
    validate_ac_structure,
    validate_against_spec_quality_gate,
)

_CANONICAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^File exists\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^Function defined\s*:\s*[\w.]+", re.IGNORECASE),
    re.compile(r"^Class defined\s*:\s*[\w.]+", re.IGNORECASE),
    re.compile(r"^pytest\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^integration\s*:\s*[\w./:-]+", re.IGNORECASE),
    re.compile(r"^behavior\s*:\s*.+\bwhen\b.+", re.IGNORECASE),
    re.compile(r"^python\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^Field exists\s*.*:\s*\S+", re.IGNORECASE),
]

_ERROR_KEYWORDS = {
    "error", "failure", "fail", "invalid", "missing", "reject",
    "exception", "raises", "corrupt", "timeout", "negative", "bad",
}


def _is_canonical(ac: str) -> bool:
    return any(p.match(ac.strip()) for p in _CANONICAL_PATTERNS)


class TestValidateAcStructure:
    def test_canonical_function_defined_passes(self):
        result = validate_ac_structure("Function defined: bob3.research_strategies.validate_ac_structure")
        assert result["passed"] is True
        assert result["non_canonical"] == []

    def test_canonical_file_exists_passes(self):
        result = validate_ac_structure("File exists: src/bob3/research_strategies.py")
        assert result["passed"] is True
        assert result["non_canonical"] == []

    def test_canonical_pytest_passes(self):
        result = validate_ac_structure("pytest: tests/test_foo.py")
        assert result["passed"] is True

    def test_canonical_integration_passes(self):
        result = validate_ac_structure("integration: bob3.gate_resynthesis")
        assert result["passed"] is True

    def test_canonical_behavior_when_passes(self):
        result = validate_ac_structure("behavior: emit_canonical_acs raises ValueError when topic is empty")
        assert result["passed"] is True

    def test_canonical_class_defined_passes(self):
        result = validate_ac_structure("Class defined: bob3.research_strategies.SomeClass")
        assert result["passed"] is True

    def test_canonical_python_passes(self):
        result = validate_ac_structure("python: bob3.research_strategies")
        assert result["passed"] is True

    def test_prose_ac_fails(self):
        result = validate_ac_structure("The system should handle errors gracefully")
        assert result["passed"] is False
        assert len(result["non_canonical"]) == 1

    def test_enum_prose_fails(self):
        result = validate_ac_structure(
            "FailureClass enum: should classify failures AND classify_failure() != unknown"
        )
        assert result["passed"] is False

    def test_result_has_required_keys(self):
        result = validate_ac_structure("Function defined: bob3.foo")
        for key in ("passed", "reason", "non_canonical", "has_error_path"):
            assert key in result, f"Missing key: {key!r}"

    def test_reason_is_string(self):
        result = validate_ac_structure("pytest: tests/test_foo.py")
        assert isinstance(result["reason"], str)
        assert len(result["reason"]) > 0

    def test_has_error_path_true_for_error_ac(self):
        result = validate_ac_structure(
            "behavior: emit_canonical_acs raises ValueError when topic is invalid"
        )
        assert result["has_error_path"] is True

    def test_has_error_path_false_for_non_error_ac(self):
        result = validate_ac_structure("Function defined: bob3.research_strategies.emit_canonical_acs")
        assert result["has_error_path"] is False

    def test_non_canonical_contains_failing_ac(self):
        prose = "The feature should work correctly"
        result = validate_ac_structure(prose)
        assert prose in result["non_canonical"]

    def test_non_canonical_empty_when_passing(self):
        result = validate_ac_structure("File exists: src/bob3/research_strategies.py")
        assert result["non_canonical"] == []

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_ac_structure(42)  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_ac_structure(None)  # type: ignore[arg-type]

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_ac_structure("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_ac_structure("   \t\n")

    def test_behavior_without_when_fails(self):
        result = validate_ac_structure("behavior: something happens")
        assert result["passed"] is False


class TestEmitCanonicalAcsForms:
    def test_all_returned_acs_match_canonical_patterns(self):
        acs = emit_canonical_acs("path_finding_retry")
        for ac in acs:
            assert _is_canonical(ac), f"Non-canonical AC in output: {ac!r}"

    def test_at_least_one_error_path_ac(self):
        acs = emit_canonical_acs("schema_validator")
        has_error = any(
            any(kw in ac.lower() for kw in _ERROR_KEYWORDS)
            for ac in acs
        )
        assert has_error, f"No error-path AC in output: {acs}"

    def test_minimum_ac_count(self):
        acs = emit_canonical_acs("some_feature")
        assert len(acs) >= 2

    def test_all_acs_are_strings(self):
        acs = emit_canonical_acs("feature_topic")
        for ac in acs:
            assert isinstance(ac, str)

    def test_validate_structure_passes_for_all_emitted_acs(self):
        acs = emit_canonical_acs("test_feature")
        for ac in acs:
            result = validate_ac_structure(ac)
            assert result["passed"] is True, (
                f"validate_ac_structure rejected emitted AC {ac!r}: {result['reason']}"
            )

    def test_gate_passes_for_all_emitted_acs(self):
        acs = emit_canonical_acs("another_feature")
        gate_result = validate_against_spec_quality_gate(acs)
        assert gate_result["passed"] is True, (
            f"Gate rejected emitted ACs: {gate_result['non_canonical']}"
        )

    def test_different_topics_all_canonical(self):
        for topic in ("path_finding", "error_handler", "schema_gen", "retry_strategy"):
            acs = emit_canonical_acs(topic)
            for ac in acs:
                assert _is_canonical(ac), f"Non-canonical AC for topic {topic!r}: {ac!r}"

    def test_canonical_forms_all_recognised(self):
        """Each canonical prefix type must be recognised by validate_ac_structure."""
        canonical_samples = [
            "File exists: src/bob3/foo.py",
            "Function defined: bob3.foo.bar",
            "Class defined: bob3.foo.Baz",
            "pytest: tests/test_foo.py",
            "integration: bob3.gate_resynthesis",
            "behavior: foo raises ValueError when input is None",
            "python: bob3.research_strategies",
        ]
        for ac in canonical_samples:
            result = validate_ac_structure(ac)
            assert result["passed"] is True, (
                f"validate_ac_structure rejected canonical AC {ac!r}: {result['reason']}"
            )

    def test_prose_forms_all_rejected(self):
        """Prose-form ACs that previously caused gate failures MUST be rejected."""
        prose_samples = [
            "FailureClass enum: should classify failures AND classify_failure() != unknown",
            "The system should handle errors gracefully",
            "All functions return correct results",
            "Error messages are informative",
            "Retry logic is implemented",
        ]
        for ac in prose_samples:
            result = validate_ac_structure(ac)
            assert result["passed"] is False, (
                f"validate_ac_structure incorrectly accepted prose AC {ac!r}"
            )
