"""Tests for key-example parametrization (``key_example:`` sub-key on behavior ACs).

Verifies that:
- ``extract_key_examples`` in ``bob.acceptance_criteria.key_example`` parses
  dict and string entries into :class:`KeyExample` objects.
- ``emit_parametrize_tests`` produces valid ``@pytest.mark.parametrize`` source.
- The verifier emits one parametrize test per key-example with ``seed=0``.
- Integration via ``key_examples_property_based_ac_variant`` wires up correctly.
"""

from __future__ import annotations

import pytest

from bob.acceptance_criteria.key_example import (
    KeyExample,
    check_boundary_requirement,
    emit_parametrize_tests,
    extract_key_examples,
)
from bob.key_examples_property_based_ac_variant import key_examples_property_based_ac_variant
from bob.spec_quality.example_grammar import emit_parametrize_test


# ---------------------------------------------------------------------------
# extract_key_examples
# ---------------------------------------------------------------------------


class TestExtractKeyExamples:
    def test_dict_entries_parsed(self):
        entries = [{"given": "x=1", "then": "1"}, {"given": "x=2", "then": "4"}]
        examples = extract_key_examples(entries)
        assert len(examples) == 2
        assert all(isinstance(e, KeyExample) for e in examples)

    def test_string_entries_parsed(self):
        entries = ["given: x=1, then: 1", "given: x=2, then: 4"]
        examples = extract_key_examples(entries)
        assert len(examples) == 2

    def test_none_entries_skipped(self):
        examples = extract_key_examples([None, {"given": "x=1", "then": "1"}, None])
        assert len(examples) == 1

    def test_empty_list_returns_empty(self):
        assert extract_key_examples([]) == []

    def test_none_input_returns_empty(self):
        assert extract_key_examples(None) == []

    def test_given_field_preserved(self):
        examples = extract_key_examples([{"given": "my_input", "then": "my_output"}])
        assert examples[0].given == "my_input"

    def test_then_field_preserved(self):
        examples = extract_key_examples([{"given": "x", "then": "y"}])
        assert examples[0].then == "y"

    def test_mixed_dict_and_string_entries(self):
        entries = [{"given": "a", "then": "b"}, "given: c, then: d"]
        examples = extract_key_examples(entries)
        assert len(examples) == 2

    def test_invalid_string_entries_skipped(self):
        entries = ["not_a_key_example", "also not one"]
        examples = extract_key_examples(entries)
        assert examples == []

    def test_strict_false_skips_bad_dict_silently(self):
        entries = [{"bad_key": "value"}, {"given": "x", "then": "y"}]
        examples = extract_key_examples(entries, strict=False)
        assert len(examples) == 1

    def test_strict_true_raises_on_bad_dict(self):
        entries = [{"bad_key": "value"}]
        with pytest.raises(ValueError):
            extract_key_examples(entries, strict=True)


# ---------------------------------------------------------------------------
# emit_parametrize_tests
# ---------------------------------------------------------------------------


class TestEmitParametrizeTests:
    def _make_example(self, given: str, then: str) -> KeyExample:
        return KeyExample(given=given, then=then, raw=f"given: {given}, then: {then}")

    def test_empty_examples_returns_empty_string(self):
        assert emit_parametrize_tests([]) == ""

    def test_single_example_produces_parametrize_decorator(self):
        code = emit_parametrize_tests([self._make_example("1", "1")])
        assert "@pytest.mark.parametrize" in code

    def test_two_examples_in_output(self):
        examples = [self._make_example("1", "1"), self._make_example("2", "4")]
        code = emit_parametrize_tests(examples)
        assert "1" in code
        assert "4" in code

    def test_seed_0_in_output(self):
        code = emit_parametrize_tests([self._make_example("x", "y")], seed=0)
        assert "0" in code

    def test_output_is_valid_python(self):
        code = emit_parametrize_tests([self._make_example("1", "1")])
        compile(code, "<test>", "exec")

    def test_custom_test_name_used(self):
        code = emit_parametrize_tests(
            [self._make_example("x", "y")], test_name="test_my_custom"
        )
        assert "test_my_custom" in code

    def test_pytest_import_present(self):
        code = emit_parametrize_tests([self._make_example("x", "y")])
        assert "import pytest" in code or "pytest" in code


# ---------------------------------------------------------------------------
# check_boundary_requirement
# ---------------------------------------------------------------------------


class TestCheckBoundaryRequirement:
    def _make_example(self, given: str, then: str) -> KeyExample:
        return KeyExample(given=given, then=then, raw=f"given: {given}, then: {then}")

    def test_non_numeric_ac_satisfied_without_boundary(self):
        result = check_boundary_requirement(
            "system logs authentication event", []
        )
        assert result is True

    def test_numeric_ac_not_satisfied_without_boundary(self):
        result = check_boundary_requirement(
            "system converts integer to range value", []
        )
        assert result is False

    def test_numeric_ac_satisfied_with_zero_example(self):
        result = check_boundary_requirement(
            "system converts integer to range value",
            [self._make_example("0", "0")],
        )
        assert result is True


# ---------------------------------------------------------------------------
# Integration: parametrize tests emitted per key-example with seed=0
# ---------------------------------------------------------------------------


class TestIntegrationParametrize:
    def test_one_example_yields_parametrize_test(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "x=1", "then": "1"}],
        )
        assert "@pytest.mark.parametrize" in result["parametrize_test"]

    def test_two_examples_both_in_parametrize_test(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[
                {"given": "x=1", "then": "1"},
                {"given": "x=2", "then": "4"},
            ],
        )
        code = result["parametrize_test"]
        assert "x=1" in code
        assert "x=2" in code

    def test_seed_zero_in_parametrize_test(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "x=1", "then": "1"}],
        )
        assert "0" in result["parametrize_test"]

    def test_no_examples_yields_empty_parametrize_test(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[],
        )
        assert result["parametrize_test"] == ""

    def test_parametrize_test_is_valid_python(self):
        result = key_examples_property_based_ac_variant(
            property_ac=None,
            key_examples=[{"given": "1", "then": "1"}],
        )
        code = result["parametrize_test"]
        compile(code, "<test>", "exec")
