"""Tests for bob76.ears — BehaviorCriterion and parse_behavior_criterion.

Verifies the sixth AC grammar:
    behavior: <subject> <verb> <object> when <condition>
"""

from __future__ import annotations

import pytest

from bob76.ears import BehaviorCriterion, parse_behavior_criterion


class TestBehaviorCriterionType:
    def test_is_namedtuple_or_has_fields(self):
        bc = BehaviorCriterion(
            subject="parser",
            verb="returns",
            object_="value",
            condition="AC matches",
        )
        assert bc.subject == "parser"
        assert bc.verb == "returns"
        assert bc.object_ == "value"
        assert bc.condition == "AC matches"

    def test_positional_construction(self):
        bc = BehaviorCriterion("system", "emits", "event", "trigger fires")
        assert bc.subject == "system"
        assert bc.verb == "emits"
        assert bc.object_ == "event"
        assert bc.condition == "trigger fires"


class TestParseBehaviorCriterionNonBehavior:
    def test_returns_none_for_pytest_ac(self):
        assert parse_behavior_criterion("pytest: tests/test_foo.py") is None

    def test_returns_none_for_file_exists_ac(self):
        assert parse_behavior_criterion("File exists: src/foo.py") is None

    def test_returns_none_for_function_defined_ac(self):
        assert parse_behavior_criterion("Function defined: foo.bar") is None

    def test_returns_none_for_integration_ac(self):
        assert parse_behavior_criterion("integration: bob76.evaluator") is None

    def test_returns_none_for_empty_string(self):
        assert parse_behavior_criterion("") is None

    def test_returns_none_for_whitespace_only(self):
        assert parse_behavior_criterion("   ") is None


class TestParseBehaviorCriterionValid:
    def test_parses_simple_subject_verb_object_when_condition(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_criterion(ac)
        assert result is not None
        assert isinstance(result, BehaviorCriterion)
        assert result.subject == "parser"
        assert result.verb == "returns"
        assert result.object_ == "BehaviorAC"
        assert result.condition == "AC matches grammar"

    def test_parses_scheduler_example(self):
        ac = "behavior: scheduler triggers job when deadline passes"
        result = parse_behavior_criterion(ac)
        assert result is not None
        assert result.subject == "scheduler"
        assert result.verb == "triggers"
        assert result.object_ == "job"
        assert result.condition == "deadline passes"

    def test_parses_api_returns_404_example(self):
        ac = "behavior: api returns 404 when resource is missing"
        result = parse_behavior_criterion(ac)
        assert result is not None
        assert result.subject == "api"
        assert result.verb == "returns"
        assert result.object_ == "404"
        assert result.condition == "resource is missing"

    def test_condition_preserved_verbatim(self):
        ac = "behavior: cache evicts entry when memory exceeds threshold and TTL expires"
        result = parse_behavior_criterion(ac)
        assert result is not None
        assert "memory exceeds threshold" in result.condition

    def test_returns_behavior_criterion_instance(self):
        ac = "behavior: validator raises error when input is empty"
        result = parse_behavior_criterion(ac)
        assert isinstance(result, BehaviorCriterion)

    def test_behavior_prefix_case_insensitive(self):
        ac = "Behavior: system logs event when user authenticates"
        result = parse_behavior_criterion(ac)
        assert result is not None
        assert result.condition == "user authenticates"


class TestParseBehaviorCriterionMalformed:
    def test_raises_value_error_when_no_when_clause(self):
        with pytest.raises(ValueError):
            parse_behavior_criterion("behavior: parser returns value")

    def test_raises_value_error_message_mentions_when(self):
        with pytest.raises(ValueError, match="when"):
            parse_behavior_criterion("behavior: system does something")

    def test_raises_value_error_not_returns_none(self):
        with pytest.raises(ValueError):
            parse_behavior_criterion("behavior: orchestrator dispatches task")
