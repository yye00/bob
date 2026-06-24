"""Tests for bob.behavior_ac: add_key_examples and KeyExampleVariant."""

from __future__ import annotations

import pytest

from bob.behavior_ac import (
    KeyExample,
    KeyExampleVariant,
    add_key_examples,
    parse_key_example,
)
from bob.spec_quality.example_grammar import PropertyAC


class TestAddKeyExamples:
    def test_add_examples_to_empty_variant(self):
        variant = KeyExampleVariant(behavior_ac="system logs event")
        result = add_key_examples(variant, [{"given": "x=1", "then": "logged"}])
        assert len(result.examples) == 1

    def test_returns_new_variant_not_mutated(self):
        variant = KeyExampleVariant(behavior_ac="system logs event")
        result = add_key_examples(variant, [{"given": "x=1", "then": "logged"}])
        assert result is not variant
        assert len(variant.examples) == 0

    def test_preserves_original_examples(self):
        original_ex = KeyExample(given="a=0", then="0", raw="given: a=0, then: 0")
        variant = KeyExampleVariant(behavior_ac="ac", examples=[original_ex])
        result = add_key_examples(variant, [{"given": "b=1", "then": "1"}])
        assert len(result.examples) == 2
        assert result.examples[0] is original_ex

    def test_none_entries_skipped(self):
        variant = KeyExampleVariant(behavior_ac="ac")
        result = add_key_examples(variant, [None, {"given": "x", "then": "y"}, None])
        assert len(result.examples) == 1

    def test_empty_list_returns_equivalent_variant(self):
        variant = KeyExampleVariant(behavior_ac="ac")
        result = add_key_examples(variant, [])
        assert len(result.examples) == 0
        assert result.behavior_ac == variant.behavior_ac

    def test_string_form_example_parsed(self):
        variant = KeyExampleVariant(behavior_ac="ac")
        result = add_key_examples(variant, ["given: x=5, then: result=25"])
        assert len(result.examples) == 1
        assert result.examples[0].given == "x=5"

    def test_preserves_property_ac(self):
        prop = PropertyAC(
            name="p",
            generator="st.integers()",
            predicate="True",
            raw="property: p for st.integers() assert True",
        )
        variant = KeyExampleVariant(behavior_ac="ac", property_ac=prop)
        result = add_key_examples(variant, [{"given": "0", "then": "0"}])
        assert result.property_ac is prop

    def test_multiple_examples_added(self):
        variant = KeyExampleVariant(behavior_ac="ac")
        result = add_key_examples(variant, [
            {"given": "x=1", "then": "1"},
            {"given": "x=2", "then": "2"},
            {"given": "x=3", "then": "3"},
        ])
        assert len(result.examples) == 3


class TestKeyExampleVariantFewShotContext:
    def test_no_examples_no_property_empty_context(self):
        variant = KeyExampleVariant(behavior_ac="ac")
        assert variant.few_shot_context == ""

    def test_property_included_in_context(self):
        prop = PropertyAC(
            name="p",
            generator="st.integers()",
            predicate="True",
            raw="property: p for st.integers() assert True",
        )
        variant = KeyExampleVariant(behavior_ac="ac", property_ac=prop)
        ctx = variant.few_shot_context
        assert "property:" in ctx
        assert "st.integers()" in ctx

    def test_examples_included_in_context(self):
        ex = KeyExample(given="x=0", then="0", raw="given: x=0, then: 0")
        variant = KeyExampleVariant(behavior_ac="ac", examples=[ex])
        ctx = variant.few_shot_context
        assert "key_examples:" in ctx
        assert "x=0" in ctx


class TestKeyExampleVariantBoundary:
    def test_non_numeric_ac_boundary_not_required(self):
        variant = KeyExampleVariant(behavior_ac="system logs authentication event")
        assert variant.boundary_required is False
        assert variant.boundary_satisfied is True

    def test_numeric_ac_with_zero_boundary_satisfied(self):
        ex = KeyExample(given="0", then="0", raw="given: 0, then: 0")
        variant = KeyExampleVariant(
            behavior_ac="system converts integer value to string",
            examples=[ex],
        )
        assert variant.boundary_satisfied is True

    def test_hypothesis_test_empty_without_property_ac(self):
        variant = KeyExampleVariant(behavior_ac="ac")
        assert variant.hypothesis_test() == ""

    def test_parametrize_test_empty_without_examples(self):
        variant = KeyExampleVariant(behavior_ac="ac")
        assert variant.parametrize_test() == ""

    def test_parametrize_test_generated_with_examples(self):
        ex = KeyExample(given="x=1", then="result=1", raw="given: x=1, then: result=1")
        variant = KeyExampleVariant(behavior_ac="ac", examples=[ex])
        code = variant.parametrize_test()
        assert "@pytest.mark.parametrize" in code
