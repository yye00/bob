"""Tests for key_examples_property_based_ac_variant.

Tests cover:
- parse_property_ac: seventh AC grammar ``property: <name> for <generator> assert <predicate>``
- key_example: sub-key on behavior ACs
- Codegen uses them as few-shot context
- Verifier emits one Hypothesis test per property
- Verifier emits one parametrized pytest per key_example with seed=0
- Boundary examples are required for numeric-range ACs
"""

from __future__ import annotations

import pytest

from bob.key_examples_property_based_ac_variant import key_examples_property_based_ac_variant


# ---------------------------------------------------------------------------
# Integration: key_examples_property_based_ac_variant
# ---------------------------------------------------------------------------


def test_key_examples_property_based_ac_variant():
    """Primary AC test: the integration function returns a valid result dict."""
    result = key_examples_property_based_ac_variant(
        property_ac="property: non_negative for st.integers() assert x >= 0",
        key_examples=[
            {"given": "x=5", "then": "result=25"},
            {"given": "x=0", "then": "result=0"},
        ],
    )
    assert result is not None
    assert isinstance(result, dict)
    assert "hypothesis_test" in result
    assert "parametrize_test" in result
    assert "property" in result
    assert "key_examples" in result


class TestPropertyACGrammar:
    """Tests for the seventh AC grammar: property: <name> for <generator> assert <predicate>."""

    def test_basic_property_ac_parsed(self):
        result = key_examples_property_based_ac_variant(
            property_ac="property: non_negative for st.integers() assert x >= 0",
            key_examples=[],
        )
        prop = result["property"]
        assert prop.name == "non_negative"
        assert "st.integers()" in prop.generator
        assert "x >= 0" in prop.predicate

    def test_property_ac_with_text_strategy(self):
        result = key_examples_property_based_ac_variant(
            property_ac="property: non_empty for st.text() assert len(x) >= 0",
            key_examples=[],
        )
        prop = result["property"]
        assert prop.name == "non_empty"
        assert "st.text()" in prop.generator

    def test_hypothesis_test_emitted_per_property(self):
        result = key_examples_property_based_ac_variant(
            property_ac="property: always_true for st.integers() assert True",
            key_examples=[],
        )
        ht = result["hypothesis_test"]
        assert "@given" in ht
        assert "from hypothesis import" in ht

    def test_hypothesis_test_contains_predicate(self):
        result = key_examples_property_based_ac_variant(
            property_ac="property: bounded for st.integers(min_value=0) assert x >= 0",
            key_examples=[],
        )
        ht = result["hypothesis_test"]
        assert "x >= 0" in ht

    def test_hypothesis_test_is_valid_python(self):
        result = key_examples_property_based_ac_variant(
            property_ac="property: non_negative for st.integers() assert x >= 0",
            key_examples=[],
        )
        compile(result["hypothesis_test"], "<string>", "exec")

    def test_none_property_ac_handled(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "x=1", "then": "y=1"}],
        )
        assert result["property"] is None
        assert result["hypothesis_test"] == ""

    def test_non_property_ac_string_returns_none_property(self):
        result = key_examples_property_based_ac_variant(
            property_ac="pytest: tests/test_foo.py",
            key_examples=[],
        )
        assert result["property"] is None


class TestKeyExampleSubKey:
    """Tests for key_example: sub-key on behavior ACs."""

    def test_key_examples_parsed(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[
                {"given": "x=5", "then": "result=25"},
            ],
        )
        examples = result["key_examples"]
        assert len(examples) == 1
        assert examples[0].given == "x=5"
        assert examples[0].then == "result=25"

    def test_multiple_key_examples(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[
                {"given": "x=0", "then": "result=0"},
                {"given": "x=1", "then": "result=1"},
                {"given": "x=-1", "then": "error"},
            ],
        )
        assert len(result["key_examples"]) == 3

    def test_parametrize_test_emitted_per_key_example(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[
                {"given": "x=5", "then": "25"},
            ],
        )
        pt = result["parametrize_test"]
        assert "@pytest.mark.parametrize" in pt
        assert "import pytest" in pt

    def test_parametrize_test_seed_zero(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "x=5", "then": "25"}],
        )
        assert "seed=0" in result["parametrize_test"]

    def test_empty_key_examples_returns_empty_parametrize(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
        )
        assert result["parametrize_test"] == ""

    def test_parametrize_test_is_valid_python(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[
                {"given": "x=5", "then": "25"},
                {"given": "x=0", "then": "0"},
            ],
        )
        compile(result["parametrize_test"], "<string>", "exec")

    def test_key_example_string_format_supported(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=["given: x=5, then: result=25"],
        )
        examples = result["key_examples"]
        assert len(examples) == 1
        assert "x=5" in examples[0].given

    def test_invalid_key_examples_skipped(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[
                {"given": "x=5", "then": "25"},
                {"no_given": "bad"},
                None,
            ],
        )
        assert len(result["key_examples"]) == 1


class TestBoundaryRequirements:
    """Tests for boundary-example requirements on numeric-range ACs."""

    def test_numeric_ac_requires_boundary(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "x=5", "then": "25"}],
            behavior_ac="system transforms integer input to output range 0-100",
        )
        assert result["boundary_required"] is True

    def test_numeric_ac_with_boundary_example_satisfied(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[
                {"given": "x=0", "then": "0"},
                {"given": "x=100", "then": "100"},
            ],
            behavior_ac="system transforms integer input to output range 0-100",
        )
        assert result["boundary_satisfied"] is True

    def test_non_numeric_ac_does_not_require_boundary(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
            behavior_ac="system logs user authentication event",
        )
        assert result["boundary_required"] is False

    def test_no_behavior_ac_no_boundary_check(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
        )
        assert result["boundary_required"] is False
        assert result["boundary_satisfied"] is True


class TestFewShotContext:
    """Tests for codegen few-shot context returned by the function."""

    def test_few_shot_context_key_present(self):
        result = key_examples_property_based_ac_variant(
            property_ac="property: non_negative for st.integers() assert x >= 0",
            key_examples=[{"given": "x=1", "then": "1"}],
        )
        assert "few_shot_context" in result

    def test_few_shot_context_contains_property_info(self):
        result = key_examples_property_based_ac_variant(
            property_ac="property: positive for st.integers(min_value=1) assert x > 0",
            key_examples=[],
        )
        ctx = result["few_shot_context"]
        assert "positive" in ctx or "property" in ctx.lower()

    def test_few_shot_context_contains_key_example_info(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "x=5", "then": "25"}],
        )
        ctx = result["few_shot_context"]
        assert "x=5" in ctx or "key_example" in ctx.lower() or "given" in ctx.lower()

    def test_few_shot_context_is_string(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
        )
        assert isinstance(result["few_shot_context"], str)
