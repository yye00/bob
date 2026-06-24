"""Boundary-case tests for bob.prose_connector_registry.

AC: boundary case — empty, zero, or minimum input returns a well-defined result
rather than raising.
"""

from __future__ import annotations

from bob.prose_connector_registry import get_policy_verb_connectors, is_feature_hash_reference


class TestGetPolicyVerbConnectorsBoundary:
    def test_returns_frozenset_on_call(self):
        result = get_policy_verb_connectors()
        assert isinstance(result, frozenset)

    def test_returns_non_empty_frozenset(self):
        result = get_policy_verb_connectors()
        assert len(result) > 0

    def test_all_tokens_are_strings(self):
        result = get_policy_verb_connectors()
        for token in result:
            assert isinstance(token, str), f"Expected str, got {type(token)}"

    def test_minimum_token_length(self):
        result = get_policy_verb_connectors()
        for token in result:
            assert len(token) >= 1, f"Token too short: {token!r}"

    def test_calling_multiple_times_is_stable(self):
        r1 = get_policy_verb_connectors()
        r2 = get_policy_verb_connectors()
        assert r1 == r2

    def test_is_frozen(self):
        result = get_policy_verb_connectors()
        try:
            result.add("__test__")  # type: ignore[union-attr]
            assert False, "frozenset should not be mutable"
        except (AttributeError, TypeError):
            pass


class TestIsFeatureHashReferenceBoundary:
    def test_empty_string_returns_false(self):
        assert is_feature_hash_reference("") is False

    def test_single_char_returns_false(self):
        assert is_feature_hash_reference("x") is False

    def test_exactly_8_hex_digits_with_class_returns_true(self):
        assert is_feature_hash_reference("dd11d1f8-class") is True

    def test_exactly_8_hex_digits_with_feature_returns_true(self):
        assert is_feature_hash_reference("1c574f4a-feature") is True

    def test_exactly_8_hex_digits_with_fn_returns_true(self):
        assert is_feature_hash_reference("a3b2c1d0-fn") is True

    def test_exactly_8_hex_digits_with_method_returns_true(self):
        assert is_feature_hash_reference("a3b2c1d0-method") is True

    def test_all_zeros_returns_true(self):
        assert is_feature_hash_reference("00000000-class") is True

    def test_all_lowercase_hex_returns_true(self):
        assert is_feature_hash_reference("abcdef01-feature") is True

    def test_python_dotted_path_returns_false(self):
        assert is_feature_hash_reference("bob.module.func") is False

    def test_plain_word_returns_false(self):
        assert is_feature_hash_reference("plaintext") is False

    def test_too_short_hex_returns_false(self):
        assert is_feature_hash_reference("dd11d1f-class") is False

    def test_too_long_hex_returns_false(self):
        assert is_feature_hash_reference("dd11d1f88-class") is False

    def test_uppercase_hex_returns_false(self):
        # Pattern requires lowercase hex only
        assert is_feature_hash_reference("DD11D1F8-class") is False

    def test_unknown_suffix_returns_false(self):
        assert is_feature_hash_reference("dd11d1f8-module") is False
