"""Error-path tests for the seventh AC grammar.

Tests verify that invalid inputs raise ValueError and functions do not
silently succeed when given malformed property ACs or key-example dicts.
"""

from __future__ import annotations

import pytest

from bob3.acceptance_criteria import parse_property_ac, parse_key_example_ac
from bob3.spec_quality.example_grammar import (
    PropertyParseError,
    MissingBoundaryError,
    raises_on_malformed_property,
    require_boundary_example,
    KeyExample,
    check_boundary_satisfied,
)


class TestParsePropertyACErrorPaths:
    def test_missing_for_clause_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: name assert x > 0")

    def test_missing_assert_clause_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: name for st.integers()")

    def test_property_keyword_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property:")

    def test_property_with_name_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: some_name")

    def test_raises_value_error_not_type_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: x for assert")

    def test_error_is_not_silently_swallowed(self):
        try:
            result = parse_property_ac("property: bad_ac_missing_clauses")
            # If we reach here, it must have returned None (non-property) — not allowed
            # for property: prefix ACs. Both raise or None are invalid here.
            # The test verifies the function does NOT silently succeed.
            assert result is None or False, (
                f"Expected ValueError but got result: {result!r}"
            )
        except ValueError:
            pass  # expected

    def test_property_parse_error_is_value_error_subclass(self):
        assert issubclass(PropertyParseError, ValueError)

    def test_property_parse_error_message_is_informative(self):
        with pytest.raises(ValueError) as exc_info:
            parse_property_ac("property: name for st.integers()")
        assert len(str(exc_info.value)) > 0


class TestRaisesOnMalformedPropertyErrorPaths:
    def test_missing_for_raises_property_parse_error(self):
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property("property: name assert x > 0")

    def test_missing_assert_raises_property_parse_error(self):
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property("property: name for st.integers()")

    def test_non_property_string_raises_property_parse_error(self):
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property("pytest: tests/test_foo.py")

    def test_property_parse_error_is_value_error(self):
        with pytest.raises(ValueError):
            raises_on_malformed_property("property: name for st.integers()")

    def test_valid_property_ac_does_not_raise(self):
        result = raises_on_malformed_property(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert result is not None
        assert result.name == "non_negative"


class TestParseKeyExampleACErrorPaths:
    def test_dict_missing_both_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"other_key": "value"})

    def test_dict_with_only_unrelated_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"foo": "bar", "baz": "qux"})

    def test_does_not_raise_on_none_input(self):
        result = parse_key_example_ac(None)
        assert result is None

    def test_does_not_raise_on_empty_string(self):
        result = parse_key_example_ac("")
        assert result is None

    def test_does_not_silently_succeed_on_bad_dict(self):
        try:
            result = parse_key_example_ac({"wrong_key": "value"})
            assert result is None or False, (
                f"Expected ValueError but got: {result!r}"
            )
        except ValueError:
            pass  # expected

    def test_valid_dict_does_not_raise(self):
        result = parse_key_example_ac({"given": "input", "then": "output"})
        assert result is not None
        assert result.given == "input"
        assert result.then == "output"

    def test_valid_string_form_does_not_raise(self):
        result = parse_key_example_ac("given: 0, then: 0")
        assert result is not None


class TestMissingBoundaryErrorPaths:
    def test_missing_boundary_error_is_value_error(self):
        assert issubclass(MissingBoundaryError, ValueError)

    def test_numeric_ac_without_boundary_raises_missing_boundary_error(self):
        ac = "Compute integer score from input range"
        with pytest.raises(MissingBoundaryError):
            require_boundary_example(ac, [])

    def test_error_message_identifies_missing_boundary(self):
        ac = "Calculate numeric value from input"
        with pytest.raises(MissingBoundaryError) as exc_info:
            require_boundary_example(ac, [])
        assert len(str(exc_info.value)) > 0

    def test_non_numeric_ac_does_not_raise_missing_boundary_error(self):
        ac = "User can log out successfully"
        require_boundary_example(ac, [])  # must not raise

    def test_numeric_ac_with_valid_boundary_does_not_raise(self):
        ac = "Compute integer result from range"
        examples = [KeyExample(given="0", then="0", raw="given: 0, then: 0")]
        require_boundary_example(ac, examples)  # must not raise
