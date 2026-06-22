"""Error-path tests for key-examples / property-based AC variant.

AC: invalid input raises ValueError and the function does not silently succeed
(error path).

Tests verify that malformed property ACs and invalid key-example dicts raise
ValueError rather than silently returning incorrect results or None.
"""

from __future__ import annotations

import pytest

from ac_grammar.property_based import parse_key_example_ac, parse_property_ac
from bob3.spec_quality.example_grammar import (
    MissingBoundaryError,
    PropertyParseError,
    require_boundary_example,
    raises_on_malformed_property,
)


# ---------------------------------------------------------------------------
# parse_property_ac — error paths (via ac_grammar.property_based)
# ---------------------------------------------------------------------------


class TestParsePropertyACErrorPath:
    def test_missing_for_clause_raises_value_error(self):
        with pytest.raises(ValueError, match="for"):
            parse_property_ac("property: non_negative assert x >= 0")

    def test_missing_assert_clause_raises_value_error(self):
        with pytest.raises(ValueError, match="assert"):
            parse_property_ac("property: non_negative for st.integers()")

    def test_property_keyword_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property:")

    def test_property_with_name_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: some_name")

    def test_property_missing_predicate_text_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: p for st.integers() assert")

    def test_raises_value_error_not_other_exception(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: x for assert y")


# ---------------------------------------------------------------------------
# parse_key_example_ac — error paths (via ac_grammar.property_based)
# ---------------------------------------------------------------------------


class TestParseKeyExampleACErrorPath:
    def test_dict_missing_both_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"wrong_key": "x", "another_wrong": "y"})

    def test_dict_with_only_unrelated_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"foo": "bar", "baz": "qux"})

    def test_does_not_raise_on_none(self):
        result = parse_key_example_ac(None)
        assert result is None

    def test_does_not_raise_on_empty_string(self):
        result = parse_key_example_ac("")
        assert result is None

    def test_does_not_silently_succeed_on_bad_dict(self):
        with pytest.raises(ValueError):
            result = parse_key_example_ac({"not_given": "x", "not_then": "y"})
            # Must have raised before reaching here
            pytest.fail(f"Expected ValueError, got {result!r}")


# ---------------------------------------------------------------------------
# raises_on_malformed_property — error paths (spec_quality.example_grammar)
# ---------------------------------------------------------------------------


class TestRaisesOnMalformedProperty:
    def test_missing_for_raises_property_parse_error(self):
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property("property: p assert x > 0")

    def test_missing_assert_raises_property_parse_error(self):
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property("property: p for st.integers()")

    def test_non_property_string_raises_property_parse_error(self):
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property("pytest: tests/test_foo.py")

    def test_valid_property_ac_does_not_raise(self):
        result = raises_on_malformed_property(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert result is not None
        assert result.name == "non_negative"

    def test_property_parse_error_is_value_error(self):
        with pytest.raises(ValueError):
            raises_on_malformed_property("property: p assert x > 0")


# ---------------------------------------------------------------------------
# require_boundary_example — error paths
# ---------------------------------------------------------------------------


class TestRequireBoundaryExampleErrorPath:
    def test_numeric_ac_without_boundary_examples_raises(self):
        from bob3.spec_quality.example_grammar import KeyExample
        examples = [KeyExample(given="x=5", then="25", raw="given: x=5, then: 25")]
        with pytest.raises(MissingBoundaryError):
            require_boundary_example(
                "system transforms integer value to output range 0-100",
                examples,
            )

    def test_missing_boundary_error_is_value_error(self):
        from bob3.spec_quality.example_grammar import KeyExample
        examples = [KeyExample(given="x=5", then="25", raw="given: x=5, then: 25")]
        with pytest.raises(ValueError):
            require_boundary_example(
                "system transforms integer value to output range 0-100",
                examples,
            )

    def test_non_numeric_ac_does_not_raise(self):
        from bob3.spec_quality.example_grammar import KeyExample
        examples = []
        require_boundary_example("system logs authentication event", examples)

    def test_numeric_ac_with_zero_boundary_does_not_raise(self):
        from bob3.spec_quality.example_grammar import KeyExample
        examples = [
            KeyExample(given="0", then="0", raw="given: 0, then: 0"),
        ]
        require_boundary_example(
            "system transforms integer value to output range 0-100",
            examples,
        )
