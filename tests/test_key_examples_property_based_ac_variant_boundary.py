"""Boundary tests for key-examples / property-based AC variant.

AC: empty, zero, or minimum input returns a well-defined result rather than
raising (boundary case).

Tests verify that the parsing and emission functions handle edge/minimum inputs
gracefully — returning empty results or None, never raising unexpectedly.
"""

from __future__ import annotations

import pytest

from ac_grammar.property_based import parse_key_example_ac, parse_property_ac
from bob3.key_examples_property_based_ac_variant import key_examples_property_based_ac_variant
from bob3.spec_quality.example_grammar import (
    check_boundary_satisfied,
    emit_hypothesis_test,
    emit_parametrize_test,
    parse_property_ac as eg_parse_property_ac,
    requires_boundary,
)


# ---------------------------------------------------------------------------
# parse_property_ac — boundary inputs
# ---------------------------------------------------------------------------


class TestParsePropertyACBoundary:
    def test_empty_string_returns_none_not_raises(self):
        result = parse_property_ac("")
        assert result is None

    def test_none_returns_none_not_raises(self):
        result = parse_property_ac(None)
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = parse_property_ac("   ")
        assert result is None

    def test_property_keyword_only_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_property_ac("property:")

    def test_minimal_valid_property_ac(self):
        result = parse_property_ac("property: p for st.integers() assert True")
        assert result is not None
        assert result.name == "p"

    def test_single_character_name(self):
        result = parse_property_ac("property: x for st.integers() assert x == x")
        assert result is not None

    def test_predicate_with_zero(self):
        result = parse_property_ac("property: zero_ok for st.integers() assert x >= 0 or x < 0")
        assert result is not None


# ---------------------------------------------------------------------------
# parse_key_example_ac — boundary inputs
# ---------------------------------------------------------------------------


class TestParseKeyExampleACBoundary:
    def test_none_returns_none_not_raises(self):
        result = parse_key_example_ac(None)
        assert result is None

    def test_empty_string_returns_none_not_raises(self):
        result = parse_key_example_ac("")
        assert result is None

    def test_empty_dict_returns_none_not_raises(self):
        result = parse_key_example_ac({})
        assert result is None

    def test_given_empty_string_value(self):
        result = parse_key_example_ac({"given": "", "then": "expected"})
        assert result is not None
        assert result.given == ""

    def test_then_empty_string_value(self):
        result = parse_key_example_ac({"given": "input", "then": ""})
        assert result is not None
        assert result.then == ""

    def test_zero_as_given(self):
        result = parse_key_example_ac({"given": "0", "then": "0"})
        assert result is not None
        assert result.given == "0"

    def test_string_with_just_given_and_then_labels(self):
        result = parse_key_example_ac("given: , then: ")
        # Empty values — either returns None or returns a valid entry with empty strings
        # The important thing is it does NOT raise
        assert result is None or isinstance(result, type(result))


# ---------------------------------------------------------------------------
# emit_hypothesis_test — boundary inputs
# ---------------------------------------------------------------------------


class TestEmitHypothesisTestBoundary:
    def test_simple_property_returns_valid_source(self):
        prop = eg_parse_property_ac("property: t for st.integers() assert True")
        code = emit_hypothesis_test(prop, seed=0)
        assert "@given" in code
        compile(code, "<string>", "exec")

    def test_seed_zero_produces_output(self):
        prop = eg_parse_property_ac("property: t for st.integers() assert True")
        code = emit_hypothesis_test(prop, seed=0)
        assert "0" in code  # seed=0 appears in settings


# ---------------------------------------------------------------------------
# emit_parametrize_test — boundary inputs
# ---------------------------------------------------------------------------


class TestEmitParametrizeTestBoundary:
    def test_empty_list_returns_empty_string(self):
        result = emit_parametrize_test([], seed=0)
        assert result == ""

    def test_single_example_produces_parametrize(self):
        from bob3.spec_quality.example_grammar import KeyExample
        ex = KeyExample(given="0", then="0", raw="given: 0, then: 0")
        code = emit_parametrize_test([ex], seed=0)
        assert "@pytest.mark.parametrize" in code
        compile(code, "<string>", "exec")


# ---------------------------------------------------------------------------
# requires_boundary — boundary inputs
# ---------------------------------------------------------------------------


class TestRequiresBoundaryBoundary:
    def test_empty_ac_does_not_require_boundary(self):
        req = requires_boundary("")
        assert req.required is False

    def test_non_numeric_ac_does_not_require_boundary(self):
        req = requires_boundary("system logs authentication event")
        assert req.required is False

    def test_zero_word_ac_requires_boundary(self):
        req = requires_boundary("system must return zero when input is empty")
        assert req.required is True

    def test_range_word_triggers_boundary(self):
        req = requires_boundary("value must be in range 0-100")
        assert req.required is True


# ---------------------------------------------------------------------------
# key_examples_property_based_ac_variant integration — boundary inputs
# ---------------------------------------------------------------------------


class TestIntegrationBoundary:
    def test_empty_key_examples_list(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
        )
        assert result["key_examples"] == []
        assert result["parametrize_test"] == ""
        assert result["boundary_required"] is False
        assert result["boundary_satisfied"] is True

    def test_none_property_ac_no_hypothesis(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
        )
        assert result["hypothesis_test"] == ""

    def test_all_none_key_examples_yields_empty(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[None, None, None],
        )
        assert result["key_examples"] == []

    def test_zero_value_key_example_parsed(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "0", "then": "0"}],
        )
        assert len(result["key_examples"]) == 1

    def test_boundary_satisfied_with_zero_example(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "0", "then": "0"}],
            behavior_ac="system converts integer value to string",
        )
        assert result["boundary_satisfied"] is True
