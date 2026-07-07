"""Boundary-case tests for ears_criteria.parse_behavior.

Empty, zero, or minimum-input cases must return a well-defined result
rather than raising an exception.
"""

from __future__ import annotations

import pytest

from ears_criteria import BehaviorCriterion, parse_behavior


def test_empty_string_returns_none():
    """Empty string is a well-defined result: None, not an exception."""
    result = parse_behavior("")
    assert result is None


def test_whitespace_only_returns_none():
    """Whitespace-only string returns None without raising."""
    result = parse_behavior("   ")
    assert result is None


def test_none_like_non_behavior_ac_returns_none():
    """A non-behavior prefix AC returns None (not a raise)."""
    result = parse_behavior("pytest: tests/test_foo.py")
    assert result is None


def test_minimum_valid_ac_parses():
    """Minimum valid behavior AC (short subject/verb/object/condition) parses."""
    ac = "behavior: a b c when d"
    result = parse_behavior(ac)
    # A minimum AC should parse without raising
    assert result is not None
    assert isinstance(result, BehaviorCriterion)
    assert result.condition == "d"


def test_behavior_prefix_only_non_behavior_content_raises_valueerror():
    """behavior: prefix with no 'when' is malformed → ValueError, not a silent None."""
    with pytest.raises(ValueError):
        parse_behavior("behavior: something without a when")


def test_single_word_after_behavior_prefix_raises_valueerror():
    """Single word after behavior: (no when) raises ValueError."""
    with pytest.raises(ValueError):
        parse_behavior("behavior: word")


def test_behavior_with_empty_after_colon_raises_or_none():
    """behavior: with nothing after the colon is handled gracefully."""
    ac = "behavior:"
    # Either returns None or raises ValueError — but must not raise any other exception
    try:
        result = parse_behavior(ac)
        assert result is None
    except ValueError:
        pass  # Also acceptable — malformed behavior AC


def test_very_long_condition_parses():
    """A very long condition clause parses without raising."""
    long_condition = "condition is " + " and ".join(f"thing{i}" for i in range(20))
    ac = f"behavior: system logs error when {long_condition}"
    result = parse_behavior(ac)
    assert result is not None
    assert isinstance(result, BehaviorCriterion)
    assert long_condition in result.condition


def test_condition_with_special_characters():
    """Condition containing non-alpha chars is captured correctly."""
    ac = "behavior: parser returns result when input == ''"
    result = parse_behavior(ac)
    assert result is not None
    assert isinstance(result, BehaviorCriterion)
    assert result.condition  # not empty


def test_numeric_object_parses():
    """Numeric token as object parses without raising."""
    ac = "behavior: api returns 404 when resource is missing"
    result = parse_behavior(ac)
    assert result is not None
    assert isinstance(result, BehaviorCriterion)


def test_ac_grammar_parse_empty_returns_none():
    """ac_grammar.behavior_ears.parse_behavior_criterion('') is None, not a raise."""
    from ac_grammar.behavior_ears import parse_behavior_criterion

    assert parse_behavior_criterion("") is None


def test_ac_grammar_parse_whitespace_returns_none():
    from ac_grammar.behavior_ears import parse_behavior_criterion

    assert parse_behavior_criterion("   ") is None


def test_ac_grammar_check_behavior_no_context_returns_dict():
    """check_behavior with a minimal criterion and no context returns a dict."""
    from ac_grammar.behavior_ears import check_behavior, parse_behavior_criterion

    crit = parse_behavior_criterion("behavior: a b c when d")
    result = check_behavior(crit)
    assert isinstance(result, dict)
    assert result["verdict"] is False
