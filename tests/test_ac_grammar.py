"""Tests for bob77.ac_grammar — seventh AC grammar: property-based and key-example parsing.

Tests cover:
- parse_property_ac: parses ``property: <name> for <generator> assert <predicate>``
- parse_key_example_ac: parses ``key_example:`` sub-key entries (dict or string)
- Error cases raise ValueError for malformed inputs
- Boundary/null inputs handled gracefully
"""

from __future__ import annotations

import pytest

from bob77.ac_grammar import parse_key_example_ac, parse_property_ac
from bob.spec_quality.example_grammar import PropertyAC, KeyExample


# ---------------------------------------------------------------------------
# parse_property_ac — happy path
# ---------------------------------------------------------------------------


class TestParsePropertyAC:
    def test_basic_integer_property(self):
        result = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert result is not None
        assert isinstance(result, PropertyAC)
        assert result.name == "non_negative"
        assert result.generator == "st.integers()"
        assert result.predicate == "x >= 0"

    def test_text_strategy_property(self):
        result = parse_property_ac(
            "property: non_empty_text for st.text() assert len(s) >= 0"
        )
        assert result is not None
        assert result.name == "non_empty_text"
        assert "st.text()" in result.generator

    def test_bounded_integers_property(self):
        result = parse_property_ac(
            "property: bounded for st.integers(min_value=0, max_value=100) assert 0 <= x <= 100"
        )
        assert result is not None
        assert result.name == "bounded"
        assert "min_value=0" in result.generator

    def test_property_with_float_strategy(self):
        result = parse_property_ac(
            "property: finite_float for st.floats(allow_nan=False) assert not math.isnan(x)"
        )
        assert result is not None

    def test_property_raw_preserved(self):
        raw = "property: identity for st.integers() assert x == x"
        result = parse_property_ac(raw)
        assert result is not None
        assert result.raw == raw

    def test_non_property_ac_returns_none(self):
        assert parse_property_ac("pytest: tests/test_foo.py") is None
        assert parse_property_ac("file exists: src/bob77/thing.py") is None
        assert parse_property_ac("function defined: mod.func") is None

    def test_none_input_returns_none(self):
        assert parse_property_ac(None) is None

    def test_empty_string_returns_none(self):
        assert parse_property_ac("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_property_ac("   ") is None


# ---------------------------------------------------------------------------
# parse_property_ac — error paths
# ---------------------------------------------------------------------------


class TestParsePropertyACErrors:
    def test_missing_for_clause_raises_value_error(self):
        with pytest.raises(ValueError, match="for"):
            parse_property_ac("property: p assert x >= 0")

    def test_missing_assert_clause_raises_value_error(self):
        with pytest.raises(ValueError, match="assert"):
            parse_property_ac("property: p for st.integers()")

    def test_property_keyword_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property:")

    def test_property_with_name_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: some_name")


# ---------------------------------------------------------------------------
# parse_key_example_ac — happy path
# ---------------------------------------------------------------------------


class TestParseKeyExampleAC:
    def test_dict_with_given_and_then(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert result is not None
        assert isinstance(result, KeyExample)
        assert result.given == "x=5"
        assert result.then == "result=25"

    def test_dict_with_zero_values(self):
        result = parse_key_example_ac({"given": "0", "then": "0"})
        assert result is not None
        assert result.given == "0"
        assert result.then == "0"

    def test_dict_with_capitalized_keys(self):
        result = parse_key_example_ac({"Given": "input=abc", "Then": "output=ABC"})
        assert result is not None

    def test_string_form_given_then(self):
        result = parse_key_example_ac("given: x=5, then: result=25")
        assert result is not None
        assert result.given == "x=5"
        assert result.then == "result=25"

    def test_string_form_without_comma(self):
        result = parse_key_example_ac("given: empty list then: returns []")
        assert result is not None

    def test_none_returns_none(self):
        assert parse_key_example_ac(None) is None

    def test_empty_string_returns_none(self):
        assert parse_key_example_ac("") is None

    def test_empty_dict_returns_none(self):
        assert parse_key_example_ac({}) is None


# ---------------------------------------------------------------------------
# parse_key_example_ac — error paths
# ---------------------------------------------------------------------------


class TestParseKeyExampleACErrors:
    def test_dict_missing_both_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"wrong_key": "x", "another_wrong": "y"})

    def test_dict_with_only_unrelated_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"foo": "bar", "baz": "qux"})
