"""Tests that increment_bootstrap_attempts raises ValueError for negative counters (73d63cdc).

AC: asserts increment_bootstrap_attempts raises ValueError with message containing
"negative" when counter < 0.
"""

from __future__ import annotations

import pytest

from bob.orchestrator.bootstrap_override import increment_bootstrap_attempts


class TestErrorPathNegativeCounter:
    def test_raises_value_error_for_negative_one(self):
        """increment_bootstrap_attempts raises ValueError when current == -1."""
        with pytest.raises(ValueError, match="negative"):
            increment_bootstrap_attempts(-1)

    def test_raises_value_error_for_large_negative(self):
        """increment_bootstrap_attempts raises ValueError for any negative value."""
        for val in (-1, -2, -5, -100):
            with pytest.raises(ValueError, match="negative"):
                increment_bootstrap_attempts(val)

    def test_error_message_contains_negative(self):
        """The ValueError message must contain 'negative'."""
        try:
            increment_bootstrap_attempts(-1)
            pytest.fail("Expected ValueError was not raised")
        except ValueError as e:
            assert "negative" in str(e).lower()

    def test_zero_does_not_raise(self):
        """increment_bootstrap_attempts(0) returns 1 without raising."""
        result = increment_bootstrap_attempts(0)
        assert result == 1

    def test_positive_does_not_raise(self):
        """increment_bootstrap_attempts with positive values increments normally."""
        assert increment_bootstrap_attempts(0) == 1
        assert increment_bootstrap_attempts(1) == 2
        assert increment_bootstrap_attempts(5) == 6

    def test_increments_by_exactly_one(self):
        """increment_bootstrap_attempts always adds exactly 1."""
        for val in (0, 1, 2, 10):
            assert increment_bootstrap_attempts(val) == val + 1
