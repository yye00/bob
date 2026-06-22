"""Tests for raises_on_malformed_property — rejects ACs with missing generator clause."""

from __future__ import annotations

import pytest

from bob3.spec_quality.example_grammar import (
    PropertyAC,
    PropertyParseError,
    raises_on_malformed_property,
)


class TestRaisesOnMalformedProperty:
    def test_valid_property_returns_parsed(self):
        ac = "property: non_negative for st.integers() assert x >= 0"
        result = raises_on_malformed_property(ac)
        assert isinstance(result, PropertyAC)
        assert result.name == "non_negative"

    def test_missing_for_clause_raises(self):
        ac = "property: non_negative assert x >= 0"
        with pytest.raises(PropertyParseError, match="generator"):
            raises_on_malformed_property(ac)

    def test_missing_assert_clause_raises(self):
        ac = "property: non_negative for st.integers()"
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property(ac)

    def test_not_a_property_ac_raises(self):
        ac = "pytest: tests/test_foo.py"
        with pytest.raises(PropertyParseError, match="property:"):
            raises_on_malformed_property(ac)

    def test_behavior_ac_raises(self):
        ac = "behavior: parser returns None when input is empty"
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property(ac)

    def test_file_exists_ac_raises(self):
        ac = "File exists: src/bob3/spec_quality/example_grammar.py"
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property(ac)

    def test_empty_string_raises(self):
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property("")

    def test_property_only_prefix_raises(self):
        with pytest.raises(PropertyParseError):
            raises_on_malformed_property("property:")

    def test_valid_string_generator_returned(self):
        ac = "property: sorted_output for st.lists(st.integers()) assert result == sorted(result)"
        result = raises_on_malformed_property(ac)
        assert "st.lists" in result.generator

    def test_valid_predicate_returned(self):
        ac = "property: abs_positive for st.integers() assert abs(x) >= 0"
        result = raises_on_malformed_property(ac)
        assert "abs(x) >= 0" in result.predicate

    def test_error_message_includes_ac(self):
        ac = "property: bad_ac assert x >= 0"
        with pytest.raises(PropertyParseError) as exc_info:
            raises_on_malformed_property(ac)
        assert "bad_ac" in str(exc_info.value) or "generator" in str(exc_info.value)

    def test_property_parse_error_is_value_error(self):
        ac = "property: missing_for assert x >= 0"
        with pytest.raises(ValueError):
            raises_on_malformed_property(ac)
