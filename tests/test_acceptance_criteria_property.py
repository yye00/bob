"""Tests for bob3.acceptance_criteria.parse_property_ac.

Verifies the seventh AC grammar: ``property: <name> for <generator> assert <predicate>``
is correctly parsed and exported from bob3.acceptance_criteria.
"""

from __future__ import annotations

import pytest

from bob3.acceptance_criteria import parse_property_ac
from bob3.spec_quality.example_grammar import PropertyAC


class TestParsePropertyACBasic:
    def test_returns_property_ac_for_valid_input(self):
        result = parse_property_ac("property: non_negative for st.integers() assert x >= 0")
        assert result is not None
        assert isinstance(result, PropertyAC)

    def test_name_is_extracted(self):
        result = parse_property_ac("property: non_negative for st.integers() assert x >= 0")
        assert result.name == "non_negative"

    def test_generator_is_extracted(self):
        result = parse_property_ac("property: non_negative for st.integers() assert x >= 0")
        assert result.generator == "st.integers()"

    def test_predicate_is_extracted(self):
        result = parse_property_ac("property: non_negative for st.integers() assert x >= 0")
        assert result.predicate == "x >= 0"

    def test_raw_is_stored(self):
        ac = "property: non_negative for st.integers() assert x >= 0"
        result = parse_property_ac(ac)
        assert result.raw == ac.strip()

    def test_multiword_name(self):
        result = parse_property_ac("property: always positive for st.integers(min_value=1) assert x > 0")
        assert result is not None
        assert "positive" in result.name.lower() or "always" in result.name.lower()

    def test_complex_generator(self):
        result = parse_property_ac(
            "property: bounded for st.integers(min_value=0, max_value=100) assert 0 <= x <= 100"
        )
        assert result is not None
        assert "min_value=0" in result.generator

    def test_complex_predicate(self):
        result = parse_property_ac(
            "property: non_empty for st.lists(st.integers()) assert len(x) >= 0"
        )
        assert result is not None
        assert "len(x)" in result.predicate


class TestParsePropertyACNonProperty:
    def test_returns_none_for_pytest_ac(self):
        result = parse_property_ac("pytest: tests/test_foo.py")
        assert result is None

    def test_returns_none_for_file_exists_ac(self):
        result = parse_property_ac("File exists: src/bob3/foo.py")
        assert result is None

    def test_returns_none_for_function_defined_ac(self):
        result = parse_property_ac("Function defined: bob3.foo.bar")
        assert result is None

    def test_returns_none_for_empty_string(self):
        result = parse_property_ac("")
        assert result is None

    def test_returns_none_for_none(self):
        result = parse_property_ac(None)
        assert result is None

    def test_returns_none_for_whitespace_only(self):
        result = parse_property_ac("   ")
        assert result is None


class TestParsePropertyACErrors:
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

    def test_raises_value_error_not_type_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property: x for assert")


class TestParsePropertyACImport:
    def test_function_importable_from_acceptance_criteria(self):
        from bob3.acceptance_criteria import parse_property_ac as fn
        assert callable(fn)

    def test_returns_property_ac_dataclass(self):
        result = parse_property_ac("property: t for st.integers() assert True")
        assert hasattr(result, "name")
        assert hasattr(result, "generator")
        assert hasattr(result, "predicate")
        assert hasattr(result, "raw")

    def test_property_ac_is_frozen(self):
        result = parse_property_ac("property: t for st.integers() assert True")
        with pytest.raises((AttributeError, TypeError)):
            result.name = "modified"
