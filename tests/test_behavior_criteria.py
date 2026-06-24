"""Tests for bob.behavior_criteria — EARS-style behavior AC sixth grammar.

Verifies that:
  - EARSBehaviorCriterion is a named tuple with (subject, verb, object_, condition)
  - parse_behavior_criteria parses behavior: ACs into EARSBehaviorCriterion
  - parse_behavior_criteria returns None for non-behavior ACs
  - parse_behavior_criteria raises ValueError for malformed behavior ACs
  - bob.verifier exposes verify_behavior_ac (integration)
"""

from __future__ import annotations

import pytest

from bob.behavior_criteria import EARSBehaviorCriterion, parse_behavior_criteria


def test_ears_behavior_criterion_is_named_tuple():
    c = EARSBehaviorCriterion(subject="parser", verb="returns", object_="result", condition="AC matches")
    assert c.subject == "parser"
    assert c.verb == "returns"
    assert c.object_ == "result"
    assert c.condition == "AC matches"


def test_parse_behavior_criteria_canonical():
    """Canonical: well-formed behavior: AC parses into EARSBehaviorCriterion."""
    ac = "behavior: parser returns BehaviorAC when AC matches grammar"
    result = parse_behavior_criteria(ac)
    assert result is not None
    assert isinstance(result, EARSBehaviorCriterion)
    assert result.subject == "parser"
    assert result.verb == "returns"
    assert result.object_ == "BehaviorAC"
    assert result.condition == "AC matches grammar"


def test_parse_behavior_criteria_returns_none_for_non_behavior():
    """Non-behavior ACs return None."""
    assert parse_behavior_criteria("pytest: tests/test_foo.py") is None
    assert parse_behavior_criteria("File exists: src/foo.py") is None
    assert parse_behavior_criteria("Function defined: foo.bar") is None
    assert parse_behavior_criteria("integration: bob.verifier") is None


def test_parse_behavior_criteria_raises_for_missing_when():
    """Malformed behavior: AC (missing 'when') raises ValueError."""
    with pytest.raises(ValueError):
        parse_behavior_criteria("behavior: system does something")


def test_parse_behavior_criteria_various_valid():
    """Multiple well-formed ACs parse correctly."""
    cases = [
        ("behavior: scheduler triggers job when deadline passes",
         "scheduler", "triggers", "job", "deadline passes"),
        ("behavior: api returns 404 when resource is missing",
         "api", "returns", "404", "resource is missing"),
        ("behavior: cache stores value when key is new",
         "cache", "stores", "value", "key is new"),
    ]
    for ac, subj, verb, obj, cond in cases:
        r = parse_behavior_criteria(ac)
        assert r is not None, f"Expected result for: {ac}"
        assert isinstance(r, EARSBehaviorCriterion)
        assert r.subject == subj
        assert r.verb == verb
        assert r.object_ == obj
        assert r.condition == cond


def test_parse_behavior_criteria_empty_returns_none():
    """Empty string returns None."""
    assert parse_behavior_criteria("") is None


def test_parse_behavior_criteria_whitespace_returns_none():
    """Whitespace-only string returns None."""
    assert parse_behavior_criteria("   ") is None


def test_verifier_integration():
    """bob.verifier exposes verify_behavior_ac (integration AC)."""
    from bob import verifier
    assert hasattr(verifier, "verify_behavior_ac"), (
        "bob.verifier must expose verify_behavior_ac for integration"
    )


@pytest.mark.parametrize("given_val, expected", [
    ("x=5", "result=25"),
    ("x=0", "result=0"),
    ("x=-3", "result=-3"),
])
def test_key_example_parametrized(given_val, expected):
    """key_example returns a dict with given and then; verifier emits parametrize tests with seed=0."""
    from bob.behavior_criteria import key_example
    ex = key_example(given=given_val, then=expected)
    assert ex["given"] == given_val
    assert ex["then"] == expected
    assert set(ex.keys()) == {"given", "then"}
