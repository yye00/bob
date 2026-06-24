"""Tests for bob.spec_synthesis.validate_boundary_examples — boundary requirement validation."""

from __future__ import annotations

import pytest

from bob.spec_synthesis import validate_boundary_examples
from bob.spec_quality.example_grammar import BoundaryRequirement, KeyExample


class TestValidateBoundaryExamplesReturnType:
    def test_returns_boundary_requirement(self):
        result = validate_boundary_examples("system logs event", [])
        assert isinstance(result, BoundaryRequirement)

    def test_has_required_attribute(self):
        result = validate_boundary_examples("system logs event", [])
        assert hasattr(result, "required")

    def test_has_has_boundary_attribute(self):
        result = validate_boundary_examples("system logs event", [])
        assert hasattr(result, "has_boundary")

    def test_has_satisfied_property(self):
        result = validate_boundary_examples("system logs event", [])
        assert hasattr(result, "satisfied")


class TestValidateBoundaryExamplesNonNumericAC:
    def test_non_numeric_ac_not_required(self):
        result = validate_boundary_examples("system logs authentication event", [])
        assert result.required is False

    def test_non_numeric_ac_satisfied_with_empty_examples(self):
        result = validate_boundary_examples("system logs authentication event", [])
        assert result.satisfied is True

    def test_non_numeric_ac_satisfied_with_examples(self):
        examples = [KeyExample(given="event=login", then="logged=True", raw="given: event=login, then: logged=True")]
        result = validate_boundary_examples("system logs authentication event", examples)
        assert result.satisfied is True

    def test_non_numeric_ac_has_no_boundary_required(self):
        result = validate_boundary_examples("user submits valid form", [])
        assert result.required is False


class TestValidateBoundaryExamplesNumericAC:
    def test_numeric_ac_requires_boundary(self):
        result = validate_boundary_examples(
            "system transforms integer value to output range 0-100", []
        )
        assert result.required is True

    def test_numeric_ac_without_boundary_not_satisfied(self):
        examples = [KeyExample(given="x=5", then="25", raw="given: x=5, then: 25")]
        result = validate_boundary_examples(
            "system transforms integer value to output range 0-100", examples
        )
        assert result.satisfied is False

    def test_numeric_ac_with_zero_boundary_satisfied(self):
        examples = [KeyExample(given="0", then="0", raw="given: 0, then: 0")]
        result = validate_boundary_examples(
            "system transforms integer value to output range 0-100", examples
        )
        assert result.satisfied is True

    def test_range_ac_requires_boundary(self):
        result = validate_boundary_examples("value must be in range 0 to 255", [])
        assert result.required is True

    def test_transform_ac_requires_boundary(self):
        result = validate_boundary_examples("system converts input to normalized form", [])
        assert result.required is True

    def test_zero_keyword_ac_requires_boundary(self):
        result = validate_boundary_examples("system returns zero when input is empty", [])
        assert result.required is True


class TestValidateBoundaryExamplesBoundaryDetection:
    def test_negative_number_example_satisfies_boundary(self):
        examples = [KeyExample(given="-1", then="error", raw="given: -1, then: error")]
        result = validate_boundary_examples(
            "system computes score from integer input", examples
        )
        assert result.satisfied is True

    def test_empty_string_example_satisfies_boundary(self):
        examples = [KeyExample(given="empty", then="0", raw="given: empty, then: 0")]
        result = validate_boundary_examples(
            "system counts integers in a range", examples
        )
        assert result.satisfied is True

    def test_max_keyword_example_satisfies_boundary(self):
        examples = [KeyExample(given="max", then="100", raw="given: max, then: 100")]
        result = validate_boundary_examples(
            "system converts numeric value", examples
        )
        assert result.satisfied is True

    def test_min_keyword_example_satisfies_boundary(self):
        examples = [KeyExample(given="min", then="0", raw="given: min, then: 0")]
        result = validate_boundary_examples(
            "system applies threshold to numeric range", examples
        )
        assert result.satisfied is True


class TestValidateBoundaryExamplesErrorHandling:
    def test_non_string_ac_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_boundary_examples(123, [])

    def test_none_ac_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_boundary_examples(None, [])

    def test_list_ac_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_boundary_examples(["system", "converts"], [])

    def test_empty_string_ac_returns_not_required(self):
        result = validate_boundary_examples("", [])
        assert result.required is False
        assert result.satisfied is True
