"""Tests for behavior_ac_parser error/failure paths.

Covers:
- Empty string raises ValueError
- Non-behavior prefix raises ValueError
- Missing conditional clause raises ValueError
"""

from __future__ import annotations

import pytest
from bob.spec_quality.behavior_ac_parser import parse_behavior_ac


class TestEmptyStringRaisesValueError:
    """Empty string must raise ValueError (error/failure path)."""

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("   ")

    def test_non_behavior_prefix_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("pytest: tests/test_foo.py")

    def test_missing_conditional_clause_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("behavior: something does something")

    def test_error_message_non_empty(self):
        with pytest.raises(ValueError) as exc_info:
            parse_behavior_ac("")
        assert str(exc_info.value), "error message must be non-empty"
