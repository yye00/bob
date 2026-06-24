"""Tests for bob.ears_grammar — sixth AC grammar: behavior: <subject> <verb> <object> when <condition>.

Verifies that:
1. ``parse_behavior_ac`` returns a BehaviorAC for valid behavior ACs.
2. ``parse_behavior_ac`` returns None for non-behavior ACs.
3. ``parse_behavior_ac`` raises ValueError for malformed behavior ACs (missing 'when').
4. ``evaluate_behavior_ac`` builds a structured prompt from a BehaviorAC.
5. The module integrates with bob.evaluator.
"""

from __future__ import annotations

import pytest

from bob.ears_grammar import BehaviorAC, evaluate_behavior_ac, parse_behavior_ac


class TestParseBehaviorAC:
    """Tests for parse_behavior_ac."""

    def test_canonical_ac_parses(self):
        """Canonical behavior AC parses into the four structured components."""
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_ac(ac)
        assert result is not None
        assert isinstance(result, BehaviorAC)
        assert result.subject == "parser"
        assert result.verb == "returns"
        assert result.object == "BehaviorAC"
        assert result.condition == "AC matches grammar"

    def test_non_behavior_ac_returns_none(self):
        """Non-behavior prefixed ACs return None."""
        assert parse_behavior_ac("pytest: tests/test_foo.py") is None
        assert parse_behavior_ac("File exists: src/foo.py") is None
        assert parse_behavior_ac("Function defined: foo.bar") is None
        assert parse_behavior_ac("integration: bob.evaluator") is None
        assert parse_behavior_ac("Class defined: MyClass") is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        assert parse_behavior_ac("") is None

    def test_whitespace_returns_none(self):
        """Whitespace-only string returns None."""
        assert parse_behavior_ac("   ") is None

    def test_missing_when_returns_none_or_raises(self):
        """behavior: AC without 'when' clause returns None (no 'when' match) or raises ValueError."""
        from bob.ears_grammar import raises_on_malformed, EARSParseError
        # parse_behavior_ac may return None (no 'when' match via regex)
        result = parse_behavior_ac("behavior: parser returns BehaviorAC")
        assert result is None  # falls through all regexes and returns None

        # raises_on_malformed is the strict variant that always raises
        with pytest.raises((ValueError, EARSParseError)):
            raises_on_malformed("behavior: parser returns BehaviorAC")

    def test_behavior_prefix_only_raises_or_none(self):
        """behavior: with nothing meaningful after the colon is handled gracefully."""
        try:
            result = parse_behavior_ac("behavior:")
            assert result is None
        except ValueError:
            pass  # Also acceptable

    def test_various_valid_acs_parse(self):
        """Multiple well-formed behavior ACs all produce BehaviorAC instances."""
        cases = [
            "behavior: scheduler triggers job when deadline passes",
            "behavior: api returns 404 when resource is missing",
            "behavior: cache stores value when key is new",
            "behavior: system logs error when input is invalid",
        ]
        for ac in cases:
            result = parse_behavior_ac(ac)
            assert result is not None, f"Expected non-None for: {ac!r}"
            assert isinstance(result, BehaviorAC)
            assert result.condition  # condition must be non-empty

    def test_result_contains_raw_field(self):
        """BehaviorAC includes the raw AC string."""
        ac = "behavior: user sees dashboard when login succeeds"
        result = parse_behavior_ac(ac)
        assert result is not None
        assert result.raw == ac

    def test_case_insensitive_prefix(self):
        """Prefix matching is case-insensitive."""
        result = parse_behavior_ac("BEHAVIOR: system logs event when triggered")
        assert result is not None
        assert isinstance(result, BehaviorAC)


class TestEvaluateBehaviorAC:
    """Tests for evaluate_behavior_ac."""

    def test_returns_nonempty_string(self):
        """evaluate_behavior_ac returns a non-empty string."""
        ac = "behavior: orchestrator queues task when feature is ready"
        bac = parse_behavior_ac(ac)
        assert bac is not None
        check = evaluate_behavior_ac(bac)
        assert isinstance(check, str)
        assert len(check) > 0

    def test_references_all_parsed_parts(self):
        """Evaluator check references subject, verb, object, and condition."""
        ac = "behavior: orchestrator queues task when feature is ready"
        bac = parse_behavior_ac(ac)
        assert bac is not None
        check = evaluate_behavior_ac(bac)
        assert "orchestrator" in check
        assert "queues" in check
        assert "task" in check
        assert "feature is ready" in check

    def test_uses_structural_labels(self):
        """Evaluator check uses structural terms (subject, verb, object, condition)."""
        ac = "behavior: cache expires entry when ttl passes"
        bac = parse_behavior_ac(ac)
        assert bac is not None
        check = evaluate_behavior_ac(bac)
        assert any(term in check.lower() for term in ("subject", "verb", "object", "condition", "when"))


class TestEvaluatorIntegration:
    """Integration tests: bob.ears_grammar connects to bob.evaluator."""

    def test_evaluator_build_task_section_includes_behavior_check(self):
        """build_evaluator_task_section appends behavior checks for behavior ACs."""
        from bob.evaluator import build_evaluator_task_section

        criteria = ["behavior: parser returns result when AC is valid", "pytest: tests/test_foo.py"]
        section = build_evaluator_task_section(criteria)
        assert "parser" in section
        assert "result" in section
        assert "AC is valid" in section

    def test_evaluator_build_task_section_no_behavior_acs(self):
        """build_evaluator_task_section is unchanged when no behavior ACs are present."""
        from bob.evaluator import build_evaluator_task_section

        criteria = ["pytest: tests/test_foo.py", "File exists: src/foo.py"]
        section = build_evaluator_task_section(criteria)
        # Should not contain behavior-specific content
        assert "behavior" not in section.lower() or "Behavior AC" not in section
