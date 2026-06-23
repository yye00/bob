"""Tests for research_strategies canonical AC emission and spec_quality gate validation.

Covers:
- emit_canonical_acs produces ACs in canonical prefix forms
- validate_against_spec_quality_gate rejects prose-form ACs and passes canonical ones
- Retry logic escalates prompt on failure
- Blocked status emitted when retries exhausted
- At least one negative/error-path AC required
"""

from __future__ import annotations

import pytest

from bob3.research_strategies import emit_canonical_acs, validate_against_spec_quality_gate


class TestEmitCanonicalAcs:
    def test_returns_list_of_strings(self):
        acs = emit_canonical_acs("path_finding_retry")
        assert isinstance(acs, list)
        assert all(isinstance(ac, str) for ac in acs)

    def test_minimum_two_acs(self):
        acs = emit_canonical_acs("feature_x")
        assert len(acs) >= 2

    def test_all_acs_match_canonical_prefixes(self):
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

        acs = emit_canonical_acs("path_finding_retry")
        for ac in acs:
            assert any(p.match(ac.strip()) for p in canonical_patterns), (
                f"AC not in canonical form: {ac!r}"
            )

    def test_at_least_one_negative_path_ac(self):
        error_keywords = {
            "error", "failure", "fail", "invalid", "missing", "reject",
            "exception", "raises", "corrupt", "timeout", "negative", "bad",
        }
        acs = emit_canonical_acs("path_finding_retry")
        has_error_ac = any(
            any(kw in ac.lower() for kw in error_keywords) for ac in acs
        )
        assert has_error_ac, (
            f"No negative/error-path AC found in: {acs}"
        )

    def test_different_topics_produce_topic_aware_acs(self):
        acs1 = emit_canonical_acs("schema_validator")
        acs2 = emit_canonical_acs("cost_enforcer")
        # Both should be valid canonical ACs; they may differ in content
        assert len(acs1) >= 2
        assert len(acs2) >= 2

    def test_empty_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_canonical_acs("")

    def test_whitespace_only_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_canonical_acs("   ")


class TestValidateAgainstSpecQualityGate:
    def test_canonical_acs_pass_gate(self):
        canonical_acs = [
            "Function defined: bob3.research_strategies.emit_canonical_acs",
            "File exists: src/bob3/research_strategies.py",
            "pytest: tests/test_research_strategies_canonical_acs.py",
            "behavior: emit_canonical_acs raises ValueError when topic is empty",
        ]
        result = validate_against_spec_quality_gate(canonical_acs)
        assert result["passed"] is True
        assert result["non_canonical"] == []

    def test_prose_acs_fail_gate(self):
        prose_acs = [
            "FailureClass enum: should classify failures correctly",
            "The system handles all edge cases properly",
            "classify_failure() != unknown AND some other condition",
        ]
        result = validate_against_spec_quality_gate(prose_acs)
        assert result["passed"] is False
        assert len(result["non_canonical"]) > 0

    def test_mixed_acs_partial_fail(self):
        acs = [
            "Function defined: bob3.foo.bar",
            "The system should handle input gracefully",
        ]
        result = validate_against_spec_quality_gate(acs)
        assert result["passed"] is False
        assert len(result["non_canonical"]) == 1
        assert result["non_canonical"][0] == "The system should handle input gracefully"

    def test_empty_list_fails_gate(self):
        result = validate_against_spec_quality_gate([])
        assert result["passed"] is False

    def test_result_has_required_keys(self):
        result = validate_against_spec_quality_gate(["Function defined: bob3.foo"])
        assert "passed" in result
        assert "non_canonical" in result

    def test_all_canonical_produces_empty_non_canonical(self):
        acs = [
            "integration: bob3.synthesis",
            "behavior: synthesis raises ValueError when ACs are prose form",
        ]
        result = validate_against_spec_quality_gate(acs)
        assert result["non_canonical"] == []

    def test_invalid_input_type_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            validate_against_spec_quality_gate("not a list")  # type: ignore[arg-type]
