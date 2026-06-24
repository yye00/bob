"""Tests for bob.acceptance_criteria_parser.

Verifies BehaviorCriterion and parse_behavior_criterion for the sixth
AC grammar: behavior: <subject> <verb> <object> when <condition>
"""

from __future__ import annotations

import pytest

from bob.acceptance_criteria_parser import BehaviorCriterion, parse_behavior_criterion


# ---------------------------------------------------------------------------
# Happy-path parsing
# ---------------------------------------------------------------------------


def test_canonical_parse():
    """Canonical behavior AC parses into the correct four fields."""
    ac = "behavior: parser returns BehaviorCriterion when AC matches grammar"
    result = parse_behavior_criterion(ac)
    assert result is not None
    assert isinstance(result, BehaviorCriterion)
    assert result.subject == "parser"
    assert result.verb == "returns"
    assert result.object_ == "BehaviorCriterion"
    assert result.condition == "AC matches grammar"


def test_various_well_formed_acs():
    """Multiple well-formed behavior ACs parse to the expected fields."""
    cases = [
        (
            "behavior: scheduler triggers job when deadline passes",
            ("scheduler", "deadline passes"),
        ),
        (
            "behavior: api returns 404 when resource is missing",
            ("api", "resource is missing"),
        ),
        (
            "behavior: cache stores value when key is new",
            ("cache", "key is new"),
        ),
    ]
    for ac, (subject, condition) in cases:
        result = parse_behavior_criterion(ac)
        assert result is not None, f"Expected non-None for {ac!r}"
        assert result.subject == subject, f"Subject mismatch for {ac!r}"
        assert result.condition == condition, f"Condition mismatch for {ac!r}"


def test_behavior_criterion_is_named_tuple():
    """BehaviorCriterion is a NamedTuple with the four required fields."""
    bc = BehaviorCriterion(subject="s", verb="v", object_="o", condition="c")
    assert bc.subject == "s"
    assert bc.verb == "v"
    assert bc.object_ == "o"
    assert bc.condition == "c"


def test_result_type_is_behavior_criterion():
    """parse_behavior_criterion returns a BehaviorCriterion instance."""
    ac = "behavior: orchestrator queues task when feature is ready"
    result = parse_behavior_criterion(ac)
    assert isinstance(result, BehaviorCriterion)


# ---------------------------------------------------------------------------
# Non-behavior ACs return None
# ---------------------------------------------------------------------------


def test_returns_none_for_pytest_ac():
    assert parse_behavior_criterion("pytest: tests/test_foo.py") is None


def test_returns_none_for_file_exists_ac():
    assert parse_behavior_criterion("File exists: src/foo.py") is None


def test_returns_none_for_function_defined_ac():
    assert parse_behavior_criterion("Function defined: foo.bar") is None


def test_returns_none_for_integration_ac():
    assert parse_behavior_criterion("integration: bob.cli") is None


def test_returns_none_for_empty_string():
    assert parse_behavior_criterion("") is None


def test_returns_none_for_whitespace_only():
    assert parse_behavior_criterion("   ") is None


# ---------------------------------------------------------------------------
# Error cases — malformed behavior ACs raise ValueError
# ---------------------------------------------------------------------------


def test_behavior_without_when_raises_valueerror():
    """behavior: AC missing 'when' raises ValueError."""
    with pytest.raises(ValueError):
        parse_behavior_criterion("behavior: parser returns value")


def test_valueerror_message_mentions_when():
    """ValueError message for missing 'when' references the missing clause."""
    with pytest.raises(ValueError, match="when"):
        parse_behavior_criterion("behavior: orchestrator dispatches task")


def test_single_word_body_raises_valueerror():
    with pytest.raises(ValueError):
        parse_behavior_criterion("behavior: word")


def test_behavior_prefix_only_raises_or_returns_none():
    """behavior: with nothing after colon is handled gracefully (no crash)."""
    ac = "behavior:"
    try:
        result = parse_behavior_criterion(ac)
        assert result is None
    except ValueError:
        pass  # also acceptable


# ---------------------------------------------------------------------------
# Evaluator integration — bob.evaluator imports parse_behavior_criterion
# ---------------------------------------------------------------------------


def test_evaluator_integration():
    """bob.evaluator.check_behavior_criterion uses parse_behavior_criterion."""
    from bob.evaluator import check_behavior_criterion

    ac = "behavior: system logs error when input is invalid"
    check_text = check_behavior_criterion(ac)
    assert check_text is not None
    assert isinstance(check_text, str)
    assert len(check_text) > 0


def test_evaluator_returns_none_for_non_behavior_ac():
    """evaluator.check_behavior_criterion returns None for non-behavior ACs."""
    from bob.evaluator import check_behavior_criterion

    assert check_behavior_criterion("pytest: tests/foo.py") is None
    assert check_behavior_criterion("File exists: src/bar.py") is None


def test_evaluator_check_references_parsed_fields():
    """Evaluator check string contains the parsed subject and condition."""
    from bob.evaluator import check_behavior_criterion

    ac = "behavior: cache expires entry when ttl passes"
    check_text = check_behavior_criterion(ac)
    assert check_text is not None
    assert "cache" in check_text
    assert "ttl passes" in check_text
