"""Tests for boundary-example requirement enforcement.

Verifies:
- requires_boundary detects ACs involving numeric range / data transformation.
- Non-numeric, non-transforming ACs do not require boundary examples.
- check_boundary_satisfied correctly evaluates whether examples satisfy the requirement.
- BoundaryRequirement.satisfied property works correctly.
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.example_grammar import (
    BoundaryRequirement,
    KeyExample,
    check_boundary_satisfied,
    parse_key_example,
    requires_boundary,
)


def _ex(given: str, then: str) -> KeyExample:
    return KeyExample(given=given, then=then, raw=f"given: {given}, then: {then}")


# ---------------------------------------------------------------------------
# requires_boundary — detection logic
# ---------------------------------------------------------------------------


class TestRequiresBoundary:
    def test_numeric_range_ac_requires_boundary(self):
        ac = "Function defined: transform_value returns an integer in valid range"
        result = requires_boundary(ac)
        assert isinstance(result, BoundaryRequirement)
        assert result.required is True

    def test_data_transform_ac_requires_boundary(self):
        ac = "behavior: encoder transforms binary data when input is given"
        result = requires_boundary(ac)
        assert result.required is True

    def test_compute_keyword_requires_boundary(self):
        ac = "Function defined: compute_score calculates average score"
        result = requires_boundary(ac)
        assert result.required is True

    def test_simple_file_exists_no_boundary(self):
        ac = "File exists: src/bob3/spec_quality/example_grammar.py"
        result = requires_boundary(ac)
        assert result.required is False

    def test_pytest_criterion_no_boundary(self):
        ac = "pytest: tests/test_foo.py"
        result = requires_boundary(ac)
        assert result.required is False

    def test_integration_criterion_no_boundary(self):
        ac = "integration: bob3.spec_quality.ears_parser"
        result = requires_boundary(ac)
        assert result.required is False

    def test_reason_is_nonempty(self):
        result = requires_boundary("function computes integer sum")
        assert result.reason != ""

    def test_has_boundary_defaults_false(self):
        result = requires_boundary("compute the integer value")
        assert result.has_boundary is False

    def test_ac_preserved_in_result(self):
        ac = "compute the integer value"
        result = requires_boundary(ac)
        assert result.ac == ac

    def test_float_keyword_requires_boundary(self):
        result = requires_boundary("calculates a float result for numeric input")
        assert result.required is True

    def test_zero_keyword_requires_boundary(self):
        result = requires_boundary("should not accept zero as valid input")
        assert result.required is True

    def test_normalize_keyword_requires_boundary(self):
        result = requires_boundary("normalize the data before processing")
        assert result.required is True

    def test_positive_keyword_requires_boundary(self):
        result = requires_boundary("returns positive values only")
        assert result.required is True


# ---------------------------------------------------------------------------
# check_boundary_satisfied
# ---------------------------------------------------------------------------


class TestCheckBoundarySatisfied:
    def test_satisfied_when_zero_example_present(self):
        ac = "compute the integer sum of values"
        examples = [_ex("x=0", "result=0"), _ex("x=5", "result=5")]
        result = check_boundary_satisfied(ac, examples)
        assert result.required is True
        assert result.has_boundary is True
        assert result.satisfied is True

    def test_satisfied_when_negative_example_present(self):
        ac = "transform the numeric value"
        examples = [_ex("x=-1", "error"), _ex("x=5", "ok")]
        result = check_boundary_satisfied(ac, examples)
        assert result.has_boundary is True

    def test_not_satisfied_when_no_boundary_example(self):
        ac = "compute the integer sum"
        examples = [_ex("x=5", "result=5"), _ex("x=10", "result=10")]
        result = check_boundary_satisfied(ac, examples)
        assert result.required is True
        assert result.has_boundary is False
        assert result.satisfied is False

    def test_not_required_gives_satisfied_with_no_examples(self):
        ac = "pytest: tests/test_foo.py"
        result = check_boundary_satisfied(ac, [])
        assert result.required is False
        assert result.satisfied is True

    def test_empty_example_string_counts_as_boundary(self):
        ac = "convert the numeric string"
        examples = [_ex('""', "empty_result")]
        result = check_boundary_satisfied(ac, examples)
        assert result.has_boundary is True

    def test_null_example_counts_as_boundary(self):
        ac = "transform numeric input"
        examples = [_ex("None", "null_result")]
        result = check_boundary_satisfied(ac, examples)
        assert result.has_boundary is True

    def test_max_keyword_in_example_counts_as_boundary(self):
        ac = "compute the maximum integer value"
        examples = [_ex("x=max_int", "result=overflow")]
        result = check_boundary_satisfied(ac, examples)
        assert result.has_boundary is True

    def test_large_number_counts_as_boundary(self):
        ac = "calculate the integer result"
        examples = [_ex("x=999999", "result=big")]
        result = check_boundary_satisfied(ac, examples)
        assert result.has_boundary is True


# ---------------------------------------------------------------------------
# BoundaryRequirement.satisfied property
# ---------------------------------------------------------------------------


class TestBoundaryRequirementSatisfied:
    def test_not_required_always_satisfied(self):
        br = BoundaryRequirement(
            ac="pytest: tests/foo.py",
            required=False,
            has_boundary=False,
            reason="not needed",
        )
        assert br.satisfied is True

    def test_required_and_has_boundary_satisfied(self):
        br = BoundaryRequirement(
            ac="compute integer",
            required=True,
            has_boundary=True,
            reason="needed",
        )
        assert br.satisfied is True

    def test_required_and_no_boundary_not_satisfied(self):
        br = BoundaryRequirement(
            ac="compute integer",
            required=True,
            has_boundary=False,
            reason="needed",
        )
        assert br.satisfied is False
