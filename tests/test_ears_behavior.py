"""Tests for bob3.ears_behavior — sixth AC grammar (EARS-style behavior ACs).

Verifies the ``behavior: <subject> <verb> <object> when <condition>`` grammar:
- parse_behavior_criterion returns EarsBehaviorCriterion for valid ACs
- parse_behavior_criterion returns None for non-behavior ACs
- parse_behavior_criterion raises ValueError for malformed behavior ACs
- EarsBehaviorCriterion is accessible from bob3.ears_behavior
"""

from __future__ import annotations

import pytest

from bob3.ears_behavior import EarsBehaviorCriterion, parse_behavior_criterion


class TestParseBehaviorCriterion:
    def test_parses_valid_behavior_ac(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_criterion(ac)
        assert result is not None
        assert isinstance(result, EarsBehaviorCriterion)

    def test_subject_extracted(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_criterion(ac)
        assert result.subject == "parser"

    def test_verb_extracted(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_criterion(ac)
        assert result.verb == "returns"

    def test_object_extracted(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_criterion(ac)
        assert result.object_ == "BehaviorAC"

    def test_condition_extracted(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_criterion(ac)
        assert result.condition == "AC matches grammar"

    def test_returns_none_for_pytest_ac(self):
        assert parse_behavior_criterion("pytest: tests/test_foo.py") is None

    def test_returns_none_for_file_exists_ac(self):
        assert parse_behavior_criterion("File exists: src/foo.py") is None

    def test_returns_none_for_function_defined_ac(self):
        assert parse_behavior_criterion("Function defined: foo.bar") is None

    def test_returns_none_for_integration_ac(self):
        assert parse_behavior_criterion("integration: bob3.evaluator") is None

    def test_returns_none_for_empty_string(self):
        assert parse_behavior_criterion("") is None

    def test_returns_none_for_whitespace_only(self):
        assert parse_behavior_criterion("   ") is None

    def test_raises_value_error_for_behavior_without_when(self):
        with pytest.raises(ValueError):
            parse_behavior_criterion("behavior: parser returns value")

    def test_raises_value_error_message_mentions_when(self):
        with pytest.raises(ValueError, match="when"):
            parse_behavior_criterion("behavior: system does something")

    def test_parses_scheduler_example(self):
        ac = "behavior: scheduler triggers job when deadline passes"
        result = parse_behavior_criterion(ac)
        assert result is not None
        assert result.subject == "scheduler"
        assert result.condition == "deadline passes"

    def test_parses_api_example(self):
        ac = "behavior: api returns 404 when resource is missing"
        result = parse_behavior_criterion(ac)
        assert result is not None
        assert result.subject == "api"
        assert result.condition == "resource is missing"

    def test_result_is_namedtuple_with_four_fields(self):
        ac = "behavior: cache stores value when key is new"
        result = parse_behavior_criterion(ac)
        assert result is not None
        assert hasattr(result, "subject")
        assert hasattr(result, "verb")
        assert hasattr(result, "object_")
        assert hasattr(result, "condition")


class TestEarsBehaviorCriterion:
    def test_ears_behavior_criterion_is_accessible(self):
        assert EarsBehaviorCriterion is not None

    def test_ears_behavior_criterion_is_constructable(self):
        criterion = EarsBehaviorCriterion(
            subject="system",
            verb="logs",
            object_="error",
            condition="input is invalid",
        )
        assert criterion.subject == "system"
        assert criterion.verb == "logs"
        assert criterion.object_ == "error"
        assert criterion.condition == "input is invalid"

    def test_parse_returns_ears_behavior_criterion_instance(self):
        ac = "behavior: validator rejects input when schema fails"
        result = parse_behavior_criterion(ac)
        assert isinstance(result, EarsBehaviorCriterion)


class TestEvaluatorIntegration:
    def test_evaluator_module_imports_parse_behavior_criterion(self):
        from bob3 import evaluator
        assert hasattr(evaluator, "parse_behavior_criterion")

    def test_evaluator_parse_behavior_criterion_works(self):
        from bob3 import evaluator
        ac = "behavior: system emits event when threshold is exceeded"
        result = evaluator.parse_behavior_criterion(ac)
        assert result is not None
