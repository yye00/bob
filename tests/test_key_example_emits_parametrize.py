"""Tests for key_example: sub-key grammar → emit_parametrize_test.

Verifies:
- parse_key_example handles dict and string inputs.
- emit_parametrize_test produces valid pytest.mark.parametrize source.
- Fixed seed=0 is recorded in a comment.
- Empty example lists produce no test code (graceful).
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.example_grammar import (
    KeyExample,
    emit_parametrize_test,
    parse_key_example,
)


# ---------------------------------------------------------------------------
# parse_key_example
# ---------------------------------------------------------------------------


class TestParseKeyExample:
    def test_dict_with_given_then(self):
        result = parse_key_example({"given": "x=5", "then": "result=25"})
        assert result is not None
        assert isinstance(result, KeyExample)
        assert result.given == "x=5"
        assert result.then == "result=25"

    def test_dict_with_integer_values(self):
        result = parse_key_example({"given": 0, "then": 0})
        assert result is not None
        assert result.given == "0"
        assert result.then == "0"

    def test_dict_missing_then_returns_none(self):
        assert parse_key_example({"given": "x=5"}) is None

    def test_dict_missing_given_returns_none(self):
        assert parse_key_example({"then": "result=25"}) is None

    def test_dict_empty_returns_none(self):
        assert parse_key_example({}) is None

    def test_string_given_then(self):
        result = parse_key_example("given: x=5, then: result=25")
        assert result is not None
        assert result.given == "x=5"
        assert result.then == "result=25"

    def test_string_given_then_without_comma(self):
        result = parse_key_example("given: empty_string then: empty_output")
        assert result is not None
        assert "empty_string" in result.given
        assert "empty_output" in result.then

    def test_string_case_insensitive(self):
        result = parse_key_example("Given: x=0, Then: result=0")
        assert result is not None
        assert result.given == "x=0"
        assert result.then == "result=0"

    def test_string_missing_then_returns_none(self):
        assert parse_key_example("given: x=5") is None

    def test_none_returns_none(self):
        assert parse_key_example(None) is None  # type: ignore[arg-type]

    def test_raw_field_set(self):
        result = parse_key_example({"given": "x=1", "then": "y=2"})
        assert result is not None
        assert result.raw != ""

    def test_dict_with_Given_capitalized(self):
        result = parse_key_example({"Given": "x=5", "Then": "result=25"})
        assert result is not None
        assert result.given == "x=5"

    def test_boundary_value_zero(self):
        result = parse_key_example({"given": "x=0", "then": "result=0"})
        assert result is not None
        assert "0" in result.given

    def test_boundary_value_negative(self):
        result = parse_key_example({"given": "x=-1", "then": "error=ValueError"})
        assert result is not None
        assert "-1" in result.given


# ---------------------------------------------------------------------------
# emit_parametrize_test
# ---------------------------------------------------------------------------


class TestEmitParametrizeTest:
    def _make_examples(self, pairs):
        return [
            KeyExample(given=str(g), then=str(t), raw=f"given: {g}, then: {t}")
            for g, t in pairs
        ]

    def test_emitted_code_contains_parametrize(self):
        examples = self._make_examples([("x=5", "result=25")])
        code = emit_parametrize_test(examples)
        assert "@pytest.mark.parametrize" in code

    def test_emitted_code_imports_pytest(self):
        examples = self._make_examples([("x=1", "result=1")])
        code = emit_parametrize_test(examples)
        assert "import pytest" in code

    def test_emitted_code_contains_given_val(self):
        examples = self._make_examples([("x=5", "result=25")])
        code = emit_parametrize_test(examples)
        assert "given_val" in code

    def test_emitted_code_contains_expected(self):
        examples = self._make_examples([("x=5", "result=25")])
        code = emit_parametrize_test(examples)
        assert "expected" in code

    def test_multiple_examples_all_appear(self):
        examples = self._make_examples([("x=0", "result=0"), ("x=1", "result=1"), ("x=-1", "error")])
        code = emit_parametrize_test(examples)
        assert "x=0" in code
        assert "x=1" in code
        assert "x=-1" in code

    def test_empty_examples_returns_empty_string(self):
        assert emit_parametrize_test([]) == ""

    def test_seed_0_in_comment(self):
        examples = self._make_examples([("x=5", "25")])
        code = emit_parametrize_test(examples)
        assert "seed=0" in code

    def test_custom_seed_in_comment(self):
        examples = self._make_examples([("x=5", "25")])
        code = emit_parametrize_test(examples, seed=42)
        assert "seed=42" in code

    def test_custom_test_name(self):
        examples = self._make_examples([("x=5", "25")])
        code = emit_parametrize_test(examples, test_name="test_square_function")
        assert "test_square_function" in code

    def test_emitted_code_is_valid_python(self):
        examples = self._make_examples([("x=5", "25"), ("x=0", "0")])
        code = emit_parametrize_test(examples)
        compile(code, "<string>", "exec")

    def test_emitted_code_has_assert(self):
        examples = self._make_examples([("x=5", "25")])
        code = emit_parametrize_test(examples)
        assert "assert" in code

    def test_function_def_present(self):
        examples = self._make_examples([("x=5", "25")])
        code = emit_parametrize_test(examples, test_name="my_test")
        assert "def my_test" in code
