"""Tests boundary: minimum-length 'when' clause (single character condition)."""
import pytest
from bob.spec_quality.ears_parser import BehaviorAC, parse_behavior_ac


def test_minimum_when_clause_single_char_condition():
    """parse_behavior_ac returns BehaviorAC with single-character condition."""
    result = parse_behavior_ac("behavior: a does b when c")
    assert result is not None
    assert isinstance(result, BehaviorAC)
    assert result.condition == "c"


def test_minimum_when_clause_condition_is_single_character():
    result = parse_behavior_ac("behavior: a does b when c")
    assert result is not None
    assert len(result.condition) == 1


def test_minimum_subject_and_object_single_char():
    result = parse_behavior_ac("behavior: a does b when c")
    assert result is not None
    assert "a" in result.subject
    assert "b" in result.object


def test_minimum_when_clause_verb_captured():
    result = parse_behavior_ac("behavior: a does b when c")
    assert result is not None
    assert result.verb != ""


def test_minimum_when_clause_raw_preserved():
    ac = "behavior: a does b when c"
    result = parse_behavior_ac(ac)
    assert result is not None
    assert result.raw == ac


def test_minimum_when_clause_all_fields_present():
    result = parse_behavior_ac("behavior: a does b when c")
    assert result is not None
    assert result.subject is not None
    assert result.verb is not None
    assert result.object is not None
    assert result.condition is not None
