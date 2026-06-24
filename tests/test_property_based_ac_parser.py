"""Tests for bob.property_based_ac_parser — seventh AC grammar parser.

Covers:
- parse_property_criterion — property: <name> for <generator> assert <predicate>
- parse_key_example_variant — key_example: sub-key entries (dict or string)
- Integration with bob.acceptance_criteria
"""

from __future__ import annotations

import pytest

from bob.property_based_ac_parser import (
    KeyExample,
    PropertyAC,
    parse_key_example_variant,
    parse_property_criterion,
)


# ---------------------------------------------------------------------------
# parse_property_criterion — happy path
# ---------------------------------------------------------------------------


class TestParsePropertyCriterionHappyPath:
    def test_basic_property_ac_returns_property_ac(self):
        result = parse_property_criterion(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert isinstance(result, PropertyAC)
        assert result.name == "non_negative"
        assert result.generator == "st.integers()"
        assert result.predicate == "x >= 0"

    def test_property_with_complex_generator(self):
        result = parse_property_criterion(
            "property: bounded for st.integers(min_value=0, max_value=100) assert 0 <= x <= 100"
        )
        assert result is not None
        assert result.name == "bounded"
        assert "min_value=0" in result.generator

    def test_property_preserves_raw_string(self):
        raw = "property: idempotent for st.text() assert x == x"
        result = parse_property_criterion(raw)
        assert result is not None
        assert result.raw == raw

    def test_non_property_ac_returns_none(self):
        result = parse_property_criterion("pytest: tests/test_foo.py")
        assert result is None

    def test_file_exists_ac_returns_none(self):
        result = parse_property_criterion("File exists: src/bob/foo.py")
        assert result is None

    def test_function_defined_ac_returns_none(self):
        result = parse_property_criterion("Function defined: bob.foo.bar")
        assert result is None

    def test_name_with_underscores(self):
        result = parse_property_criterion(
            "property: always_positive for st.integers(min_value=1) assert x > 0"
        )
        assert result is not None
        assert result.name == "always_positive"

    def test_predicate_with_function_call(self):
        result = parse_property_criterion(
            "property: sorted_order for st.lists(st.integers()) assert result == sorted(result)"
        )
        assert result is not None
        assert "sorted" in result.predicate


# ---------------------------------------------------------------------------
# parse_property_criterion — boundary / edge inputs
# ---------------------------------------------------------------------------


class TestParsePropertyCriterionBoundary:
    def test_none_returns_none(self):
        result = parse_property_criterion(None)
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_property_criterion("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = parse_property_criterion("   ")
        assert result is None

    def test_minimal_valid_property(self):
        result = parse_property_criterion("property: p for st.integers() assert True")
        assert result is not None
        assert result.name == "p"

    def test_single_char_name(self):
        result = parse_property_criterion("property: x for st.integers() assert x == x")
        assert result is not None


# ---------------------------------------------------------------------------
# parse_property_criterion — error paths
# ---------------------------------------------------------------------------


class TestParsePropertyCriterionErrors:
    def test_missing_for_clause_raises_value_error(self):
        with pytest.raises(ValueError, match="for"):
            parse_property_criterion("property: non_negative assert x >= 0")

    def test_missing_assert_clause_raises_value_error(self):
        with pytest.raises(ValueError, match="assert"):
            parse_property_criterion("property: non_negative for st.integers()")

    def test_property_keyword_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_criterion("property:")

    def test_property_with_name_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_criterion("property: some_name")

    def test_missing_predicate_text_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_criterion("property: p for st.integers() assert")

    def test_raises_value_error_not_other_exception(self):
        with pytest.raises(ValueError):
            parse_property_criterion("property: x for assert y")


# ---------------------------------------------------------------------------
# parse_key_example_variant — happy path
# ---------------------------------------------------------------------------


class TestParseKeyExampleVariantHappyPath:
    def test_dict_with_given_and_then(self):
        result = parse_key_example_variant({"given": "x=5", "then": "result=25"})
        assert isinstance(result, KeyExample)
        assert result.given == "x=5"
        assert result.then == "result=25"

    def test_string_form_given_then(self):
        result = parse_key_example_variant("given: x=5, then: result=25")
        assert result is not None
        assert result.given == "x=5"
        assert result.then == "result=25"

    def test_dict_integer_values_coerced_to_str(self):
        result = parse_key_example_variant({"given": 0, "then": 0})
        assert result is not None
        assert result.given == "0"
        assert result.then == "0"

    def test_dict_with_capitalized_keys(self):
        result = parse_key_example_variant({"Given": "input", "Then": "output"})
        assert result is not None

    def test_string_form_without_comma(self):
        result = parse_key_example_variant("given: a then: b")
        assert result is not None
        assert result.given == "a"
        assert result.then == "b"


# ---------------------------------------------------------------------------
# parse_key_example_variant — boundary / edge inputs
# ---------------------------------------------------------------------------


class TestParseKeyExampleVariantBoundary:
    def test_none_returns_none(self):
        result = parse_key_example_variant(None)
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_key_example_variant("")
        assert result is None

    def test_empty_dict_returns_none(self):
        result = parse_key_example_variant({})
        assert result is None

    def test_given_empty_string_value(self):
        result = parse_key_example_variant({"given": "", "then": "expected"})
        assert result is not None
        assert result.given == ""

    def test_then_empty_string_value(self):
        result = parse_key_example_variant({"given": "input", "then": ""})
        assert result is not None
        assert result.then == ""

    def test_zero_as_given(self):
        result = parse_key_example_variant({"given": "0", "then": "0"})
        assert result is not None
        assert result.given == "0"


# ---------------------------------------------------------------------------
# parse_key_example_variant — error paths
# ---------------------------------------------------------------------------


class TestParseKeyExampleVariantErrors:
    def test_dict_missing_both_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_variant({"wrong_key": "x", "another_wrong": "y"})

    def test_dict_with_only_unrelated_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_variant({"foo": "bar", "baz": "qux"})

    def test_does_not_raise_on_none(self):
        result = parse_key_example_variant(None)
        assert result is None

    def test_does_not_raise_on_empty_string(self):
        result = parse_key_example_variant("")
        assert result is None

    def test_does_not_silently_succeed_on_bad_dict(self):
        with pytest.raises(ValueError):
            result = parse_key_example_variant({"not_given": "x", "not_then": "y"})
            pytest.fail(f"Expected ValueError, got {result!r}")


# ---------------------------------------------------------------------------
# Integration: bob.acceptance_criteria imports parse_property_criterion / parse_key_example_variant
# ---------------------------------------------------------------------------


class TestAcceptanceCriteriaIntegration:
    def test_acceptance_criteria_module_importable(self):
        import bob.acceptance_criteria as ac_mod
        assert ac_mod is not None

    def test_parse_property_criterion_importable_from_parser(self):
        from bob.property_based_ac_parser import parse_property_criterion
        assert callable(parse_property_criterion)

    def test_parse_key_example_variant_importable_from_parser(self):
        from bob.property_based_ac_parser import parse_key_example_variant
        assert callable(parse_key_example_variant)

    def test_parse_property_criterion_returns_correct_type(self):
        from bob.property_based_ac_parser import parse_property_criterion, PropertyAC
        result = parse_property_criterion(
            "property: always_true for st.integers() assert True"
        )
        assert isinstance(result, PropertyAC)

    def test_parse_key_example_variant_returns_correct_type(self):
        from bob.property_based_ac_parser import parse_key_example_variant, KeyExample
        result = parse_key_example_variant({"given": "input", "then": "output"})
        assert isinstance(result, KeyExample)
