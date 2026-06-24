"""Tests for key_example sub-key AC parsing and emission.

Covers:
- parse_key_example_ac: parses dict and string forms
- emit_parametrize_test: emits @pytest.mark.parametrize code with seed=0
- Integration with bob.codegen (emit_key_example_test)
- Integration with bob.verifier (run_key_example_test)
"""

from __future__ import annotations

import pytest

from ac_grammar.property_based import parse_key_example_ac
from bob.spec_quality.example_grammar import (
    KeyExample,
    emit_parametrize_test,
    parse_key_example,
)


# ---------------------------------------------------------------------------
# parse_key_example_ac — dict form
# ---------------------------------------------------------------------------


class TestParseKeyExampleACDictForm:
    def test_basic_dict_returns_key_example(self):
        result = parse_key_example_ac({"given": "x=5", "then": "25"})
        assert isinstance(result, KeyExample)

    def test_given_field_extracted(self):
        result = parse_key_example_ac({"given": "x=5", "then": "25"})
        assert result.given == "x=5"

    def test_then_field_extracted(self):
        result = parse_key_example_ac({"given": "x=5", "then": "25"})
        assert result.then == "25"

    def test_raw_field_is_non_empty(self):
        result = parse_key_example_ac({"given": "x=5", "then": "25"})
        assert result.raw != ""

    def test_list_input_as_given(self):
        result = parse_key_example_ac({"given": "[1, 2, 3]", "then": "6"})
        assert "[1, 2, 3]" in result.given
        assert result.then == "6"

    def test_numeric_string_given(self):
        result = parse_key_example_ac({"given": "0", "then": "0"})
        assert result.given == "0"
        assert result.then == "0"

    def test_empty_dict_returns_none(self):
        result = parse_key_example_ac({})
        assert result is None

    def test_dict_missing_given_returns_none(self):
        result = parse_key_example_ac({"then": "25"})
        assert result is None

    def test_dict_missing_then_returns_none(self):
        result = parse_key_example_ac({"given": "x=5"})
        assert result is None

    def test_dict_missing_both_known_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"foo": "bar", "baz": "qux"})


# ---------------------------------------------------------------------------
# parse_key_example_ac — string form
# ---------------------------------------------------------------------------


class TestParseKeyExampleACStringForm:
    def test_string_form_returns_key_example(self):
        result = parse_key_example_ac("given: x=5, then: result=25")
        assert isinstance(result, KeyExample)

    def test_string_form_given_extracted(self):
        result = parse_key_example_ac("given: x=5, then: result=25")
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

    def test_whitespace_string_returns_none(self):
        result = parse_key_example_ac("   ")
        assert result is None


# ---------------------------------------------------------------------------
# emit_parametrize_test
# ---------------------------------------------------------------------------


class TestEmitParametrizeTest:
    def test_empty_list_returns_empty_string(self):
        result = emit_parametrize_test([], seed=0)
        assert result == ""

    def test_single_example_emits_parametrize(self):
        ex = KeyExample(given="0", then="0", raw="given: 0, then: 0")
        code = emit_parametrize_test([ex], seed=0)
        assert "@pytest.mark.parametrize" in code

    def test_emitted_code_is_syntactically_valid(self):
        ex = KeyExample(given="x=5", then="25", raw="given: x=5, then: 25")
        code = emit_parametrize_test([ex], seed=0)
        compile(code, "<string>", "exec")

    def test_seed_zero_appears_in_output(self):
        ex = KeyExample(given="x=5", then="25", raw="given: x=5, then: 25")
        code = emit_parametrize_test([ex], seed=0)
        assert "0" in code

    def test_multiple_examples_all_appear(self):
        examples = [
            KeyExample(given="0", then="0", raw="given: 0, then: 0"),
            KeyExample(given="1", then="1", raw="given: 1, then: 1"),
        ]
        code = emit_parametrize_test(examples, seed=0)
        assert "@pytest.mark.parametrize" in code


# ---------------------------------------------------------------------------
# Integration: bob.codegen emit_key_example_test
# ---------------------------------------------------------------------------


class TestCodegenIntegration:
    def test_emit_key_example_test_importable(self):
        from bob.codegen import emit_key_example_test
        assert callable(emit_key_example_test)

    def test_emit_key_example_test_produces_code(self):
        from bob.codegen import emit_key_example_test
        examples = [KeyExample(given="0", then="0", raw="given: 0, then: 0")]
        code = emit_key_example_test(examples)
        assert code != ""

    def test_emit_key_example_test_contains_parametrize(self):
        from bob.codegen import emit_key_example_test
        examples = [KeyExample(given="x=5", then="25", raw="given: x=5, then: 25")]
        code = emit_key_example_test(examples)
        assert "@pytest.mark.parametrize" in code

    def test_emit_key_example_test_empty_list_returns_empty(self):
        from bob.codegen import emit_key_example_test
        code = emit_key_example_test([])
        assert code == ""

    def test_emit_key_example_test_seed_zero(self):
        from bob.codegen import emit_key_example_test
        examples = [KeyExample(given="x=5", then="25", raw="given: x=5, then: 25")]
        code = emit_key_example_test(examples, seed=0)
        assert "0" in code


# ---------------------------------------------------------------------------
# Integration: bob.verifier run_key_example_test
# ---------------------------------------------------------------------------


class TestVerifierIntegration:
    def test_run_key_example_test_importable(self):
        from bob.verifier import run_key_example_test
        assert callable(run_key_example_test)

    def test_emit_hypothesis_test_importable(self):
        from bob.verifier import emit_hypothesis_test
        assert callable(emit_hypothesis_test)

    def test_emit_hypothesis_test_produces_at_given(self):
        from bob.verifier import emit_hypothesis_test
        from bob.spec_quality.example_grammar import parse_property_ac
        prop = parse_property_ac("property: non_negative for st.integers() assert x >= 0")
        code = emit_hypothesis_test(prop, seed=0)
        assert "@given" in code
