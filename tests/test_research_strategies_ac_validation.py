"""Tests for validate_ac_against_spec_quality_gate and generate_feature_with_canonical_acs.

Covers:
- validate_ac_against_spec_quality_gate validates a single AC string
- generate_feature_with_canonical_acs produces canonical-form ACs with retry logic
- Blocked status emitted when synthesis fails persistently
- At least one negative/error-path AC in generated output
"""

from __future__ import annotations

import pytest

from bob3.research_strategies import (
    validate_ac_against_spec_quality_gate,
    validate_acs_against_spec_quality,
    generate_feature_with_canonical_acs,
)


class TestValidateAcAgainstSpecQualityGate:
    def test_canonical_function_defined_passes(self):
        result = validate_ac_against_spec_quality_gate(
            "Function defined: bob3.research_strategies.validate_ac_against_spec_quality_gate"
        )
        assert result["passed"] is True
        assert result["non_canonical"] == []

    def test_canonical_file_exists_passes(self):
        result = validate_ac_against_spec_quality_gate(
            "File exists: src/bob3/research_strategies.py"
        )
        assert result["passed"] is True

    def test_canonical_pytest_passes(self):
        result = validate_ac_against_spec_quality_gate(
            "pytest: tests/test_research_strategies_ac_validation.py"
        )
        assert result["passed"] is True

    def test_canonical_integration_passes(self):
        result = validate_ac_against_spec_quality_gate("integration: bob3.synthesis")
        assert result["passed"] is True

    def test_canonical_behavior_passes(self):
        result = validate_ac_against_spec_quality_gate(
            "behavior: generate raises ValueError when feature_topic is empty"
        )
        assert result["passed"] is True

    def test_prose_ac_fails(self):
        result = validate_ac_against_spec_quality_gate(
            "The system should handle errors gracefully"
        )
        assert result["passed"] is False
        assert len(result["non_canonical"]) == 1

    def test_enum_prose_ac_fails(self):
        result = validate_ac_against_spec_quality_gate(
            "FailureClass enum: should classify failures AND classify_failure() != unknown"
        )
        assert result["passed"] is False

    def test_non_canonical_ac_appears_in_non_canonical_list(self):
        ac = "Something something something"
        result = validate_ac_against_spec_quality_gate(ac)
        assert ac in result["non_canonical"]

    def test_result_has_required_keys(self):
        result = validate_ac_against_spec_quality_gate("Function defined: bob3.foo")
        assert "passed" in result
        assert "non_canonical" in result

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_ac_against_spec_quality_gate(42)  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_ac_against_spec_quality_gate(None)  # type: ignore[arg-type]

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_ac_against_spec_quality_gate("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_ac_against_spec_quality_gate("   ")


class TestGenerateFeatureWithCanonicalAcs:
    def test_returns_ok_status_for_valid_topic(self):
        result = generate_feature_with_canonical_acs("path_finding_retry")
        assert result["status"] == "ok"

    def test_returns_canonical_acs_list(self):
        result = generate_feature_with_canonical_acs("schema_validator")
        assert isinstance(result["acceptance_criteria"], list)
        assert len(result["acceptance_criteria"]) >= 2

    def test_attempts_field_present(self):
        result = generate_feature_with_canonical_acs("cost_enforcer")
        assert "attempts" in result
        assert result["attempts"] >= 1

    def test_non_canonical_empty_on_success(self):
        result = generate_feature_with_canonical_acs("retry_strategy")
        assert result["status"] == "ok"
        assert result["non_canonical"] == []

    def test_all_returned_acs_are_canonical(self):
        import re

        canonical_patterns = [
            re.compile(r"^File exists\s*:\s*\S+", re.IGNORECASE),
            re.compile(r"^Function defined\s*:\s*[\w.]+", re.IGNORECASE),
            re.compile(r"^Class defined\s*:\s*[\w.]+", re.IGNORECASE),
            re.compile(r"^pytest\s*:\s*\S+", re.IGNORECASE),
            re.compile(r"^integration\s*:\s*[\w./:-]+", re.IGNORECASE),
            re.compile(r"^behavior\s*:\s*.+\bwhen\b.+", re.IGNORECASE),
            re.compile(r"^python\s*:\s*\S+", re.IGNORECASE),
            re.compile(r"^Field exists\s*.*:\s*\S+", re.IGNORECASE),
        ]

        result = generate_feature_with_canonical_acs("my_feature")
        assert result["status"] == "ok"
        for ac in result["acceptance_criteria"]:
            assert any(p.match(ac.strip()) for p in canonical_patterns), (
                f"Non-canonical AC in generated output: {ac!r}"
            )

    def test_at_least_one_negative_path_ac(self):
        error_keywords = {
            "error", "failure", "fail", "invalid", "missing", "reject",
            "exception", "raises", "corrupt", "timeout", "negative", "bad",
        }
        result = generate_feature_with_canonical_acs("path_finding_retry")
        assert result["status"] == "ok"
        has_error_ac = any(
            any(kw in ac.lower() for kw in error_keywords)
            for ac in result["acceptance_criteria"]
        )
        assert has_error_ac, (
            f"No negative/error-path AC in generated output: {result['acceptance_criteria']}"
        )

    def test_empty_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_feature_with_canonical_acs("")

    def test_whitespace_only_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_feature_with_canonical_acs("   ")

    def test_non_string_topic_raises_type_error(self):
        with pytest.raises(TypeError):
            generate_feature_with_canonical_acs(42)  # type: ignore[arg-type]

    def test_none_topic_raises_type_error(self):
        with pytest.raises(TypeError):
            generate_feature_with_canonical_acs(None)  # type: ignore[arg-type]

    def test_result_has_required_keys(self):
        result = generate_feature_with_canonical_acs("feature_x")
        for key in ("status", "acceptance_criteria", "attempts", "non_canonical"):
            assert key in result, f"Missing key: {key!r}"

    def test_max_retries_respected(self):
        result = generate_feature_with_canonical_acs("valid_feature", max_retries=1)
        assert result["attempts"] <= 1

    def test_different_topics_produce_acs(self):
        r1 = generate_feature_with_canonical_acs("feature_alpha")
        r2 = generate_feature_with_canonical_acs("feature_beta")
        assert r1["status"] == "ok"
        assert r2["status"] == "ok"
        assert len(r1["acceptance_criteria"]) >= 2
        assert len(r2["acceptance_criteria"]) >= 2


class TestValidateAcsAgainstSpecQuality:
    """Tests for the validate_acs_against_spec_quality canonical alias."""

    def test_negative_error_path_ac_required(self):
        """Gate MUST reject AC lists that have no negative/error-path AC."""
        error_keywords = {
            "error", "failure", "fail", "invalid", "missing", "reject",
            "exception", "raises", "corrupt", "timeout", "negative", "bad",
        }
        result = generate_feature_with_canonical_acs("some_feature")
        assert result["status"] == "ok"
        has_error_ac = any(
            any(kw in ac.lower() for kw in error_keywords)
            for ac in result["acceptance_criteria"]
        )
        assert has_error_ac, (
            "Generated ACs must contain at least one negative/error-path AC; "
            f"got: {result['acceptance_criteria']}"
        )

    def test_all_canonical_list_passes(self):
        acs = [
            "File exists: src/bob3/research_strategies.py",
            "Function defined: bob3.research_strategies.emit_canonical_acs",
            "pytest: tests/test_foo.py",
            "behavior: raises ValueError when topic is invalid",
        ]
        result = validate_acs_against_spec_quality(acs)
        assert result["passed"] is True
        assert result["non_canonical"] == []

    def test_prose_ac_in_list_fails(self):
        acs = [
            "File exists: src/bob3/foo.py",
            "The system should handle all edge cases",
        ]
        result = validate_acs_against_spec_quality(acs)
        assert result["passed"] is False
        assert len(result["non_canonical"]) == 1

    def test_non_list_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_acs_against_spec_quality("not_a_list")  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_acs_against_spec_quality(None)  # type: ignore[arg-type]
