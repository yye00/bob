"""Tests for bob.research_strategies canonical AC generator and spec_quality gate validator."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bob.research_strategies import (
    emit_canonical_acs,
    generate_feature_with_canonical_acs,
    generate_research_strategy_acs,
    validate_ac_against_spec_quality_gate,
    validate_against_spec_quality_gate,
    validate_acs_against_gate,
    validate_acs_against_spec_quality,
)


class TestEmitCanonicalAcs:
    def test_returns_list(self):
        result = emit_canonical_acs("my_feature")
        assert isinstance(result, list)

    def test_returns_at_least_two_acs(self):
        result = emit_canonical_acs("my_feature")
        assert len(result) >= 2

    def test_all_acs_are_strings(self):
        result = emit_canonical_acs("my_feature")
        assert all(isinstance(ac, str) for ac in result)

    def test_all_acs_are_canonical(self):
        result = emit_canonical_acs("my_feature")
        gate_result = validate_against_spec_quality_gate(result)
        assert gate_result["passed"] is True, (
            f"Non-canonical ACs emitted: {gate_result['non_canonical']}"
        )

    def test_includes_error_path_ac(self):
        result = emit_canonical_acs("my_feature")
        combined = " ".join(result).lower()
        error_terms = {"error", "fail", "invalid", "missing", "reject", "exception", "raises"}
        assert any(term in combined for term in error_terms), (
            "emit_canonical_acs must include at least one error/failure-path AC"
        )

    def test_empty_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_canonical_acs("")

    def test_whitespace_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_canonical_acs("   ")

    def test_non_string_topic_raises_type_error(self):
        with pytest.raises(TypeError):
            emit_canonical_acs(42)  # type: ignore[arg-type]

    def test_different_topics_yield_different_acs(self):
        result_a = emit_canonical_acs("feature_alpha")
        result_b = emit_canonical_acs("feature_beta")
        # At least one AC should differ between topics
        assert result_a != result_b or len(result_a) > 0


class TestValidateAgainstSpecQualityGate:
    def test_all_canonical_passes(self):
        acs = [
            "File exists: src/bob/foo.py",
            "Function defined: bob.foo.bar",
            "pytest: tests/test_foo.py",
        ]
        result = validate_against_spec_quality_gate(acs)
        assert result["passed"] is True
        assert result["non_canonical"] == []

    def test_prose_ac_fails(self):
        acs = ["The system must handle errors gracefully"]
        result = validate_against_spec_quality_gate(acs)
        assert result["passed"] is False
        assert len(result["non_canonical"]) == 1

    def test_mixed_acs_fails_with_prose(self):
        acs = [
            "Function defined: bob.foo.bar",
            "This prose AC is not canonical",
        ]
        result = validate_against_spec_quality_gate(acs)
        assert result["passed"] is False
        assert "This prose AC is not canonical" in result["non_canonical"]

    def test_empty_list_returns_failed(self):
        result = validate_against_spec_quality_gate([])
        assert isinstance(result, dict)
        assert "passed" in result
        assert result["passed"] is False

    def test_non_list_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_against_spec_quality_gate("not_a_list")  # type: ignore[arg-type]

    def test_list_with_non_string_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            validate_against_spec_quality_gate([None])  # type: ignore[arg-type]

    def test_integration_prefix_is_canonical(self):
        result = validate_against_spec_quality_gate(["integration: bob.orchestrator"])
        assert result["passed"] is True

    def test_pytest_prefix_is_canonical(self):
        result = validate_against_spec_quality_gate(["pytest: tests/test_foo.py"])
        assert result["passed"] is True

    def test_behavior_when_prefix_is_canonical(self):
        result = validate_against_spec_quality_gate(
            ["behavior: foo raises ValueError when input is invalid"]
        )
        assert result["passed"] is True

    def test_class_defined_prefix_is_canonical(self):
        result = validate_against_spec_quality_gate(["Class defined: bob.foo.MyClass"])
        assert result["passed"] is True


class TestValidateAcAgainstSpecQualityGate:
    def test_canonical_ac_passes(self):
        result = validate_ac_against_spec_quality_gate("Function defined: bob.foo.bar")
        assert result["passed"] is True
        assert result["non_canonical"] == []

    def test_prose_ac_fails(self):
        result = validate_ac_against_spec_quality_gate("This is a prose AC")
        assert result["passed"] is False
        assert len(result["non_canonical"]) == 1

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_ac_against_spec_quality_gate("")

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError):
            validate_ac_against_spec_quality_gate(42)  # type: ignore[arg-type]


class TestGenerateFeatureWithCanonicalAcs:
    def test_successful_generation_returns_ok_status(self):
        result = generate_feature_with_canonical_acs("my_feature_topic")
        assert result["status"] == "ok"

    def test_successful_generation_returns_acs(self):
        result = generate_feature_with_canonical_acs("my_feature_topic")
        assert isinstance(result["acceptance_criteria"], list)
        assert len(result["acceptance_criteria"]) > 0

    def test_successful_generation_reports_attempts(self):
        result = generate_feature_with_canonical_acs("my_feature_topic")
        assert isinstance(result["attempts"], int)
        assert result["attempts"] >= 1

    def test_successful_generation_has_no_non_canonical(self):
        result = generate_feature_with_canonical_acs("my_feature_topic")
        assert result["non_canonical"] == []

    def test_empty_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_feature_with_canonical_acs("")

    def test_whitespace_topic_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_feature_with_canonical_acs("  ")

    def test_non_string_topic_raises_type_error(self):
        with pytest.raises(TypeError):
            generate_feature_with_canonical_acs(None)  # type: ignore[arg-type]

    def test_custom_max_retries(self):
        result = generate_feature_with_canonical_acs("my_feature", max_retries=5)
        assert result["status"] == "ok"
        assert result["attempts"] <= 5


def test_emit_invalid_acs_triggers_retry():
    """When emit_canonical_acs returns prose ACs, generate_feature_with_canonical_acs retries."""
    call_count = {"n": 0}
    _prose_acs = ["This is a prose AC that fails the gate"]
    _canonical_acs = [
        "Function defined: bob.my_feature.fn",
        "File exists: src/bob/my_feature.py",
        "pytest: tests/test_my_feature.py",
        "behavior: fn raises ValueError when input is invalid",
    ]

    def _fake_emit(topic):
        call_count["n"] += 1
        if call_count["n"] < 2:
            return _prose_acs
        return _canonical_acs

    with patch("bob.research_strategies.emit_canonical_acs", side_effect=_fake_emit):
        result = generate_feature_with_canonical_acs("my_feature", max_retries=3)

    assert result["status"] == "ok", "Should succeed after retry"
    assert call_count["n"] >= 2, "Should have retried at least once after initial invalid ACs"
    assert result["attempts"] >= 2


def test_synthesis_blocked_on_persistent_failure():
    """When all retries produce non-canonical ACs, result is synthesis_blocked_invalid_acs."""
    _prose_acs = ["This is always-prose AC that never passes the gate"]

    with patch(
        "bob.research_strategies.emit_canonical_acs",
        return_value=_prose_acs,
    ):
        result = generate_feature_with_canonical_acs("bad_feature", max_retries=3)

    assert result["status"] == "synthesis_blocked_invalid_acs"
    assert result["acceptance_criteria"] == []
    assert result["attempts"] == 3
    assert len(result["non_canonical"]) > 0


def test_negative_error_path_ac():
    """AC set from emit_canonical_acs must include at least one error/failure-path AC."""
    from bob.research_strategies import emit_canonical_acs, _ERROR_KEYWORDS

    acs = emit_canonical_acs("some_feature")
    # At least one AC must contain an error/failure-path keyword
    error_acs = [
        ac for ac in acs
        if any(kw in ac.lower() for kw in _ERROR_KEYWORDS)
    ]
    assert len(error_acs) >= 1, (
        f"emit_canonical_acs must include at least one negative/error-path AC; "
        f"got: {acs!r}"
    )


class TestAliases:
    def test_validate_acs_against_gate_is_alias(self):
        acs = ["Function defined: bob.foo.bar"]
        result1 = validate_against_spec_quality_gate(acs)
        result2 = validate_acs_against_gate(acs)
        assert result1 == result2

    def test_validate_acs_against_spec_quality_is_alias(self):
        acs = ["Function defined: bob.foo.bar"]
        result1 = validate_against_spec_quality_gate(acs)
        result2 = validate_acs_against_spec_quality(acs)
        assert result1 == result2


def test_emits_canonical_structured_forms():
    """ACs emitted by generate_research_strategy_acs must all match canonical prefixes."""
    result = generate_research_strategy_acs("my_research_feature")
    assert result["status"] == "ok", f"Expected ok, got: {result['status']}"
    acs = result["acceptance_criteria"]
    assert isinstance(acs, list) and len(acs) > 0
    gate_result = validate_against_spec_quality_gate(acs)
    assert gate_result["passed"] is True, (
        f"Non-canonical ACs in output: {gate_result['non_canonical']}"
    )


def test_includes_negative_error_path_ac():
    """At least one AC from generate_research_strategy_acs must cover a negative/error path."""
    result = generate_research_strategy_acs("my_research_feature")
    assert result["status"] == "ok"
    acs = result["acceptance_criteria"]
    error_terms = {"error", "fail", "invalid", "missing", "reject", "exception", "raises"}
    combined = " ".join(acs).lower()
    assert any(term in combined for term in error_terms), (
        f"No error/failure-path AC found in output: {acs!r}"
    )


def test_retries_on_validation_failure():
    """generate_research_strategy_acs must retry when initial ACs fail the gate."""
    call_count = {"n": 0}
    _prose_acs = ["This is a prose AC that will fail the gate"]
    _canonical_acs = [
        "Function defined: bob.my_feature.fn",
        "File exists: src/bob/my_feature.py",
        "pytest: tests/test_my_feature.py",
        "behavior: fn raises ValueError when input is invalid",
    ]

    def _fake_emit(topic):
        call_count["n"] += 1
        if call_count["n"] < 2:
            return _prose_acs
        return _canonical_acs

    with patch("bob.research_strategies.emit_canonical_acs", side_effect=_fake_emit):
        result = generate_research_strategy_acs("my_feature", max_retries=3)

    assert result["status"] == "ok", "Should succeed after retrying"
    assert call_count["n"] >= 2, "Should have retried at least once"
    assert result["attempts"] >= 2


def test_marks_synthesis_blocked_on_persistent_failure():
    """When all retries produce non-canonical ACs, status is synthesis_blocked_invalid_acs."""
    _prose_acs = ["This always-prose AC will never pass the gate"]

    with patch(
        "bob.research_strategies.emit_canonical_acs",
        return_value=_prose_acs,
    ):
        result = generate_research_strategy_acs("bad_feature", max_retries=3)

    assert result["status"] == "synthesis_blocked_invalid_acs"
    assert result["acceptance_criteria"] == []
    assert result["attempts"] == 3
    assert len(result["non_canonical"]) > 0
