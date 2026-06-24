"""Error-path tests for bob.acceptance_criteria module.

Tests that invalid inputs raise ValueError and do not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.acceptance_criteria.property_based import PropertyBasedAC, PropertyParseError
from bob.acceptance_criteria.key_examples import KeyExampleAC
from bob.acceptance_criteria.registry import get_handler, register, AC_REGISTRY


class TestPropertyBasedACErrorPaths:
    def test_from_string_missing_for_raises_value_error(self):
        with pytest.raises(ValueError):
            PropertyBasedAC.from_string("property: p assert x > 0")

    def test_from_string_missing_assert_raises_value_error(self):
        with pytest.raises(ValueError):
            PropertyBasedAC.from_string("property: p for st.integers()")

    def test_from_string_keyword_only_raises_value_error(self):
        with pytest.raises(ValueError):
            PropertyBasedAC.from_string("property:")

    def test_from_string_missing_predicate_raises_value_error(self):
        with pytest.raises(ValueError):
            PropertyBasedAC.from_string("property: p for st.integers() assert")

    def test_property_parse_error_is_value_error_subclass(self):
        assert issubclass(PropertyParseError, ValueError)

    def test_try_parse_malformed_property_raises(self):
        with pytest.raises(ValueError):
            PropertyBasedAC.try_parse("property: p assert x > 0")

    def test_try_parse_malformed_missing_assert_raises(self):
        with pytest.raises(ValueError):
            PropertyBasedAC.try_parse("property: p for st.integers()")


class TestKeyExampleACErrorPaths:
    def test_strict_mode_dict_missing_both_keys_raises(self):
        with pytest.raises(ValueError):
            KeyExampleAC.from_entries(
                [{"wrong_key": "x", "another_key": "y"}],
                strict=True,
            )

    def test_strict_mode_empty_keys_dict_raises(self):
        with pytest.raises(ValueError):
            KeyExampleAC.from_entries([{"foo": "bar"}], strict=True)

    def test_non_strict_mode_malformed_dict_skipped(self):
        ac = KeyExampleAC.from_entries([{"wrong_key": "x"}], strict=False)
        assert ac.examples == []

    def test_valid_dict_does_not_raise(self):
        ac = KeyExampleAC.from_entries([{"given": "x=5", "then": "25"}])
        assert len(ac.examples) == 1

    def test_strict_valid_dict_does_not_raise(self):
        ac = KeyExampleAC.from_entries([{"given": "x=5", "then": "25"}], strict=True)
        assert len(ac.examples) == 1


class TestRegistryErrorPaths:
    def test_get_handler_unknown_grammar_returns_none(self):
        assert get_handler("nonexistent_grammar") is None

    def test_register_empty_grammar_raises(self):
        with pytest.raises(ValueError):
            register("", PropertyBasedAC)

    def test_register_non_class_raises(self):
        with pytest.raises(ValueError):
            register("my_grammar", "not_a_class")  # type: ignore[arg-type]

    def test_register_and_get_roundtrip(self):
        register("test_grammar_error_path", PropertyBasedAC)
        assert get_handler("test_grammar_error_path") is PropertyBasedAC
        # Clean up
        del AC_REGISTRY["test_grammar_error_path"]

    def test_property_handler_registered(self):
        assert get_handler("property") is PropertyBasedAC

    def test_key_example_handler_registered(self):
        assert get_handler("key_example") is KeyExampleAC
