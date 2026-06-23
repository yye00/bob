"""Tests for verifier integration: one Hypothesis test per property, one parametrized
pytest per key_example with seed=0.

The verifier:
- Emits one Hypothesis test per property AC
- Emits one @pytest.mark.parametrize test per key_example with seed=0
- Uses seed=0 for reproducibility
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.example_grammar import (
    KeyExample,
    PropertyAC,
    emit_hypothesis_test,
    emit_parametrize_test,
    parse_key_example,
    parse_property_ac,
)


# ---------------------------------------------------------------------------
# Verifier: emit one Hypothesis test per property AC
# ---------------------------------------------------------------------------


class TestVerifierHypothesisEmission:
    """Verifier emits one Hypothesis test per property AC."""

    def test_verifier_emits_hypothesis_test_for_property(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert result is not None
        assert len(result) > 0
        assert "@given" in result

    def test_verifier_uses_seed_zero(self):
        prop = parse_property_ac(
            "property: bounded for st.integers(min_value=0, max_value=10) assert 0 <= x <= 10"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "deriving=0" in result

    def test_verifier_hypothesis_test_is_syntactically_valid(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        compile(result, "<hypothesis_test>", "exec")

    def test_verifier_embeds_property_generator(self):
        prop = parse_property_ac(
            "property: pos for st.integers(min_value=1) assert x > 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "st.integers(min_value=1)" in result

    def test_verifier_embeds_property_predicate(self):
        prop = parse_property_ac(
            "property: positive for st.integers(min_value=1) assert x > 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "x > 0" in result

    def test_verifier_function_name_from_property_name(self):
        prop = parse_property_ac(
            "property: identity_check for st.integers() assert x == x"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "def test_property_identity_check" in result

    def test_verifier_includes_settings_decorator(self):
        prop = parse_property_ac(
            "property: non_negative for st.integers() assert x >= 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "@settings(" in result

    def test_verifier_handles_text_strategy(self):
        prop = parse_property_ac(
            "property: non_empty for st.text(min_size=1) assert len(s) > 0"
        )
        result = emit_hypothesis_test(prop, seed=0)
        assert "st.text(min_size=1)" in result
        assert "len(s) > 0" in result


# ---------------------------------------------------------------------------
# Verifier: emit one parametrized pytest per key_example with seed=0
# ---------------------------------------------------------------------------


class TestVerifierParametrizedEmission:
    """Verifier emits one @pytest.mark.parametrize test per key_example with seed=0."""

    def test_verifier_emits_parametrize_for_single_example(self):
        ex = parse_key_example({"given": "x=5", "then": "result=25"})
        result = emit_parametrize_test([ex], seed=0)
        assert "@pytest.mark.parametrize" in result

    def test_verifier_parametrize_uses_seed_zero(self):
        ex = parse_key_example({"given": "x=5", "then": "result=25"})
        result = emit_parametrize_test([ex], seed=0)
        assert "seed=0" in result

    def test_verifier_parametrize_includes_given_value(self):
        ex = parse_key_example({"given": "x=5", "then": "result=25"})
        result = emit_parametrize_test([ex], seed=0)
        assert "x=5" in result

    def test_verifier_parametrize_includes_then_value(self):
        ex = parse_key_example({"given": "x=5", "then": "result=25"})
        result = emit_parametrize_test([ex], seed=0)
        assert "result=25" in result

    def test_verifier_parametrize_multiple_examples(self):
        examples = [
            parse_key_example({"given": "0", "then": "0"}),
            parse_key_example({"given": "1", "then": "1"}),
            parse_key_example({"given": "-1", "then": "-1"}),
        ]
        result = emit_parametrize_test(examples, seed=0)
        assert "@pytest.mark.parametrize" in result
        assert "'0'" in result or '"0"' in result
        assert "'1'" in result or '"1"' in result
        assert "'-1'" in result or '"-1"' in result

    def test_verifier_parametrize_is_valid_python(self):
        examples = [
            parse_key_example({"given": "x=1", "then": "1"}),
            parse_key_example({"given": "x=0", "then": "0"}),
        ]
        result = emit_parametrize_test(examples, seed=0)
        compile(result, "<parametrize_test>", "exec")

    def test_verifier_empty_examples_returns_empty_string(self):
        result = emit_parametrize_test([], seed=0)
        assert result == ""

    def test_verifier_parametrize_imports_pytest(self):
        ex = parse_key_example({"given": "x=5", "then": "result=25"})
        result = emit_parametrize_test([ex], seed=0)
        assert "import pytest" in result

    def test_verifier_parametrize_test_has_function_def(self):
        ex = parse_key_example({"given": "x=5", "then": "result=25"})
        result = emit_parametrize_test([ex], seed=0)
        assert "def test_" in result

    def test_verifier_parametrize_with_string_form_example(self):
        ex = parse_key_example("given: x=5, then: result=25")
        assert ex is not None
        result = emit_parametrize_test([ex], seed=0)
        assert "@pytest.mark.parametrize" in result
        assert "seed=0" in result


# ---------------------------------------------------------------------------
# Integration: property + key_examples via the main integration function
# ---------------------------------------------------------------------------


class TestVerifierIntegration:
    """Integration tests combining property AC and key_example processing."""

    def test_property_ac_produces_hypothesis_test(self):
        from bob3.key_examples_property_based_ac_variant import (
            key_examples_property_based_ac_variant,
        )

        result = key_examples_property_based_ac_variant(
            property_ac="property: non_negative for st.integers() assert x >= 0",
            key_examples=[],
        )
        assert "@given" in result["hypothesis_test"]

    def test_key_examples_produce_parametrize_test(self):
        from bob3.key_examples_property_based_ac_variant import (
            key_examples_property_based_ac_variant,
        )

        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "0", "then": "0"}],
        )
        assert "@pytest.mark.parametrize" in result["parametrize_test"]

    def test_both_emitted_when_both_provided(self):
        from bob3.key_examples_property_based_ac_variant import (
            key_examples_property_based_ac_variant,
        )

        result = key_examples_property_based_ac_variant(
            property_ac="property: pos for st.integers(min_value=1) assert x > 0",
            key_examples=[{"given": "1", "then": "1"}, {"given": "0", "then": "0"}],
        )
        assert "@given" in result["hypothesis_test"]
        assert "@pytest.mark.parametrize" in result["parametrize_test"]
        assert "seed=0" in result["parametrize_test"]

    def test_hypothesis_test_seed_is_zero(self):
        from bob3.key_examples_property_based_ac_variant import (
            key_examples_property_based_ac_variant,
        )

        result = key_examples_property_based_ac_variant(
            property_ac="property: non_negative for st.integers() assert x >= 0",
            key_examples=[],
        )
        assert "deriving=0" in result["hypothesis_test"]

    def test_parametrize_test_seed_is_zero(self):
        from bob3.key_examples_property_based_ac_variant import (
            key_examples_property_based_ac_variant,
        )

        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "x=1", "then": "1"}],
        )
        assert "seed=0" in result["parametrize_test"]
