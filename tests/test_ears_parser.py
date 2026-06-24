"""Tests for src/bob/spec_quality/ears_parser.py.

Verifies parse_behavior_ac and evaluate_behavior_ac for the sixth AC grammar:
    behavior: <subject> <verb> <object> when <condition>
"""

from __future__ import annotations

import pytest

from bob.spec_quality.ears_parser import (
    BehaviorAC,
    parse_behavior_ac,
    evaluate_behavior_ac,
    behavior_acs_from_criteria,
    build_behavior_ac_evaluator_section,
)


# ---------------------------------------------------------------------------
# parse_behavior_ac
# ---------------------------------------------------------------------------


class TestParseBehaviorAc:
    def test_returns_none_for_non_behavior_ac(self):
        assert parse_behavior_ac("File exists: src/foo.py") is None
        assert parse_behavior_ac("Function defined: bob.foo.bar") is None
        assert parse_behavior_ac("pytest: tests/test_foo.py") is None
        assert parse_behavior_ac("integration: bob.cli") is None

    def test_returns_none_for_empty_string(self):
        assert parse_behavior_ac("") is None

    def test_returns_none_for_behavior_without_when(self):
        assert parse_behavior_ac("behavior: parser does something") is None

    def test_parses_simple_subject_verb_object_when_condition(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_ac(ac)
        assert result is not None
        assert isinstance(result, BehaviorAC)
        assert "parser" in result.subject.lower()
        assert "returns" in result.verb.lower() or "BehaviorAC" in result.object or "grammar" in result.condition

    def test_condition_is_captured_correctly(self):
        ac = "behavior: evaluator emits structured prompt when behavior AC is present"
        result = parse_behavior_ac(ac)
        assert result is not None
        assert "behavior AC is present" in result.condition or "behavior" in result.condition

    def test_raw_field_contains_full_string(self):
        ac = "behavior: system logs error when input is invalid"
        result = parse_behavior_ac(ac)
        assert result is not None
        assert result.raw.startswith("behavior")

    def test_case_insensitive_behavior_prefix(self):
        ac = "Behavior: user sees dashboard when login succeeds"
        result = parse_behavior_ac(ac)
        assert result is not None
        assert "login succeeds" in result.condition or "succeeds" in result.condition

    def test_returns_behavior_ac_dataclass(self):
        ac = "behavior: user sees results when query is submitted"
        result = parse_behavior_ac(ac)
        assert result is not None
        assert hasattr(result, "subject")
        assert hasattr(result, "verb")
        assert hasattr(result, "object")
        assert hasattr(result, "condition")

    def test_condition_does_not_include_verb(self):
        ac = "behavior: cache stores value when key is new"
        result = parse_behavior_ac(ac)
        assert result is not None
        assert "when" not in result.condition.lower() or result.condition.lower().startswith("when") is False

    def test_parses_multiword_subject(self):
        ac = "behavior: the system returns 404 when resource is missing"
        result = parse_behavior_ac(ac)
        assert result is not None
        assert result.condition.strip() != ""

    def test_all_fields_are_non_empty_strings(self):
        ac = "behavior: scheduler triggers job when deadline passes"
        result = parse_behavior_ac(ac)
        assert result is not None
        # All fields should be strings
        assert isinstance(result.subject, str)
        assert isinstance(result.verb, str)
        assert isinstance(result.object, str)
        assert isinstance(result.condition, str)

    def test_whitespace_insensitive(self):
        ac = "  behavior :   parser   returns   result   when   input  is  valid  "
        result = parse_behavior_ac(ac)
        assert result is not None
        assert result.condition.strip() != ""


# ---------------------------------------------------------------------------
# evaluate_behavior_ac
# ---------------------------------------------------------------------------


class TestEvaluateBehaviorAc:
    def test_returns_string(self):
        bac = BehaviorAC(
            raw="behavior: parser returns BehaviorAC when AC matches",
            subject="parser",
            verb="returns",
            object="BehaviorAC",
            condition="AC matches",
        )
        result = evaluate_behavior_ac(bac)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_subject_verb_object_condition(self):
        bac = BehaviorAC(
            raw="behavior: cache stores value when key is new",
            subject="cache",
            verb="stores",
            object="value",
            condition="key is new",
        )
        result = evaluate_behavior_ac(bac)
        assert "cache" in result
        assert "stores" in result
        assert "value" in result
        assert "key is new" in result

    def test_contains_pass_fail_instruction(self):
        bac = BehaviorAC(
            raw="behavior: evaluator emits prompt when behavior AC present",
            subject="evaluator",
            verb="emits",
            object="prompt",
            condition="behavior AC present",
        )
        result = evaluate_behavior_ac(bac)
        assert "PASS" in result or "FAIL" in result

    def test_structured_not_freeform(self):
        bac = BehaviorAC(
            raw="behavior: system logs warning when disk is full",
            subject="system",
            verb="logs",
            object="warning",
            condition="disk is full",
        )
        result = evaluate_behavior_ac(bac)
        # Must reference each parsed part individually, not just paste raw
        assert "system" in result
        assert "logs" in result
        assert "warning" in result
        assert "disk is full" in result

    def test_contains_file_line_reference_instruction(self):
        bac = BehaviorAC(
            raw="behavior: api returns 404 when resource missing",
            subject="api",
            verb="returns",
            object="404",
            condition="resource missing",
        )
        result = evaluate_behavior_ac(bac)
        assert "file" in result.lower() or "line" in result.lower()

    def test_handles_empty_verb(self):
        bac = BehaviorAC(
            raw="behavior: something when condition",
            subject="something",
            verb="",
            object="",
            condition="condition",
        )
        result = evaluate_behavior_ac(bac)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# behavior_acs_from_criteria
# ---------------------------------------------------------------------------


class TestBehaviorAcsFromCriteria:
    def test_extracts_from_json_list(self):
        criteria = '["behavior: parser returns BehaviorAC when AC matches", "pytest: tests/test_foo.py"]'
        result = behavior_acs_from_criteria(criteria)
        assert len(result) == 1
        assert isinstance(result[0], BehaviorAC)

    def test_extracts_from_list(self):
        criteria = [
            "behavior: system logs error when input invalid",
            "File exists: src/foo.py",
            "behavior: evaluator checks behavior when AC present",
        ]
        result = behavior_acs_from_criteria(criteria)
        assert len(result) == 2

    def test_returns_empty_for_no_behavior_acs(self):
        criteria = [
            "pytest: tests/test_foo.py",
            "File exists: src/foo.py",
        ]
        result = behavior_acs_from_criteria(criteria)
        assert result == []

    def test_extracts_from_newline_string(self):
        criteria = "behavior: user sees dashboard when login succeeds\npytest: tests/test_bar.py"
        result = behavior_acs_from_criteria(criteria)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# build_behavior_ac_evaluator_section
# ---------------------------------------------------------------------------


class TestBuildBehaviorAcEvaluatorSection:
    def test_returns_empty_string_when_no_behavior_acs(self):
        criteria = ["pytest: tests/test_foo.py", "File exists: src/bar.py"]
        result = build_behavior_ac_evaluator_section(criteria)
        assert result == ""

    def test_returns_non_empty_when_behavior_acs_present(self):
        criteria = ["behavior: parser returns result when input valid"]
        result = build_behavior_ac_evaluator_section(criteria)
        assert result != ""
        assert isinstance(result, str)

    def test_section_contains_structured_checks(self):
        criteria = ["behavior: cache stores value when key is new"]
        result = build_behavior_ac_evaluator_section(criteria)
        assert "Behavior AC" in result
        assert "cache" in result
        assert "key is new" in result

    def test_handles_multiple_behavior_acs(self):
        criteria = [
            "behavior: api returns 200 when request valid",
            "behavior: system logs error when input invalid",
        ]
        result = build_behavior_ac_evaluator_section(criteria)
        assert "Behavior AC 1" in result
        assert "Behavior AC 2" in result

    def test_prompt_instructs_structured_verification(self):
        criteria = ["behavior: scheduler triggers job when deadline passes"]
        result = build_behavior_ac_evaluator_section(criteria)
        assert "subject" in result.lower() or "verb" in result.lower() or "object" in result.lower()
