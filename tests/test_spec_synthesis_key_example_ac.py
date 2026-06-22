"""Tests for bob3.spec_synthesis.parse_key_example_ac — key_example sub-key grammar."""

from __future__ import annotations

import pytest

from bob3.spec_synthesis import parse_key_example_ac
from bob3.spec_quality.example_grammar import KeyExample


class TestParseKeyExampleACDictForm:
    def test_valid_dict_returns_key_example(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert result is not None
        assert isinstance(result, KeyExample)

    def test_given_extracted_correctly(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert result.given == "x=5"

    def test_then_extracted_correctly(self):
        result = parse_key_example_ac({"given": "x=5", "then": "result=25"})
        assert result.then == "result=25"

    def test_numeric_values(self):
        result = parse_key_example_ac({"given": "0", "then": "0"})
        assert result is not None
        assert result.given == "0"

    def test_empty_dict_returns_none(self):
        result = parse_key_example_ac({})
        assert result is None

    def test_dict_missing_both_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"wrong": "a", "bad": "b"})

    def test_dict_with_only_unrelated_keys_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_key_example_ac({"foo": "bar"})

    def test_case_insensitive_given_key(self):
        result = parse_key_example_ac({"Given": "input", "Then": "output"})
        assert result is not None

    def test_missing_only_then_still_returns_result(self):
        # dict with 'given' but not 'then' — the parser handles partial keys
        result = parse_key_example_ac({"given": "x", "then": "y"})
        assert result is not None


class TestParseKeyExampleACStringForm:
    def test_valid_string_returns_key_example(self):
        result = parse_key_example_ac("given: x=5, then: result=25")
        assert result is not None
        assert isinstance(result, KeyExample)

    def test_string_given_extracted(self):
        result = parse_key_example_ac("given: hello, then: world")
        assert result is not None
        assert result.given == "hello"

    def test_string_then_extracted(self):
        result = parse_key_example_ac("given: hello, then: world")
        assert result is not None
        assert result.then == "world"

    def test_empty_string_returns_none(self):
        result = parse_key_example_ac("")
        assert result is None

    def test_none_returns_none(self):
        result = parse_key_example_ac(None)
        assert result is None

    def test_plain_string_without_given_then_returns_none(self):
        result = parse_key_example_ac("just some text")
        assert result is None

    def test_string_with_zero_value(self):
        result = parse_key_example_ac("given: 0, then: 0")
        assert result is not None
        assert result.given == "0"


class TestParseKeyExampleACReturnType:
    def test_raw_field_set_for_dict_input(self):
        result = parse_key_example_ac({"given": "a", "then": "b"})
        assert result is not None
        assert "given" in result.raw.lower()
        assert "then" in result.raw.lower()

    def test_raw_field_set_for_string_input(self):
        ac = "given: a, then: b"
        result = parse_key_example_ac(ac)
        assert result is not None
        assert result.raw == ac

    def test_does_not_silently_succeed_on_bad_dict(self):
        with pytest.raises(ValueError):
            result = parse_key_example_ac({"not_given": "x", "not_then": "y"})
            pytest.fail(f"Expected ValueError, got {result!r}")
