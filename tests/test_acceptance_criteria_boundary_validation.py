"""Boundary-validation tests for the seventh AC grammar.

Tests verify that boundary requirements are correctly detected and enforced
for ACs involving data transformation or numeric range concepts.
"""

from __future__ import annotations

import pytest

from bob3.acceptance_criteria import parse_property_ac, parse_key_example_ac
from bob3.spec_quality.example_grammar import (
    KeyExample,
    BoundaryRequirement,
    check_boundary_satisfied,
    requires_boundary,
    require_boundary_example,
    MissingBoundaryError,
    emit_hypothesis_test,
    emit_parametrize_test,
    parse_key_example,
)


class TestRequiresBoundaryDetection:
    def test_numeric_ac_requires_boundary(self):
        ac = "When a score is computed it must return a non-negative integer"
        result = requires_boundary(ac)
        assert result.required is True

    def test_transform_ac_requires_boundary(self):
        ac = "Function converts input values to normalized range"
        result = requires_boundary(ac)
        assert result.required is True

    def test_non_numeric_ac_does_not_require_boundary(self):
        ac = "When user logs in the session cookie is set"
        result = requires_boundary(ac)
        assert result.required is False

    def test_range_word_triggers_boundary_requirement(self):
        ac = "Result must be within the valid range"
        result = requires_boundary(ac)
        assert result.required is True

    def test_calculate_triggers_boundary_requirement(self):
        ac = "System shall calculate the total price"
        result = requires_boundary(ac)
        assert result.required is True

    def test_returns_boundary_requirement_dataclass(self):
        result = requires_boundary("AC with integer value")
        assert isinstance(result, BoundaryRequirement)
        assert hasattr(result, "required")
        assert hasattr(result, "has_boundary")
        assert hasattr(result, "reason")
        assert hasattr(result, "satisfied")

    def test_empty_ac_does_not_require_boundary(self):
        result = requires_boundary("")
        assert result.required is False

    def test_reason_is_non_empty_string(self):
        result = requires_boundary("AC with numeric range")
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0


class TestCheckBoundarySatisfied:
    def test_zero_example_satisfies_boundary(self):
        ac = "Compute integer score for input"
        examples = [KeyExample(given="0", then="0", raw="given: 0, then: 0")]
        result = check_boundary_satisfied(ac, examples)
        assert result.satisfied is True
        assert result.has_boundary is True

    def test_empty_string_example_satisfies_boundary(self):
        ac = "Transform input data to output format"
        examples = [KeyExample(given='""', then='""', raw='given: "", then: ""')]
        result = check_boundary_satisfied(ac, examples)
        assert result.has_boundary is True

    def test_negative_number_satisfies_boundary(self):
        ac = "Compute average of integer values"
        examples = [KeyExample(given="-1", then="-1", raw="given: -1, then: -1")]
        result = check_boundary_satisfied(ac, examples)
        assert result.has_boundary is True

    def test_no_examples_unsatisfied_for_numeric_ac(self):
        ac = "Calculate integer total from inputs"
        result = check_boundary_satisfied(ac, [])
        assert result.required is True
        assert result.has_boundary is False
        assert result.satisfied is False

    def test_non_boundary_examples_do_not_satisfy(self):
        ac = "Compute score from numeric input"
        examples = [KeyExample(given="42", then="42", raw="given: 42, then: 42")]
        result = check_boundary_satisfied(ac, examples)
        # 42 is not a boundary value
        assert result.has_boundary is False
        assert result.satisfied is False

    def test_non_numeric_ac_always_satisfied(self):
        ac = "User can log out of the system"
        examples = []
        result = check_boundary_satisfied(ac, examples)
        assert result.satisfied is True


class TestRequireBoundaryExampleEnforcement:
    def test_raises_missing_boundary_error_for_numeric_ac_without_boundary(self):
        ac = "Compute integer result from input range"
        with pytest.raises(MissingBoundaryError):
            require_boundary_example(ac, [])

    def test_missing_boundary_error_is_value_error(self):
        ac = "Calculate score from numeric range"
        with pytest.raises(ValueError):
            require_boundary_example(ac, [])

    def test_does_not_raise_when_boundary_satisfied(self):
        ac = "Compute integer result from input"
        examples = [KeyExample(given="0", then="0", raw="given: 0, then: 0")]
        require_boundary_example(ac, examples)  # must not raise

    def test_does_not_raise_for_non_numeric_ac(self):
        ac = "User logs in and session is created"
        require_boundary_example(ac, [])  # must not raise


class TestPropertyACBoundaryIntegration:
    def test_parse_property_ac_returns_none_on_empty(self):
        result = parse_property_ac("")
        assert result is None

    def test_parse_property_ac_returns_none_on_none(self):
        result = parse_property_ac(None)
        assert result is None

    def test_emit_hypothesis_test_with_zero_seed(self):
        from bob3.spec_quality.example_grammar import parse_property_ac as _parse
        ac = _parse("property: non_negative for st.integers() assert x >= 0")
        code = emit_hypothesis_test(ac, seed=0)
        assert "seed" in code or "@given" in code or "st.integers" in code

    def test_emit_parametrize_test_with_boundary_zero_example(self):
        examples = [KeyExample(given="0", then="0", raw="given: 0, then: 0")]
        code = emit_parametrize_test(examples, test_name="test_zero_boundary", seed=0)
        assert "0" in code
        assert "parametrize" in code or "pytest" in code


class TestKeyExampleACBoundaryValidation:
    def test_parse_key_example_ac_with_zero_given_value(self):
        result = parse_key_example_ac({"given": "0", "then": "0"})
        assert result is not None
        assert result.given == "0"

    def test_parse_key_example_ac_with_empty_string_given(self):
        result = parse_key_example_ac({"given": "", "then": "result"})
        assert result is not None
        assert result.given == ""

    def test_parse_key_example_ac_with_none_returns_none(self):
        result = parse_key_example_ac(None)
        assert result is None

    def test_parse_key_example_ac_with_empty_dict_returns_none(self):
        result = parse_key_example_ac({})
        assert result is None
