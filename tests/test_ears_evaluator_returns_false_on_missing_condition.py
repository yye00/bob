"""Tests that evaluate_behavior_ac handles missing/empty condition gracefully."""
import pytest
from bob.spec_quality.ears_parser import BehaviorAC, evaluate_behavior_ac


def test_evaluate_returns_string_with_empty_condition():
    bac = BehaviorAC(
        raw="behavior: system logs error when disk is full",
        subject="system",
        verb="logs",
        object="error",
        condition="",
    )
    result = evaluate_behavior_ac(bac)
    assert isinstance(result, str)
    assert len(result) > 0


def test_evaluate_with_empty_condition_still_contains_pass_fail():
    bac = BehaviorAC(
        raw="behavior: system logs error when disk is full",
        subject="system",
        verb="logs",
        object="error",
        condition="",
    )
    result = evaluate_behavior_ac(bac)
    assert "PASS" in result or "FAIL" in result


def test_evaluate_with_missing_condition_uses_placeholder():
    bac = BehaviorAC(
        raw="behavior: system logs error when disk is full",
        subject="system",
        verb="logs",
        object="error",
        condition="",
    )
    result = evaluate_behavior_ac(bac)
    # Should still reference 'when' clause
    assert "when" in result.lower() or "condition" in result.lower()


def test_evaluate_normal_condition_present_in_output():
    bac = BehaviorAC(
        raw="behavior: cache returns hit when key exists",
        subject="cache",
        verb="returns",
        object="hit",
        condition="key exists",
    )
    result = evaluate_behavior_ac(bac)
    assert "key exists" in result


def test_evaluate_with_empty_condition_does_not_raise():
    bac = BehaviorAC(
        raw="behavior: system does thing when x",
        subject="system",
        verb="does",
        object="thing",
        condition="",
    )
    # Must not raise even with empty condition
    result = evaluate_behavior_ac(bac)
    assert isinstance(result, str)
