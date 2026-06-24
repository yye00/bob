"""Tests for bob.spec_synthesis.parse_property_ac — seventh AC grammar."""

from __future__ import annotations

import pytest

from bob.spec_synthesis import parse_property_ac
from bob.spec_quality.example_grammar import PropertyAC


class TestParsePropertyACBasic:
    def test_valid_property_ac_returns_property_ac(self):
        result = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert result is not None
        assert isinstance(result, PropertyAC)

    def test_name_extracted_correctly(self):
        result = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert result.name == "non_negative"

    def test_generator_extracted_correctly(self):
        result = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert result.generator == "st.integers()"

    def test_predicate_extracted_correctly(self):
        result = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert result.predicate == "x >= 0"

    def test_non_property_ac_returns_none(self):
        result = parse_property_ac("pytest: tests/test_foo.py")
        assert result is None

    def test_file_exists_ac_returns_none(self):
        result = parse_property_ac("File exists: src/bob/foo.py")
        assert result is None

    def test_none_returns_none(self):
        result = parse_property_ac(None)
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_property_ac("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = parse_property_ac("   ")
        assert result is None


class TestParsePropertyACErrorCases:
    def test_missing_for_clause_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: p assert x >= 0")

    def test_missing_assert_clause_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: p for st.integers()")

    def test_property_keyword_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property:")

    def test_property_with_name_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: my_name")

    def test_raises_value_error_not_other_exception_type(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: x for assert")

    def test_raw_field_preserved(self):
        ac = "property: sorted_list for st.lists(st.integers()) assert len(x) >= 0"
        result = parse_property_ac(ac)
        assert result is not None
        assert result.raw == ac.strip()

    def test_complex_predicate(self):
        result = parse_property_ac(
            "property: reversible for st.text() assert x == x[::-1][::-1]"
        )
        assert result is not None
        assert "==" in result.predicate

    def test_case_insensitive_property_keyword(self):
        result = parse_property_ac(
            "Property: t for st.integers() assert True"
        )
        assert result is not None
