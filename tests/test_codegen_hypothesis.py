"""Tests for codegen integration with property-based AC and key-example few-shot context.

The codegen agent uses property specs and key-examples as few-shot context when
generating implementation code.  These tests verify that:
- emit_hypothesis_test produces a valid, runnable Hypothesis test per property AC
- The generated test code embeds the property's generator and predicate
- Key-examples are included in the few-shot context for codegen
- The generated Hypothesis test is syntactically valid Python
"""

from __future__ import annotations

import re

import pytest

from bob.spec_quality.example_grammar import (
    KeyExample,
    PropertyAC,
    emit_hypothesis_test,
    emit_parametrize_test,
    parse_key_example,
    parse_property_ac,
)


# ---------------------------------------------------------------------------
# emit_hypothesis_test — codegen output
# ---------------------------------------------------------------------------


class TestEmitHypothesisTest:
    def test_basic_property_produces_hypothesis_test(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "@given" in result
        assert "from hypothesis import" in result

    def test_generator_embedded_in_given_decorator(self):
        prop = parse_property_ac(
            "property: bounded for st.integers(min_value=0, max_value=100) assert 0 <= x <= 100"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "st.integers(min_value=0, max_value=100)" in result

    def test_predicate_embedded_in_assert(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "assert x >= 0" in result

    def test_function_name_derived_from_property_name(self):
        prop = parse_property_ac(
            "property: my_property for st.integers() assert x > 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "def test_property_my_property" in result

    def test_seed_zero_used_in_settings(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "deriving=0" in result

    def test_non_zero_seed_also_works(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        result = emit_hypothesis_test(prop, seed=42)
        assert "deriving=42" in result

    def test_generated_code_is_valid_python(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        # Must compile without SyntaxError
        compile(result, "<generated>", "exec")

    def test_text_strategy_property(self):
        prop = parse_property_ac(
            "property: text_len for st.text() assert len(s) >= 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "st.text()" in result
        assert "len(s) >= 0" in result

    def test_float_strategy_property(self):
        prop = parse_property_ac(
            "property: finite for st.floats(allow_nan=False) assert not math.isnan(x)"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "st.floats(allow_nan=False)" in result

    def test_settings_decorator_present(self):
        prop = parse_property_ac(
            "property: identity for st.integers() assert x == x"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "@settings(" in result

    def test_hypothesis_import_present(self):
        prop = parse_property_ac(
            "property: pos for st.integers(min_value=1) assert x > 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "from hypothesis import given" in result

    def test_strategies_import_present(self):
        prop = parse_property_ac(
            "property: pos for st.integers(min_value=1) assert x > 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "from hypothesis import strategies as st" in result


# ---------------------------------------------------------------------------
# Few-shot context for codegen
# ---------------------------------------------------------------------------


class TestFewShotContextForCodegen:
    """Codegen uses property specs and key-examples as few-shot context."""

    def test_property_ac_provides_few_shot_info(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        # The hypothesis test itself is the few-shot context for codegen
        ht = emit_hypothesis_test(prop, seed=0)
        # Should contain the property name to guide codegen
        assert "non_negative" in ht

    def test_key_example_given_then_serves_as_few_shot(self):
        ex = parse_key_example({"given": "x=5", "then": "result=25"})
        assert ex is not None
        assert ex.given == "x=5"
        assert ex.then == "result=25"
        # The raw representation provides few-shot context
        assert "x=5" in ex.raw
        assert "result=25" in ex.raw

    def test_multiple_key_examples_provide_varied_context(self):
        examples = [
            parse_key_example({"given": "x=1", "then": "1"}),
            parse_key_example({"given": "x=10", "then": "10"}),
            parse_key_example({"given": "x=-1", "then": "-1"}),
        ]
        for ex in examples:
            assert ex is not None
        # Parametrize test encodes all examples as few-shot context for codegen
        pt = emit_parametrize_test(examples, seed=0)
        assert "x=1" in pt
        assert "x=10" in pt
        assert "x=-1" in pt

    def test_property_and_key_example_together(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        examples = [
            parse_key_example({"given": "0", "then": "0"}),
        ]
        ht = emit_hypothesis_test(prop, seed=0)
        pt = emit_parametrize_test(examples, seed=0)
        # Both are valid Python (can be compiled together conceptually)
        compile(ht, "<ht>", "exec")
        compile(pt, "<pt>", "exec")
        # Both contain the necessary info
        assert "x >= 0" in ht
        assert "@pytest.mark.parametrize" in pt


# ---------------------------------------------------------------------------
# Codegen: one Hypothesis test per property AC
# ---------------------------------------------------------------------------


class TestOneHypothesisTestPerProperty:
    """The spec mandates one Hypothesis test emitted per property AC."""

    def test_one_property_produces_one_test_function(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        # Count 'def test_' occurrences — should be exactly 1
        count = len(re.findall(r"^\s*def test_", result, re.MULTILINE))
        assert count == 1

    def test_test_function_uses_given_decorator(self):
        prop = parse_property_ac(
            "property: pos for st.integers(min_value=1) assert x > 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        lines = result.splitlines()
        given_line = next((l for l in lines if "@given(" in l), None)
        assert given_line is not None, "Expected @given(...) decorator"

    def test_different_properties_produce_different_test_names(self):
        p1 = parse_property_ac("property: alpha for st.integers() assert x > 0")
        p2 = parse_property_ac("property: beta for st.text() assert len(s) >= 0")
        ht1 = emit_hypothesis_test(p1, seed=0)
        ht2 = emit_hypothesis_test(p2, seed=0)
        assert "test_property_alpha" in ht1
        assert "test_property_beta" in ht2
        assert ht1 != ht2
