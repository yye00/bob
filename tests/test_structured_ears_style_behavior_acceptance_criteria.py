"""Tests for structured EARS-style behavior acceptance criteria (feature 31e90796).

Verifies the sixth AC grammar:
    behavior: <subject> <verb> <object> when <condition>

The ``structured_ears_style_behavior_acceptance_criteria`` function must:
1. Parse the behavior: AC into a structured tuple (subject, verb, object, condition).
2. Return a structured evaluator check based on the parsed tuple — not freeform prose.
3. Return None for non-behavior ACs (e.g. pytest:, File exists:).
"""

from __future__ import annotations

import pytest

from bob3.structured_ears_style_behavior_acceptance_criteria import (
    structured_ears_style_behavior_acceptance_criteria,
)


def test_structured_ears_style_behavior_acceptance_criteria():
    """Canonical test: parse a behavior AC and verify the structured output."""
    ac = "behavior: parser returns BehaviorAC when AC matches grammar"
    result = structured_ears_style_behavior_acceptance_criteria(ac)

    assert result is not None
    # Result must be a dict with the four parsed components
    assert "subject" in result
    assert "verb" in result
    assert "object" in result
    assert "condition" in result
    # Values must be populated from the parsed AC
    assert result["subject"] == "parser"
    assert result["verb"] == "returns"
    assert result["object"] == "BehaviorAC"
    assert result["condition"] == "AC matches grammar"


def test_returns_none_for_non_behavior_ac():
    """Non-behavior ACs must return None."""
    assert structured_ears_style_behavior_acceptance_criteria("pytest: tests/test_foo.py") is None
    assert structured_ears_style_behavior_acceptance_criteria("File exists: src/foo.py") is None
    assert structured_ears_style_behavior_acceptance_criteria("Function defined: foo.bar") is None
    assert structured_ears_style_behavior_acceptance_criteria("integration: bob3.cli") is None


def test_parse_various_behavior_acs():
    """Multiple well-formed behavior ACs should all parse correctly."""
    cases = [
        (
            "behavior: scheduler triggers job when deadline passes",
            {"subject": "scheduler", "verb": "triggers", "object": "job", "condition": "deadline passes"},
        ),
        (
            "behavior: api returns 404 when resource is missing",
            {"subject": "api", "verb": "returns", "object": "404", "condition": "resource is missing"},
        ),
        (
            "behavior: cache stores value when key is new",
            {"subject": "cache", "verb": "stores", "object": "value", "condition": "key is new"},
        ),
    ]
    for ac, expected in cases:
        result = structured_ears_style_behavior_acceptance_criteria(ac)
        assert result is not None, f"Expected non-None for: {ac!r}"
        assert result["subject"] == expected["subject"], f"Subject mismatch for {ac!r}"
        assert result["condition"] == expected["condition"], f"Condition mismatch for {ac!r}"


def test_result_contains_evaluator_check():
    """Result must include an 'evaluator_check' key with structured prompt text."""
    ac = "behavior: system logs error when input is invalid"
    result = structured_ears_style_behavior_acceptance_criteria(ac)
    assert result is not None
    assert "evaluator_check" in result
    check = result["evaluator_check"]
    assert isinstance(check, str)
    assert len(check) > 0
    # The evaluator check must reference the parsed fields — not just the raw string
    assert "system" in check
    assert "input is invalid" in check


def test_evaluator_check_references_all_parsed_parts():
    """All four parsed parts must appear in the evaluator_check string."""
    ac = "behavior: orchestrator queues task when feature is ready"
    result = structured_ears_style_behavior_acceptance_criteria(ac)
    assert result is not None
    check = result["evaluator_check"]
    assert "orchestrator" in check
    assert "queues" in check
    assert "task" in check
    assert "feature is ready" in check


def test_raw_ac_preserved_in_result():
    """The raw AC string must be preserved in the result."""
    ac = "behavior: user sees dashboard when login succeeds"
    result = structured_ears_style_behavior_acceptance_criteria(ac)
    assert result is not None
    assert "raw" in result
    assert result["raw"] == ac


def test_empty_string_returns_none():
    """Empty string must return None."""
    assert structured_ears_style_behavior_acceptance_criteria("") is None


def test_behavior_ac_without_when_returns_none():
    """A behavior: AC lacking 'when' is malformed and must return None."""
    result = structured_ears_style_behavior_acceptance_criteria("behavior: parser returns value")
    assert result is None


def test_evaluator_check_uses_structure_not_freeform():
    """Evaluator check must label subject/verb/object/condition — not be free prose."""
    ac = "behavior: cache expires entry when ttl passes"
    result = structured_ears_style_behavior_acceptance_criteria(ac)
    assert result is not None
    check = result["evaluator_check"]
    # Must reference structural concepts
    assert any(term in check.lower() for term in ("subject", "verb", "object", "condition", "when"))
