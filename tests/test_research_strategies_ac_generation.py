"""Tests for the research_strategies canonical AC generation pipeline.

Covers:
- emit_canonical_acs produces canonical-form ACs
- validate_acs_against_spec_quality validates AC lists
- generate_feature_with_canonical_acs integrates generation + validation
- Retry logic and synthesis_blocked_invalid_acs sentinel
- At least one negative/error-path AC in generated output
"""

from __future__ import annotations

import pytest

from bob.research_strategies import (
    emit_canonical_acs,
    validate_acs_against_spec_quality,
    validate_against_spec_quality_gate,
    generate_feature_with_canonical_acs,
)


class TestEmitCanonicalAcs:
    def test_returns_list(self):
        acs = emit_canonical_acs("feature_x")
        assert isinstance(acs, list)

    def test_returns_at_least_two_acs(self):
        acs = emit_canonical_acs("feature_x")
        assert len(acs) >= 2

    def test_all_acs_are_strings(self):
        acs = emit_canonical_acs("feature_x")
        assert all(isinstance(ac, str) for ac in acs)

    def test_all_acs_are_canonical(self):
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
        acs = emit_canonical_acs("some_feature")
        for ac in acs:
            assert any(p.match(ac.strip()) for p in canonical_patterns), (
                f"Non-canonical AC emitted: {ac!r}"
            )

    def test_at_least_one_negative_ac(self):
        error_keywords = {
            "error", "failure", "fail", "invalid", "missing", "reject",
            "exception", "raises", "corrupt", "timeout", "negative", "bad",
        }
        acs = emit_canonical_acs("path_finding_retry")
        has_error = any(
            any(kw in ac.lower() for kw in error_keywords) for ac in acs
        )
        assert has_error, f"No negative/error-path AC found: {acs}"

    def test_empty_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_canonical_acs("")

    def test_whitespace_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_canonical_acs("   ")

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_canonical_acs(42)  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_canonical_acs(None)  # type: ignore[arg-type]


class TestValidateAcsAgainstSpecQuality:
    def test_valid_canonical_list_passes(self):
        acs = [
            "File exists: src/bob/research_strategies.py",
            "Function defined: bob.research_strategies.emit_canonical_acs",
            "behavior: raises ValueError when topic is empty",
        ]
        result = validate_acs_against_spec_quality(acs)
        assert result["passed"] is True
        assert result["non_canonical"] == []

    def test_prose_list_fails(self):
        acs = [
            "The system should work correctly",
            "All edge cases must be handled",
        ]
        result = validate_acs_against_spec_quality(acs)
        assert result["passed"] is False
        assert len(result["non_canonical"]) == 2

    def test_mixed_list_reports_only_non_canonical(self):
        canonical = "pytest: tests/test_foo.py"
        prose = "The module handles errors"
        result = validate_acs_against_spec_quality([canonical, prose])
        assert result["passed"] is False
        assert prose in result["non_canonical"]
        assert canonical not in result["non_canonical"]

    def test_empty_list_fails(self):
        result = validate_acs_against_spec_quality([])
        assert result["passed"] is False

    def test_result_has_passed_and_non_canonical_keys(self):
        result = validate_acs_against_spec_quality(["Function defined: bob.foo"])
        assert "passed" in result
        assert "non_canonical" in result

    def test_non_list_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_acs_against_spec_quality("not a list")  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_acs_against_spec_quality(None)  # type: ignore[arg-type]

    def test_list_with_non_string_raises_value_error(self):
        with pytest.raises((TypeError, ValueError)):
            validate_acs_against_spec_quality([42])  # type: ignore[arg-type]

    def test_alias_matches_validate_against_spec_quality_gate(self):
        acs = ["Function defined: bob.foo.bar", "pytest: tests/test_x.py"]
        r1 = validate_acs_against_spec_quality(acs)
        r2 = validate_against_spec_quality_gate(acs)
        assert r1 == r2


class TestGenerateFeatureWithCanonicalAcsIntegration:
    def test_successful_generation_returns_ok(self):
        result = generate_feature_with_canonical_acs("classifier_fix")
        assert result["status"] == "ok"

    def test_generates_canonical_acs_validated_by_gate(self):
        result = generate_feature_with_canonical_acs("retry_handler")
        assert result["status"] == "ok"
        gate_check = validate_acs_against_spec_quality(result["acceptance_criteria"])
        assert gate_check["passed"] is True

    def test_synthesis_never_writes_prose_acs(self):
        result = generate_feature_with_canonical_acs("feature_with_errors")
        assert result["status"] == "ok"
        assert result["non_canonical"] == [], (
            f"Prose ACs leaked into output: {result['non_canonical']}"
        )

    def test_negative_error_path_ac_always_present(self):
        error_keywords = {
            "error", "failure", "fail", "invalid", "missing", "reject",
            "exception", "raises", "corrupt", "timeout", "negative", "bad",
        }
        result = generate_feature_with_canonical_acs("any_feature_topic")
        assert result["status"] == "ok"
        has_error_ac = any(
            any(kw in ac.lower() for kw in error_keywords)
            for ac in result["acceptance_criteria"]
        )
        assert has_error_ac, (
            f"Generated feature lacks negative/error-path AC: {result['acceptance_criteria']}"
        )

    def test_persistent_failure_returns_synthesis_blocked_status(self, monkeypatch):
        """If generation always fails, status must be synthesis_blocked_invalid_acs."""
        import bob.research_strategies as rs
        monkeypatch.setattr(rs, "emit_canonical_acs", lambda topic: ["prose only no prefix"])
        result = generate_feature_with_canonical_acs("bad_topic", max_retries=2)
        assert result["status"] == "synthesis_blocked_invalid_acs"
        assert result["acceptance_criteria"] == []
        assert result["attempts"] == 2

    def test_blocked_status_skips_write_no_exception(self, monkeypatch):
        """synthesis_blocked_invalid_acs must not raise — silently block."""
        import bob.research_strategies as rs
        monkeypatch.setattr(rs, "emit_canonical_acs", lambda topic: ["bad prose ac"])
        result = generate_feature_with_canonical_acs("bad_topic", max_retries=1)
        assert result["status"] == "synthesis_blocked_invalid_acs"
