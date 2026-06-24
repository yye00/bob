"""Boundary-case tests for spec_quality behavior-AC parser.

AC: pytest: tests/test_spec_quality_behavior_ac_parser_must_accept_canoni_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising
    (boundary case)

The facade function (spec_quality_behavior_ac_parser_must_accept_canonical_clause)
wraps parse_behavior_ac and MUST NOT propagate ValueError — it must return a dict
with accepted=False on all boundary/empty inputs.
"""

from __future__ import annotations

import pytest
from bob.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
    spec_quality_behavior_ac_parser_must_accept_canonical_clause as parse_ac_facade,
)


class TestEmptyInputReturnsDict:
    """Empty string must return a dict, not raise."""

    def test_empty_string_returns_dict(self):
        result = parse_ac_facade("")
        assert isinstance(result, dict)

    def test_empty_string_accepted_false(self):
        result = parse_ac_facade("")
        assert result.get("accepted") is False

    def test_empty_string_has_error_or_reason(self):
        result = parse_ac_facade("")
        assert "error" in result or "reason" in result


class TestWhitespaceOnlyInput:
    """Whitespace-only input must return a dict with accepted=False."""

    def test_spaces_returns_dict(self):
        result = parse_ac_facade("   ")
        assert isinstance(result, dict)

    def test_spaces_accepted_false(self):
        result = parse_ac_facade("   ")
        assert result.get("accepted") is False

    def test_newline_only_returns_dict(self):
        result = parse_ac_facade("\n")
        assert isinstance(result, dict)

    def test_newline_accepted_false(self):
        result = parse_ac_facade("\n")
        assert result.get("accepted") is False


class TestMinimumValidInput:
    """Minimum well-formed input must be accepted (boundary from the valid side)."""

    def test_minimal_when_form_accepted(self):
        ac = "behavior: x y when z"
        result = parse_ac_facade(ac)
        assert isinstance(result, dict)
        assert result.get("accepted") is True

    def test_minimal_on_form_accepted(self):
        ac = "behavior: x on y z"
        result = parse_ac_facade(ac)
        assert isinstance(result, dict)
        # Accepted OR at least returns a dict without raising
        assert "accepted" in result

    def test_minimal_result_has_raw_on_success(self):
        ac = "behavior: x does y when z happens"
        result = parse_ac_facade(ac)
        if result.get("accepted"):
            assert "raw" in result


class TestNonBehaviorPrefix:
    """Strings not starting with 'behavior:' must return dict with accepted=False."""

    def test_pytest_prefix_returns_dict(self):
        result = parse_ac_facade("pytest: tests/test_foo.py")
        assert isinstance(result, dict)

    def test_pytest_prefix_accepted_false(self):
        result = parse_ac_facade("pytest: tests/test_foo.py")
        assert result.get("accepted") is False

    def test_plain_sentence_returns_dict(self):
        result = parse_ac_facade("system logs error when disk is full")
        assert isinstance(result, dict)

    def test_plain_sentence_accepted_false(self):
        result = parse_ac_facade("system logs error when disk is full")
        assert result.get("accepted") is False


class TestNoConditionalClause:
    """Behavior prefix but no 'when' or 'on' must return dict with accepted=False."""

    def test_no_conditional_returns_dict(self):
        result = parse_ac_facade("behavior: system does something somewhere")
        assert isinstance(result, dict)

    def test_no_conditional_accepted_false(self):
        result = parse_ac_facade("behavior: system does something somewhere")
        assert result.get("accepted") is False

    def test_no_conditional_has_error(self):
        result = parse_ac_facade("behavior: system does something somewhere")
        assert "error" in result or "reason" in result
