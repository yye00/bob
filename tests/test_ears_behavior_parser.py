"""Tests for bob.ears_behavior_parser.parse_behavior_ac.

Verifies the sixth AC grammar:
    behavior: <subject> <verb> <object> when <condition>

The ``parse_behavior_ac`` function must:
1. Parse a well-formed behavior: AC into a structured dict.
2. Return None for non-behavior ACs and malformed behavior ACs (no when clause).
3. Populate subject, verb, object, condition, evaluator_check, and raw keys.
4. Produce an evaluator_check that references parsed structural fields.
"""

from __future__ import annotations

import pytest

from bob.ears_behavior_parser import parse_behavior_ac


# ---------------------------------------------------------------------------
# Happy path — well-formed behavior ACs
# ---------------------------------------------------------------------------


def test_canonical_behavior_ac_parses():
    """Canonical behavior AC returns a dict with all required keys."""
    ac = "behavior: parser returns BehaviorAC when AC matches grammar"
    result = parse_behavior_ac(ac)

    assert result is not None
    assert result["subject"] == "parser"
    assert result["verb"] == "returns"
    assert result["object"] == "BehaviorAC"
    assert result["condition"] == "AC matches grammar"


def test_result_contains_all_required_keys():
    """Result dict must contain subject, verb, object, condition, evaluator_check, raw."""
    ac = "behavior: scheduler triggers job when deadline passes"
    result = parse_behavior_ac(ac)

    assert result is not None
    assert set(result.keys()) >= {"subject", "verb", "object", "condition", "evaluator_check", "raw"}


def test_raw_ac_preserved():
    """The raw AC string must be preserved verbatim in result['raw']."""
    ac = "behavior: user sees dashboard when login succeeds"
    result = parse_behavior_ac(ac)

    assert result is not None
    assert result["raw"] == ac


def test_evaluator_check_is_non_empty_string():
    """evaluator_check must be a non-empty string."""
    ac = "behavior: system logs error when input is invalid"
    result = parse_behavior_ac(ac)

    assert result is not None
    check = result["evaluator_check"]
    assert isinstance(check, str)
    assert len(check) > 0


def test_evaluator_check_references_subject():
    """evaluator_check must reference the parsed subject."""
    ac = "behavior: orchestrator queues task when feature is ready"
    result = parse_behavior_ac(ac)

    assert result is not None
    assert "orchestrator" in result["evaluator_check"]


def test_evaluator_check_references_condition():
    """evaluator_check must reference the parsed condition."""
    ac = "behavior: system logs error when input is invalid"
    result = parse_behavior_ac(ac)

    assert result is not None
    assert "input is invalid" in result["evaluator_check"]


def test_evaluator_check_references_all_parsed_parts():
    """All four parsed parts must appear in evaluator_check."""
    ac = "behavior: orchestrator queues task when feature is ready"
    result = parse_behavior_ac(ac)

    assert result is not None
    check = result["evaluator_check"]
    assert "orchestrator" in check
    assert "queues" in check
    assert "task" in check
    assert "feature is ready" in check


def test_evaluator_check_uses_structural_labels():
    """evaluator_check must label subject/verb/object/condition structurally."""
    ac = "behavior: cache expires entry when ttl passes"
    result = parse_behavior_ac(ac)

    assert result is not None
    check = result["evaluator_check"].lower()
    assert any(term in check for term in ("subject", "verb", "object", "condition", "when"))


# ---------------------------------------------------------------------------
# Multiple well-formed ACs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ac,expected_subject,expected_condition", [
    (
        "behavior: scheduler triggers job when deadline passes",
        "scheduler",
        "deadline passes",
    ),
    (
        "behavior: api returns 404 when resource is missing",
        "api",
        "resource is missing",
    ),
    (
        "behavior: cache stores value when key is new",
        "cache",
        "key is new",
    ),
])
def test_various_well_formed_acs(ac, expected_subject, expected_condition):
    """Multiple well-formed behavior ACs all parse correctly."""
    result = parse_behavior_ac(ac)

    assert result is not None, f"Expected non-None for {ac!r}"
    assert result["subject"] == expected_subject
    assert result["condition"] == expected_condition


# ---------------------------------------------------------------------------
# Non-behavior ACs → None
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ac", [
    "pytest: tests/test_foo.py",
    "File exists: src/foo.py",
    "Function defined: foo.bar",
    "integration: bob.cli",
    "integration: bob.orchestrator",
])
def test_non_behavior_ac_returns_none(ac):
    """Non-behavior ACs must return None."""
    assert parse_behavior_ac(ac) is None


# ---------------------------------------------------------------------------
# Malformed behavior ACs (missing when) → None
# ---------------------------------------------------------------------------


def test_behavior_ac_without_when_returns_none():
    """Malformed behavior: AC without 'when' must return None (not raise)."""
    result = parse_behavior_ac("behavior: parser returns value")
    assert result is None


def test_behavior_ac_no_when_does_not_raise():
    """parse_behavior_ac must not raise for malformed behavior: ACs."""
    # Should return None, swallowing the ValueError from the underlying parser
    result = parse_behavior_ac("behavior: system does something without when")
    assert result is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_string_returns_none():
    """Empty string must return None."""
    assert parse_behavior_ac("") is None


def test_whitespace_only_returns_none():
    """Whitespace-only string must return None."""
    assert parse_behavior_ac("   ") is None


def test_numeric_object_parses():
    """Numeric token in the AC parses correctly."""
    ac = "behavior: api returns 404 when resource is missing"
    result = parse_behavior_ac(ac)
    assert result is not None
    assert result["object"] == "404"
