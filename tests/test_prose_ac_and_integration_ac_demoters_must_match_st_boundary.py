"""Boundary tests for prose-AC / integration-AC demoter prefix and connector (F-0234e7b3).

Covers: empty, zero, or minimum input returns a well-defined result rather
than raising (boundary case).
"""
import pytest

from bob.demoter import is_structural_prefix_match, get_prose_connector_registry


class TestIsStructuralPrefixMatchBoundary:
    def test_empty_string_returns_false_not_raises(self):
        """Empty string must return False, not raise any exception."""
        result = is_structural_prefix_match("")
        assert result is False

    def test_whitespace_only_returns_false_not_raises(self):
        """Whitespace-only string must return False, not raise."""
        result = is_structural_prefix_match("   ")
        assert result is False

    def test_single_char_returns_false_not_raises(self):
        """Single character input must return False, not raise."""
        result = is_structural_prefix_match("p")
        assert result is False

    def test_colon_only_returns_false(self):
        """A bare ':' with no recognized prefix returns False."""
        result = is_structural_prefix_match(":")
        assert result is False

    def test_none_returns_false_not_raises(self):
        """None input must return False, not raise TypeError."""
        result = is_structural_prefix_match(None)  # type: ignore[arg-type]
        assert result is False

    def test_minimum_valid_pytest_criterion(self):
        """Minimum valid pytest criterion must return True."""
        result = is_structural_prefix_match("pytest:")
        assert result is True

    def test_minimum_valid_file_exists(self):
        """Minimum 'file exists:' criterion must return True."""
        result = is_structural_prefix_match("file exists:")
        assert result is True

    def test_minimum_function_defined(self):
        """Minimum 'function defined:' criterion must return True."""
        result = is_structural_prefix_match("function defined:")
        assert result is True


class TestGetProseConnectorRegistryBoundary:
    def test_returns_without_raising(self):
        """Call with no arguments must not raise."""
        result = get_prose_connector_registry()
        assert result is not None

    def test_minimum_output_is_frozenset(self):
        """Registry must be a frozenset, not None or empty."""
        result = get_prose_connector_registry()
        assert isinstance(result, frozenset)
        assert len(result) > 0

    def test_all_registry_tokens_are_strings(self):
        """Every token in the registry must be a non-empty string."""
        registry = get_prose_connector_registry()
        for token in registry:
            assert isinstance(token, str), f"Non-string token: {token!r}"
            assert len(token) > 0, "Empty string token in registry"
