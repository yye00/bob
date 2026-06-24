"""Tests for src/ears_criteria.py — BehaviorCriterion and parse_behavior.

Verifies the sixth AC grammar:
    behavior: <subject> <verb> <object> when <condition>
"""

from __future__ import annotations

import pytest

from ears_criteria import BehaviorCriterion, parse_behavior


class TestParseBehaviorNonBehaviorACs:
    def test_returns_none_for_pytest_ac(self):
        assert parse_behavior("pytest: tests/test_foo.py") is None

    def test_returns_none_for_file_exists_ac(self):
        assert parse_behavior("File exists: src/foo.py") is None

    def test_returns_none_for_function_defined_ac(self):
        assert parse_behavior("Function defined: foo.bar") is None

    def test_returns_none_for_integration_ac(self):
        assert parse_behavior("integration: bob.evaluator") is None

    def test_returns_none_for_class_defined_ac(self):
        assert parse_behavior("Class defined: ears_criteria.BehaviorCriterion") is None

    def test_returns_none_for_empty_string(self):
        assert parse_behavior("") is None

    def test_returns_none_for_whitespace_only(self):
        assert parse_behavior("   ") is None


class TestParseBehaviorValidACs:
    def test_parses_simple_subject_verb_object_when_condition(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior(ac)
        assert result is not None
        assert isinstance(result, BehaviorCriterion)
        assert result.subject == "parser"
        assert result.verb == "returns"
        assert result.object_ == "BehaviorAC"
        assert result.condition == "AC matches grammar"

    def test_parses_scheduler_example(self):
        ac = "behavior: scheduler triggers job when deadline passes"
        result = parse_behavior(ac)
        assert result is not None
        assert result.subject == "scheduler"
        assert result.verb == "triggers"
        assert result.object_ == "job"
        assert result.condition == "deadline passes"

    def test_parses_api_returns_404_example(self):
        ac = "behavior: api returns 404 when resource is missing"
        result = parse_behavior(ac)
        assert result is not None
        assert result.subject == "api"
        assert result.condition == "resource is missing"

    def test_parses_cache_stores_value(self):
        ac = "behavior: cache stores value when key is new"
        result = parse_behavior(ac)
        assert result is not None
        assert result.subject == "cache"
        assert result.verb == "stores"
        assert result.object_ == "value"
        assert result.condition == "key is new"

    def test_case_insensitive_behavior_prefix(self):
        ac = "Behavior: user sees dashboard when login succeeds"
        result = parse_behavior(ac)
        assert result is not None
        assert "login succeeds" in result.condition

    def test_case_insensitive_behavior_prefix_all_caps(self):
        ac = "BEHAVIOR: system logs error when input is invalid"
        result = parse_behavior(ac)
        assert result is not None
        assert "invalid" in result.condition

    def test_condition_does_not_contain_leading_when(self):
        ac = "behavior: system notifies user when event fires"
        result = parse_behavior(ac)
        assert result is not None
        assert not result.condition.lower().startswith("when")

    def test_result_is_named_tuple(self):
        ac = "behavior: user sees results when query is submitted"
        result = parse_behavior(ac)
        assert result is not None
        assert hasattr(result, "subject")
        assert hasattr(result, "verb")
        assert hasattr(result, "object_")
        assert hasattr(result, "condition")

    def test_behavior_criterion_is_namedtuple_type(self):
        result = parse_behavior("behavior: cache expires entry when ttl passes")
        assert isinstance(result, BehaviorCriterion)

    def test_multiword_condition(self):
        ac = "behavior: evaluator emits structured prompt when behavior AC is present in criteria"
        result = parse_behavior(ac)
        assert result is not None
        assert len(result.condition.split()) >= 3

    def test_whitespace_stripped_from_fields(self):
        ac = "  behavior:   parser   returns   BehaviorAC   when   AC matches grammar  "
        result = parse_behavior(ac)
        assert result is not None
        # Fields should not have leading/trailing whitespace
        assert result.subject == result.subject.strip()
        assert result.verb == result.verb.strip()
        assert result.object_ == result.object_.strip()
        assert result.condition == result.condition.strip()


class TestParseBehaviorRaisesOnMalformed:
    def test_raises_for_behavior_without_when(self):
        with pytest.raises(ValueError, match="when"):
            parse_behavior("behavior: parser returns value")

    def test_raises_for_behavior_colon_only(self):
        with pytest.raises(ValueError):
            parse_behavior("behavior: no clause at all")

    def test_raises_not_returns_none_for_malformed(self):
        # Confirms error path: behavior prefix present but no when → ValueError not None
        with pytest.raises(ValueError):
            parse_behavior("behavior: subject does something without trigger")


class TestBehaviorCriterionType:
    def test_is_named_tuple(self):
        bc = BehaviorCriterion(subject="s", verb="v", object_="o", condition="c")
        assert bc.subject == "s"
        assert bc.verb == "v"
        assert bc.object_ == "o"
        assert bc.condition == "c"

    def test_is_iterable(self):
        bc = BehaviorCriterion(subject="s", verb="v", object_="o", condition="c")
        s, v, o, c = bc
        assert s == "s"
        assert v == "v"
        assert o == "o"
        assert c == "c"

    def test_equality(self):
        bc1 = BehaviorCriterion(subject="s", verb="v", object_="o", condition="c")
        bc2 = BehaviorCriterion(subject="s", verb="v", object_="o", condition="c")
        assert bc1 == bc2

    def test_inequality_on_different_fields(self):
        bc1 = BehaviorCriterion(subject="a", verb="v", object_="o", condition="c")
        bc2 = BehaviorCriterion(subject="b", verb="v", object_="o", condition="c")
        assert bc1 != bc2
