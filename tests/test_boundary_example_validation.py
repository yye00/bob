"""Tests for boundary example validation.

Verifies that:
- ``requires_boundary`` identifies ACs that need boundary key-examples.
- ``check_boundary_satisfied`` correctly reports whether boundary examples are present.
- ``require_boundary_example`` raises ``MissingBoundaryError`` when required examples
  are absent.
- Integration via ``key_examples_property_based_ac_variant`` propagates
  ``boundary_required`` and ``boundary_satisfied`` correctly.
"""

from __future__ import annotations

import pytest

from bob.acceptance_criteria.key_example import (
    KeyExample,
    check_boundary_requirement,
    extract_key_examples,
)
from bob.key_examples_property_based_ac_variant import key_examples_property_based_ac_variant
from bob.spec_quality.example_grammar import (
    BoundaryRequirement,
    MissingBoundaryError,
    check_boundary_satisfied,
    require_boundary_example,
    requires_boundary,
)


# ---------------------------------------------------------------------------
# requires_boundary — detection
# ---------------------------------------------------------------------------


class TestRequiresBoundary:
    def test_numeric_ac_requires_boundary(self):
        req = requires_boundary("system converts integer value to result")
        assert req.required is True

    def test_range_keyword_triggers_boundary(self):
        req = requires_boundary("value must be in range 0-100")
        assert req.required is True

    def test_transform_keyword_triggers_boundary(self):
        req = requires_boundary("system transforms input data")
        assert req.required is True

    def test_non_numeric_ac_does_not_require(self):
        req = requires_boundary("system logs an authentication event")
        assert req.required is False

    def test_returns_boundary_requirement_instance(self):
        req = requires_boundary("converts an integer")
        assert isinstance(req, BoundaryRequirement)

    def test_reason_is_non_empty_string(self):
        req = requires_boundary("converts an integer")
        assert isinstance(req.reason, str)
        assert len(req.reason) > 0

    def test_count_keyword_triggers_boundary(self):
        req = requires_boundary("system returns the count of items")
        assert req.required is True

    def test_score_keyword_triggers_boundary(self):
        req = requires_boundary("output score must not exceed threshold")
        assert req.required is True


# ---------------------------------------------------------------------------
# check_boundary_satisfied — with example list
# ---------------------------------------------------------------------------


class TestCheckBoundarySatisfied:
    def _make_example(self, given: str, then: str) -> KeyExample:
        return KeyExample(given=given, then=then, raw=f"given: {given}, then: {then}")

    def test_numeric_ac_not_satisfied_without_examples(self):
        req = check_boundary_satisfied("converts integer range value", [])
        assert req.satisfied is False

    def test_numeric_ac_satisfied_with_zero_example(self):
        req = check_boundary_satisfied(
            "converts integer range value",
            [self._make_example("0", "0")],
        )
        assert req.satisfied is True

    def test_numeric_ac_satisfied_with_negative_example(self):
        req = check_boundary_satisfied(
            "converts integer value",
            [self._make_example("-1", "error")],
        )
        assert req.satisfied is True

    def test_numeric_ac_satisfied_with_empty_string_example(self):
        req = check_boundary_satisfied(
            "transforms input value",
            [self._make_example("", "empty")],
        )
        assert req.satisfied is True

    def test_non_numeric_ac_always_satisfied(self):
        req = check_boundary_satisfied("logs authentication event", [])
        assert req.satisfied is True

    def test_non_numeric_ac_required_is_false(self):
        req = check_boundary_satisfied("logs authentication event", [])
        assert req.required is False


# ---------------------------------------------------------------------------
# require_boundary_example — enforcement
# ---------------------------------------------------------------------------


class TestRequireBoundaryExample:
    def _make_example(self, given: str, then: str) -> KeyExample:
        return KeyExample(given=given, then=then, raw=f"given: {given}, then: {then}")

    def test_numeric_ac_without_boundary_raises_missing_boundary_error(self):
        examples = [self._make_example("5", "25")]
        with pytest.raises(MissingBoundaryError):
            require_boundary_example("converts integer value in range", examples)

    def test_missing_boundary_error_is_value_error(self):
        examples = [self._make_example("5", "25")]
        with pytest.raises(ValueError):
            require_boundary_example("converts integer value in range", examples)

    def test_non_numeric_ac_does_not_raise(self):
        require_boundary_example("logs authentication event", [])

    def test_numeric_ac_with_zero_example_does_not_raise(self):
        examples = [self._make_example("0", "0")]
        require_boundary_example("converts integer value", examples)

    def test_numeric_ac_with_negative_example_does_not_raise(self):
        examples = [self._make_example("-10", "error")]
        require_boundary_example("converts integer value", examples)

    def test_numeric_ac_with_empty_examples_list_raises(self):
        with pytest.raises(MissingBoundaryError):
            require_boundary_example("transforms integer range value", [])


# ---------------------------------------------------------------------------
# Integration via key_examples_property_based_ac_variant
# ---------------------------------------------------------------------------


class TestIntegrationBoundaryValidation:
    def test_boundary_required_true_for_numeric_ac(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
            behavior_ac="system converts integer value to range",
        )
        assert result["boundary_required"] is True

    def test_boundary_required_false_for_non_numeric_ac(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
            behavior_ac="system logs an event to the audit trail",
        )
        assert result["boundary_required"] is False

    def test_boundary_not_satisfied_without_examples(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
            behavior_ac="system converts integer value in range",
        )
        assert result["boundary_satisfied"] is False

    def test_boundary_satisfied_with_zero_example(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "0", "then": "0"}],
            behavior_ac="system converts integer value in range",
        )
        assert result["boundary_satisfied"] is True

    def test_no_behavior_ac_always_satisfied(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
        )
        assert result["boundary_required"] is False
        assert result["boundary_satisfied"] is True

    def test_check_boundary_requirement_wrapper(self):
        result = check_boundary_requirement(
            "converts integer range value",
            [KeyExample(given="0", then="0", raw="given: 0, then: 0")],
        )
        assert result is True
