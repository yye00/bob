"""Tests for ac_grammar.property_based — seventh AC grammar.

Covers:
- parse_property_ac: parses ``property: <name> for <generator> assert <predicate>``
- parse_key_example_ac: parses ``key_example:`` sub-key entries
- Integration: imports and return types are correct
"""

from __future__ import annotations

import pytest

from ac_grammar.property_based import parse_key_example_ac, parse_property_ac
from bob3.spec_quality.example_grammar import KeyExample, PropertyAC


# ---------------------------------------------------------------------------
# parse_property_ac
# ---------------------------------------------------------------------------


class TestParsePropertyAC:
    def test_basic_property_ac_returns_property_ac(self):
        result = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert isinstance(result, PropertyAC)

    def test_name_extracted(self):
        result = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert result.name == "non_negative"

    def test_generator_extracted(self):
        result = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert result.generator == "st.integers()"

    def test_predicate_extracted(self):
        result = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert result.predicate == "x >= 0"

    def test_non_property_ac_returns_none(self):
        result = parse_property_ac("pytest: tests/test_foo.py")
        assert result is None

    def test_behavior_ac_returns_none(self):
        result = parse_property_ac("system must log user authentication events")
        assert result is None

    def test_none_input_returns_none(self):
        result = parse_property_ac(None)
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_property_ac("")
        assert result is None

    def test_text_strategy_generator(self):
        result = parse_property_ac(
            "property: non_empty for st.text() assert len(x) >= 0"
        )
        assert result.generator == "st.text()"

    def test_complex_generator(self):
        result = parse_property_ac(
            "property: bounded for st.integers(min_value=0, max_value=100) assert 0 <= x <= 100"
        )
        assert "min_value=0" in result.generator
        assert "max_value=100" in result.generator

    def test_complex_predicate(self):
        result = parse_property_ac(
            "property: positive_sum for st.lists(st.integers(min_value=1)) assert sum(x) > 0"
        )
        assert "sum(x) > 0" in result.predicate

    def test_raw_field_preserved(self):
        raw = "property: non_negative for st.integers() assert x >= 0"
        result = parse_property_ac(raw)
        assert result.raw == raw

    def test_missing_for_clause_raises_value_error(self):
        with pytest.raises(ValueError, match="for"):
            parse_property_ac("property: non_negative assert x >= 0")

    def test_missing_assert_clause_raises_value_error(self):
        with pytest.raises(ValueError, match="assert"):
            parse_property_ac("property: non_negative for st.integers()")

    def test_case_insensitive_keyword(self):
        result = parse_property_ac(
            "Property: non_negative for st.integers() assert x >= 0"
        )
        assert result is not None
        assert result.name == "non_negative"


# ---------------------------------------------------------------------------
# parse_key_example_ac
# ---------------------------------------------------------------------------


class TestParseKeyExampleAC:
    def test_dict_form_returns_key_example(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert isinstance(result, KeyExample)

    def test_dict_given_extracted(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert result.given == "x=5"

    def test_dict_then_extracted(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert result.then == "result=25"

    def test_string_form_parses(self):
        result = parse_key_example_ac("given: x=5, then: result=25")
        assert isinstance(result, KeyExample)
        assert "x=5" in result.given

    def test_string_form_then_extracted(self):
        result = parse_key_example_ac("given: x=5, then: result=25")
        assert "result=25" in result.then

    def test_none_returns_none(self):
        result = parse_key_example_ac(None)
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_key_example_ac("")
        assert result is None

    def test_empty_dict_returns_none(self):
        result = parse_key_example_ac({})
        assert result is None

    def test_dict_missing_both_keys_raises(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"no_given": "x", "no_then": "y"})

    def test_dict_missing_given_returns_none(self):
        result = parse_key_example_ac({"then": "result=25"})
        assert result is None

    def test_dict_missing_then_returns_none(self):
        result = parse_key_example_ac({"given": "x=5"})
        assert result is None

    def test_raw_field_set(self):
        result = parse_key_example_ac({"given": "x=5", "then": "25"})
        assert result.raw != ""

    def test_numeric_values(self):
        result = parse_key_example_ac({"given": "0", "then": "0"})
        assert result.given == "0"
        assert result.then == "0"

    def test_complex_given_value(self):
        result = parse_key_example_ac(
            {"given": "[1, 2, 3]", "then": "6"}
        )
        assert "[1, 2, 3]" in result.given


# ---------------------------------------------------------------------------
# Integration: contract_grammar compatibility
# ---------------------------------------------------------------------------


class TestContractGrammarIntegration:
    """Integration: property_based can be imported alongside contract_grammar."""

    def test_import_alongside_contract_grammar(self):
        from bob3.spec_quality.contract_grammar import ContractSpec, emit_icontract_decorators

        spec = ContractSpec(pre=["x > 0"])
        output = emit_icontract_decorators(spec)
        assert "lambda x:" in output

        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        assert prop is not None

    def test_property_ac_and_key_example_together(self):
        prop = parse_property_ac(
            "property: sorted_output for st.lists(st.integers()) assert result == sorted(x)"
        )
        ex = parse_key_example_ac({"given": "[]", "then": "[]"})
        assert prop is not None
        assert ex is not None
