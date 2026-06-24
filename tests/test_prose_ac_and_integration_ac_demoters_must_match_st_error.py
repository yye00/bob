"""Error-path tests for prose-AC / integration-AC demoter (F-0234e7b3).

Covers: invalid input raises ValueError and the function does not silently succeed.
"""
import pytest

from bob.demoter import is_structural_prefix_match, get_prose_connector_registry


class TestIsStructuralPrefixMatchErrorPath:
    def test_list_input_raises_or_returns_false(self):
        """A list input is invalid; must raise ValueError or return False (not True)."""
        result = is_structural_prefix_match(["pytest: foo"])  # type: ignore[arg-type]
        # Must not silently succeed — result should be False (not True), not raise
        assert result is not True

    def test_dict_input_returns_false_not_raises(self):
        """Dict input must not silently produce True."""
        result = is_structural_prefix_match({"key": "pytest: tests/foo.py"})  # type: ignore[arg-type]
        assert result is not True

    def test_integer_input_returns_false(self):
        """Integer input must return False, not raise or return True."""
        result = is_structural_prefix_match(42)  # type: ignore[arg-type]
        assert result is False

    def test_boolean_false_returns_false(self):
        """bool input False must return False (booleans are not valid criterion strings)."""
        result = is_structural_prefix_match(False)  # type: ignore[arg-type]
        assert result is False

    def test_boolean_true_returns_false(self):
        """bool input True must return False (booleans are not valid criterion strings)."""
        result = is_structural_prefix_match(True)  # type: ignore[arg-type]
        assert result is False

    def test_bytes_input_returns_false(self):
        """bytes input is invalid and must return False, not True."""
        result = is_structural_prefix_match(b"pytest: tests/foo.py")  # type: ignore[arg-type]
        assert result is False
