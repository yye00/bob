"""Tests for bob3.acceptance_criteria.parse_key_example_ac.

Verifies the key_example sub-key parsing: given/then dict and string forms
are correctly handled and exported from bob3.acceptance_criteria.
"""

from __future__ import annotations

import pytest

from bob3.acceptance_criteria import parse_key_example_ac
from bob3.spec_quality.example_grammar import KeyExample


class TestParseKeyExampleACDictForm:
    def test_returns_key_example_for_valid_dict(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert result is not None
        assert isinstance(result, KeyExample)

    def test_given_field_extracted(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert result.given == "x=5"

    def test_then_field_extracted(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert result.then == "result=25"

    def test_raw_is_stored(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert result.raw is not None
        assert "x=5" in result.raw
        assert "result=25" in result.raw

    def test_numeric_values(self):
        result = parse_key_example_ac({"given": "0", "then": "0"})
        assert result is not None
        assert result.given == "0"
        assert result.then == "0"

    def test_empty_given_value_accepted(self):
        result = parse_key_example_ac({"given": "", "then": "expected"})
        assert result is not None
        assert result.given == ""

    def test_empty_then_value_accepted(self):
        result = parse_key_example_ac({"given": "input", "then": ""})
        assert result is not None
        assert result.then == ""


class TestParseKeyExampleACStringForm:
    def test_returns_key_example_for_valid_string(self):
        result = parse_key_example_ac("given: x=5, then: result=25")
        assert result is not None
        assert isinstance(result, KeyExample)

    def test_given_field_extracted_from_string(self):
        result = parse_key_example_ac("given: x=5, then: result=25")
        assert result.given == "x=5"

    def test_then_field_extracted_from_string(self):
        result = parse_key_example_ac("given: x=5, then: result=25")
        assert result.then == "result=25"

    def test_string_without_comma_separator(self):
        result = parse_key_example_ac("given: hello then: world")
        assert result is not None


class TestParseKeyExampleACNoneAndEmpty:
    def test_none_returns_none(self):
        result = parse_key_example_ac(None)
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_key_example_ac("")
        assert result is None

    def test_empty_dict_returns_none(self):
        result = parse_key_example_ac({})
        assert result is None


class TestParseKeyExampleACErrors:
    def test_dict_missing_both_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"wrong_key": "x", "another_wrong": "y"})

    def test_dict_with_only_unrelated_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"foo": "bar", "baz": "qux"})

    def test_does_not_silently_succeed_on_bad_dict(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"not_given": "x", "not_then": "y"})

    def test_value_error_is_raised_not_other_exception(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"unexpected": "data", "other": "field"})


class TestParseKeyExampleACImport:
    def test_function_importable_from_acceptance_criteria(self):
        from bob3.acceptance_criteria import parse_key_example_ac as fn
        assert callable(fn)

    def test_returns_key_example_dataclass(self):
        result = parse_key_example_ac({"given": "a", "then": "b"})
        assert hasattr(result, "given")
        assert hasattr(result, "then")
        assert hasattr(result, "raw")

    def test_key_example_is_frozen(self):
        result = parse_key_example_ac({"given": "a", "then": "b"})
        with pytest.raises((AttributeError, TypeError)):
            result.given = "modified"


class TestParseKeyExampleACIntegration:
    def test_codegen_few_shot_context_available(self):
        """Key examples parsed from dicts work as few-shot context for codegen."""
        examples = [
            {"given": "x=0", "then": "result=0"},
            {"given": "x=1", "then": "result=1"},
            {"given": "x=-1", "then": "result=-1"},
        ]
        parsed = [parse_key_example_ac(e) for e in examples]
        assert all(p is not None for p in parsed)
        assert all(isinstance(p, KeyExample) for p in parsed)

    def test_verifier_parametrize_emission(self):
        """Parsed examples can be used to emit parametrized tests."""
        from bob3.spec_quality.example_grammar import emit_parametrize_test
        examples_raw = [
            {"given": "5", "then": "25"},
            {"given": "0", "then": "0"},
        ]
        parsed = [parse_key_example_ac(e) for e in examples_raw]
        code = emit_parametrize_test(parsed, seed=0)
        assert "@pytest.mark.parametrize" in code
        assert "seed=0" in code
