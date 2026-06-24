"""Tests for is_feature_hash_reference — F-caef0dcf / 1c574f4a fix.

Asserts that:
1. is_feature_hash_reference correctly identifies hash-prefix-class identifiers.
2. The integration handler does NOT call _integration_wired for hash-reference tokens.
"""
import pathlib
from unittest.mock import patch, MagicMock

from bob.verification.policy_verb_registry import is_feature_hash_reference
from bob.verification.integration_ac_resolver import resolve_integration_ac


class TestIsFeatureHashReference:
    """is_feature_hash_reference matches r'[0-9a-f]{8}-(class|feature|fn|method)'."""

    def test_dd11d1f8_class_is_hash_reference(self):
        assert is_feature_hash_reference("dd11d1f8-class") is True

    def test_1c574f4a_feature_is_hash_reference(self):
        assert is_feature_hash_reference("1c574f4a-feature") is True

    def test_a3b2c1d0_fn_is_hash_reference(self):
        assert is_feature_hash_reference("a3b2c1d0-fn") is True

    def test_00000000_method_is_hash_reference(self):
        assert is_feature_hash_reference("00000000-method") is True

    def test_bob_module_func_is_not_hash_reference(self):
        """Python dotted path must return False."""
        assert is_feature_hash_reference("bob.module.func") is False

    def test_plain_text_is_not_hash_reference(self):
        """Plain hyphenated text without hex prefix must return False."""
        assert is_feature_hash_reference("plain-text") is False

    def test_too_short_hex_is_not_hash_reference(self):
        """7-char hex prefix is not a valid hash reference."""
        assert is_feature_hash_reference("dd11d1f-class") is False

    def test_too_long_hex_is_not_hash_reference(self):
        """9-char hex prefix is not a valid hash reference."""
        assert is_feature_hash_reference("dd11d1f8a-class") is False

    def test_wrong_suffix_is_not_hash_reference(self):
        """Unknown suffix (not class/feature/fn/method) must return False."""
        assert is_feature_hash_reference("dd11d1f8-module") is False

    def test_non_hex_chars_are_not_hash_reference(self):
        """Non-hex characters in prefix must return False."""
        assert is_feature_hash_reference("gg11d1f8-class") is False

    def test_empty_string_is_not_hash_reference(self):
        assert is_feature_hash_reference("") is False

    def test_none_is_not_hash_reference(self):
        assert is_feature_hash_reference(None) is False  # type: ignore[arg-type]


class TestIntegrationHandlerSkipsHashReferences:
    """integration-AC handler must NOT call _integration_wired for hash-reference tokens."""

    def test_hash_reference_does_not_trigger_wiring_lookup(self, tmp_path):
        """dd11d1f8-class must be skipped — _integration_wired must NOT be called for it."""
        criterion = (
            "integration: dd11d1f8-class failures (verification gate failed on "
            "plausible-fixable emission, attempts<5) MUST trigger fresh-attempt grant "
            "rather than NH-demote"
        )
        mock_wired = MagicMock(return_value=False)
        with patch("bob.enhanced_verification._integration_wired", mock_wired):
            ok, reason = resolve_integration_ac(criterion, tmp_path)

        # The body has no dotted targets (dd11d1f8-class has a hyphen, not a dot)
        # so _integration_wired should never be called.
        mock_wired.assert_not_called()
        # But body contains policy verbs, so it should demote rather than hard-fail
        assert ok is True
        assert "demoted" in reason.lower()

    def test_real_dotted_target_still_calls_wiring_lookup(self, tmp_path):
        """A genuine dotted target like bob.foo.bar MUST call _integration_wired."""
        criterion = "integration: bob.foo.bar is wired"
        mock_wired = MagicMock(return_value=True)
        with patch("bob.enhanced_verification._integration_wired", mock_wired):
            ok, reason = resolve_integration_ac(criterion, tmp_path)

        mock_wired.assert_called_once()
        assert ok is True
