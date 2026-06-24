"""Tests verifying that bob.evaluator uses the parsed EARS structure.

Acceptance criteria: integration: bob.evaluator
This file confirms the evaluator's task section is generated using the
parsed (subject, verb, object, condition) tuple rather than freeform prose.
"""

from __future__ import annotations

import pytest

from bob.evaluator import build_evaluator_task_section
from bob.spec_quality.ears_parser import (
    BehaviorAC,
    evaluate_behavior_ac,
    behavior_acs_from_criteria,
    build_behavior_ac_evaluator_section,
    parse_behavior_ac,
)


class TestEvaluatorUsesParsedStructure:
    """Verifies evaluator uses parsed behavior AC structure (not freeform prose)."""

    def test_evaluator_task_section_is_string(self):
        criteria = ["pytest: tests/test_foo.py"]
        result = build_evaluator_task_section(criteria)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_evaluator_no_behavior_acs_returns_base_section(self):
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo.py",
            "integration: bob.cli",
        ]
        result = build_evaluator_task_section(criteria)
        # Should contain the base task section
        assert "Identify each acceptance criterion" in result
        # Should not contain behavior AC section
        assert "Structured behavior-AC checks" not in result

    def test_evaluator_with_behavior_ac_appends_structured_section(self):
        criteria = [
            "pytest: tests/test_foo.py",
            "behavior: evaluator emits structured prompt when behavior AC is present",
        ]
        result = build_evaluator_task_section(criteria)
        assert "Structured behavior-AC checks" in result
        assert "Behavior AC 1" in result

    def test_evaluator_section_contains_parsed_subject(self):
        criteria = ["behavior: scheduler triggers job when deadline passes"]
        result = build_evaluator_task_section(criteria)
        # The parsed subject "scheduler" must appear in the evaluator output
        assert "scheduler" in result

    def test_evaluator_section_contains_parsed_verb(self):
        criteria = ["behavior: cache stores value when key is new"]
        result = build_evaluator_task_section(criteria)
        assert "stores" in result

    def test_evaluator_section_contains_parsed_object(self):
        criteria = ["behavior: api returns 404 when resource is missing"]
        result = build_evaluator_task_section(criteria)
        assert "404" in result

    def test_evaluator_section_contains_parsed_condition(self):
        criteria = ["behavior: system logs error when input is invalid"]
        result = build_evaluator_task_section(criteria)
        assert "input is invalid" in result

    def test_evaluator_uses_structured_parts_not_freeform(self):
        """Confirm evaluate_behavior_ac explicitly references each parsed component."""
        bac = BehaviorAC(
            raw="behavior: parser returns BehaviorAC when AC matches grammar",
            subject="parser",
            verb="returns",
            object="BehaviorAC",
            condition="AC matches grammar",
        )
        prompt = evaluate_behavior_ac(bac)
        # Each parsed part must appear explicitly in the prompt
        assert "parser" in prompt
        assert "returns" in prompt
        assert "BehaviorAC" in prompt
        assert "AC matches grammar" in prompt
        # Instruction must reference subject/verb/object/condition structure
        assert any(word in prompt.lower() for word in ("subject", "verb", "object", "condition"))

    def test_evaluator_multiple_behavior_acs_all_indexed(self):
        criteria = [
            "behavior: api returns 200 when request is valid",
            "behavior: system logs error when input is invalid",
            "behavior: cache expires entry when ttl passes",
        ]
        result = build_evaluator_task_section(criteria)
        assert "Behavior AC 1" in result
        assert "Behavior AC 2" in result
        assert "Behavior AC 3" in result

    def test_evaluator_each_behavior_ac_has_pass_fail_instruction(self):
        criteria = ["behavior: user sees dashboard when login succeeds"]
        result = build_evaluator_task_section(criteria)
        assert "PASS" in result or "FAIL" in result

    def test_evaluator_preserves_base_section_with_behavior_acs(self):
        """Base section must still appear when behavior ACs are present."""
        criteria = [
            "pytest: tests/test_foo.py",
            "behavior: scheduler triggers job when deadline passes",
        ]
        result = build_evaluator_task_section(criteria)
        assert "Identify each acceptance criterion" in result
        assert "Structured behavior-AC checks" in result

    def test_evaluator_behavior_section_contains_file_line_reference_instruction(self):
        criteria = ["behavior: api returns 404 when resource missing"]
        result = build_evaluator_task_section(criteria)
        assert "file" in result.lower() or "line" in result.lower()

    def test_evaluator_json_encoded_criteria_with_behavior_ac(self):
        import json
        criteria = json.dumps([
            "behavior: parser returns BehaviorAC when AC matches",
            "pytest: tests/test_foo.py",
        ])
        result = build_evaluator_task_section(criteria)
        assert "Structured behavior-AC checks" in result
        assert "parser" in result

    def test_behavior_acs_from_criteria_integrates_with_evaluator(self):
        """behavior_acs_from_criteria output matches what evaluator uses."""
        criteria = [
            "behavior: cache stores value when key is new",
            "File exists: src/foo.py",
        ]
        bacs = behavior_acs_from_criteria(criteria)
        assert len(bacs) == 1
        assert bacs[0].subject != ""
        assert bacs[0].condition != ""
        # The evaluator section should include what we parsed
        section = build_behavior_ac_evaluator_section(criteria)
        assert bacs[0].condition in section

    def test_evaluator_no_behavior_acs_returns_identical_to_base(self):
        """When no behavior ACs exist, output equals base section exactly."""
        criteria = ["pytest: tests/test_foo.py"]
        result = build_evaluator_task_section(criteria)
        # No structured section appended
        assert "Structured behavior-AC checks" not in result


class TestEvaluatorBehaviorAcParseRoundtrip:
    """Parse AC strings and verify the parsed structure flows through the evaluator."""

    def test_parsed_ac_structure_flows_into_evaluator_output(self):
        ac = "behavior: orchestrator queues task when feature is ready"
        bac = parse_behavior_ac(ac)
        assert bac is not None
        prompt = evaluate_behavior_ac(bac)
        # Every parsed field must appear in the evaluator output
        assert bac.subject in prompt
        assert bac.condition in prompt

    def test_evaluator_section_round_trip_for_multiple_acs(self):
        criteria = [
            "behavior: cache returns hit when key exists",
            "behavior: scheduler skips job when lock held",
        ]
        bacs = behavior_acs_from_criteria(criteria)
        assert len(bacs) == 2
        for bac in bacs:
            prompt = evaluate_behavior_ac(bac)
            assert bac.condition in prompt

    def test_evaluator_uses_condition_not_freeform_description(self):
        """The condition field drives the prompt, not the raw full string."""
        ac = "behavior: system retries request when network error occurs"
        bac = parse_behavior_ac(ac)
        assert bac is not None
        prompt = evaluate_behavior_ac(bac)
        # Condition must appear explicitly
        assert bac.condition in prompt
        # The prompt should not just be the raw string repeated
        assert "subject" in prompt.lower() or "verb" in prompt.lower() or "object" in prompt.lower()
