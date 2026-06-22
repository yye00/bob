"""Tests for property-based AC codegen (seventh AC grammar).

Verifies that:
- ``parse_property_ac`` in ``bob3.acceptance_criteria.property_grammar`` parses
  the ``property: <name> for <generator> assert <predicate>`` grammar.
- ``emit_hypothesis_test`` produces runnable Hypothesis test source code.
- The codegen agent receives the property as few-shot context via
  ``key_examples_property_based_ac_variant``.
"""

from __future__ import annotations

import pytest

from bob3.acceptance_criteria.property_grammar import parse_property_ac
from bob3.key_examples_property_based_ac_variant import key_examples_property_based_ac_variant
from bob3.spec_quality.example_grammar import (
    PropertyAC,
    emit_hypothesis_test,
    parse_property_ac as eg_parse_property_ac,
)


# ---------------------------------------------------------------------------
# parse_property_ac — happy paths
# ---------------------------------------------------------------------------


class TestParsePropertyAC:
    def test_basic_property_ac(self):
        ac = "property: non_negative for st.integers() assert x >= 0"
        result = parse_property_ac(ac)
        assert isinstance(result, PropertyAC)
        assert result.name == "non_negative"
        assert result.generator == "st.integers()"
        assert result.predicate == "x >= 0"

    def test_multi_word_name(self):
        ac = "property: round trip identity for st.text() assert encode(decode(s)) == s"
        result = parse_property_ac(ac)
        assert result is not None
        assert "round" in result.name

    def test_complex_generator(self):
        ac = "property: valid_range for st.integers(min_value=0, max_value=100) assert 0 <= x <= 100"
        result = parse_property_ac(ac)
        assert result is not None
        assert "min_value" in result.generator

    def test_predicate_with_function_call(self):
        ac = "property: sorted_output for st.lists(st.integers()) assert result == sorted(result)"
        result = parse_property_ac(ac)
        assert result is not None
        assert "sorted" in result.predicate

    def test_case_insensitive_property_keyword(self):
        ac = "Property: non_negative for st.integers() assert x >= 0"
        result = parse_property_ac(ac)
        assert result is not None

    def test_raw_field_preserved(self):
        ac = "property: p for st.integers() assert x == x"
        result = parse_property_ac(ac)
        assert result is not None
        assert result.raw is not None

    def test_non_property_ac_returns_none(self):
        assert parse_property_ac("pytest: tests/test_foo.py") is None
        assert parse_property_ac("File exists: src/foo.py") is None
        assert parse_property_ac("function defined: foo.bar") is None

    def test_none_returns_none(self):
        assert parse_property_ac(None) is None

    def test_empty_returns_none(self):
        assert parse_property_ac("") is None

    def test_whitespace_returns_none(self):
        assert parse_property_ac("   ") is None


# ---------------------------------------------------------------------------
# emit_hypothesis_test — codegen output
# ---------------------------------------------------------------------------


class TestEmitHypothesisTest:
    def _parse(self, ac: str) -> PropertyAC:
        result = eg_parse_property_ac(ac)
        assert result is not None
        return result

    def test_contains_given_decorator(self):
        prop = self._parse("property: p for st.integers() assert x >= 0")
        code = emit_hypothesis_test(prop, seed=0)
        assert "@given" in code

    def test_contains_settings_decorator(self):
        prop = self._parse("property: p for st.integers() assert x >= 0")
        code = emit_hypothesis_test(prop, seed=0)
        assert "@settings" in code

    def test_seed_0_present_in_output(self):
        prop = self._parse("property: p for st.integers() assert x >= 0")
        code = emit_hypothesis_test(prop, seed=0)
        assert "0" in code

    def test_generator_in_output(self):
        prop = self._parse("property: p for st.integers() assert x >= 0")
        code = emit_hypothesis_test(prop, seed=0)
        assert "st.integers()" in code

    def test_predicate_in_output(self):
        prop = self._parse("property: p for st.integers() assert x >= 0")
        code = emit_hypothesis_test(prop, seed=0)
        assert "x >= 0" in code

    def test_output_is_valid_python(self):
        prop = self._parse("property: non_negative for st.integers() assert x >= 0")
        code = emit_hypothesis_test(prop, seed=0)
        compile(code, "<test>", "exec")

    def test_function_name_derived_from_property_name(self):
        prop = self._parse("property: non_negative for st.integers() assert x >= 0")
        code = emit_hypothesis_test(prop, seed=0)
        assert "non_negative" in code

    def test_hypothesis_import_present(self):
        prop = self._parse("property: p for st.integers() assert x >= 0")
        code = emit_hypothesis_test(prop, seed=0)
        assert "from hypothesis" in code or "import hypothesis" in code


# ---------------------------------------------------------------------------
# few-shot context via integration function
# ---------------------------------------------------------------------------


class TestFewShotContext:
    def test_property_ac_in_few_shot_context(self):
        result = key_examples_property_based_ac_variant(
            property_ac="property: non_negative for st.integers() assert x >= 0",
            key_examples=[],
        )
        ctx = result["few_shot_context"]
        assert "non_negative" in ctx

    def test_empty_property_no_few_shot_property_entry(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
        )
        ctx = result["few_shot_context"]
        assert "property:" not in ctx

    def test_key_examples_appear_in_few_shot_context(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "x=5", "then": "25"}],
        )
        ctx = result["few_shot_context"]
        assert "x=5" in ctx or "key_examples" in ctx

    def test_hypothesis_test_emitted_for_property_ac(self):
        result = key_examples_property_based_ac_variant(
            property_ac="property: non_negative for st.integers() assert x >= 0",
            key_examples=[],
        )
        assert "@given" in result["hypothesis_test"]

    def test_no_hypothesis_test_without_property_ac(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
        )
        assert result["hypothesis_test"] == ""
