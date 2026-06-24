"""Tests for bob3.behavior_ac.parse_behavior_ac and BehaviorACTuple.

Verifies the sixth AC grammar:
    behavior: <subject> <verb> <object> when <condition>

parse_behavior_ac must:
1. Parse the behavior: AC into a BehaviorACTuple (subject, verb, object_, condition, raw).
2. Return None for non-behavior ACs.
3. Raise ValueError for malformed behavior ACs (missing 'when').
"""

from __future__ import annotations

import pytest

from bob3.behavior_ac import BehaviorACTuple, parse_behavior_ac


def test_parse_canonical_behavior_ac():
    """Canonical behavior AC parses into all four structured fields."""
    ac = "behavior: parser returns BehaviorAC when AC matches grammar"
    result = parse_behavior_ac(ac)

    assert result is not None
    assert isinstance(result, BehaviorACTuple)
    assert result.subject == "parser"
    assert result.verb == "returns"
    assert result.object_ == "BehaviorAC"
    assert result.condition == "AC matches grammar"


def test_raw_field_preserved():
    """Raw AC string is preserved in the BehaviorACTuple."""
    ac = "behavior: scheduler triggers job when deadline passes"
    result = parse_behavior_ac(ac)
    assert result is not None
    assert result.raw == ac


def test_returns_none_for_non_behavior_acs():
    """Non-behavior ACs return None."""
    assert parse_behavior_ac("pytest: tests/test_foo.py") is None
    assert parse_behavior_ac("File exists: src/foo.py") is None
    assert parse_behavior_ac("Function defined: bob3.foo.bar") is None
    assert parse_behavior_ac("integration: bob3.evaluator") is None


def test_returns_none_for_empty_string():
    """Empty string returns None."""
    assert parse_behavior_ac("") is None


def test_returns_none_for_whitespace_only():
    """Whitespace-only string returns None."""
    assert parse_behavior_ac("   ") is None


def test_raises_valueerror_for_behavior_without_when():
    """behavior: AC missing 'when' clause raises ValueError."""
    with pytest.raises(ValueError):
        parse_behavior_ac("behavior: parser returns value")


def test_behavior_ac_tuple_is_named_tuple():
    """BehaviorACTuple is a NamedTuple with expected fields."""
    t = BehaviorACTuple(
        subject="sys",
        verb="logs",
        object_="error",
        condition="input is invalid",
        raw="behavior: sys logs error when input is invalid",
    )
    assert t.subject == "sys"
    assert t.verb == "logs"
    assert t.object_ == "error"
    assert t.condition == "input is invalid"


def test_multiple_well_formed_acs():
    """Multiple well-formed behavior ACs all parse without raising."""
    cases = [
        "behavior: scheduler triggers job when deadline passes",
        "behavior: api returns 404 when resource is missing",
        "behavior: cache stores value when key is new",
        "behavior: user sees dashboard when login succeeds",
    ]
    for ac in cases:
        result = parse_behavior_ac(ac)
        assert result is not None, f"Expected non-None for: {ac!r}"
        assert result.condition, f"Condition must be non-empty for: {ac!r}"


def test_evaluator_integration_via_bob3_evaluator():
    """bob3.evaluator imports parse_behavior_ac and it uses the same grammar."""
    from bob3.evaluator import parse_behavior_ac as evaluator_parse_behavior_ac

    ac = "behavior: orchestrator queues task when feature is ready"
    result = evaluator_parse_behavior_ac(ac)
    assert result is not None
