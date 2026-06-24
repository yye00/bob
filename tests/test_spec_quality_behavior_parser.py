"""Tests for bob.spec_quality.parse_behavior_ac integration.

AC: pytest: tests/test_spec_quality_behavior_parser.py
    spec_quality behavior-AC parser MUST accept canonical clause forms beyond
    strict "subject verb object when condition" — overly-tight regex blocks 70%+
    of well-formed behavior ACs.

Verifies:
  - parse_behavior_ac importable from bob.spec_quality
  - BehaviorAC importable from bob.spec_quality
  - Canonical 'when' form accepted
  - 'on <event>' synonym accepted (F-R7-556 trigger case)
  - Compound predicates joined by 'and' accepted
  - Invalid inputs raise ValueError
"""

from __future__ import annotations

import pytest

from bob.spec_quality import (
    parse_behavior_ac,
    accepts_synonym_conditional,
    BehaviorAC,
)


# ---------------------------------------------------------------------------
# Integration: importable from bob.spec_quality
# ---------------------------------------------------------------------------

def test_parse_behavior_ac_importable():
    """parse_behavior_ac must be accessible from bob.spec_quality."""
    import bob.spec_quality as sq
    assert hasattr(sq, "parse_behavior_ac")
    assert callable(sq.parse_behavior_ac)


def test_behavior_ac_dataclass_importable():
    """BehaviorAC dataclass must be importable from bob.spec_quality."""
    import bob.spec_quality as sq
    assert hasattr(sq, "BehaviorAC")


def test_accepts_synonym_conditional_importable():
    """accepts_synonym_conditional must be importable from bob.spec_quality."""
    import bob.spec_quality as sq
    assert hasattr(sq, "accepts_synonym_conditional")
    assert callable(sq.accepts_synonym_conditional)


# ---------------------------------------------------------------------------
# Canonical "when" form
# ---------------------------------------------------------------------------

def test_canonical_when_form_accepted():
    ac = "behavior: system logs error when disk is full"
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "when"


def test_canonical_when_condition_populated():
    ac = "behavior: runner emits DONE event when task completes"
    result = parse_behavior_ac(ac)
    assert "task completes" in result.condition


def test_canonical_when_raw_preserved():
    ac = "behavior: scheduler enqueues job when trigger fires"
    result = parse_behavior_ac(ac)
    assert result.raw == ac


def test_canonical_when_subject_populated():
    ac = "behavior: loader reads config when startup begins"
    result = parse_behavior_ac(ac)
    assert result.subject != ""


# ---------------------------------------------------------------------------
# "on <event>" synonym — F-R7-556 trigger case
# ---------------------------------------------------------------------------

def test_on_synonym_f_r7_556_trigger():
    """The exact AC from F-R7-556 must parse without raising."""
    ac = (
        "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves "
        "the offending file to <path>.corrupt.<unix_ts> and returns an "
        "empty findings dict so boot proceeds"
    )
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "on"
    assert "yaml.scanner.ScannerError" in result.condition


def test_on_synonym_dotted_event():
    ac = "behavior: cache invalidated on redis.TimeoutError"
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "on"
    assert "redis.TimeoutError" in result.condition


def test_on_synonym_simple_event():
    ac = "behavior: loader on ValueError returns None"
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "on"


def test_accepts_synonym_conditional_for_on_form():
    ac = "behavior: handler on SIGTERM flushes buffer"
    assert accepts_synonym_conditional(ac) is True


def test_accepts_synonym_conditional_false_for_when():
    ac = "behavior: system logs error when disk is full"
    assert accepts_synonym_conditional(ac) is False


# ---------------------------------------------------------------------------
# Compound predicates
# ---------------------------------------------------------------------------

def test_compound_predicate_when_form():
    ac = "behavior: loader reads config and sets defaults when startup begins"
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "when"
    assert "startup begins" in result.condition


def test_compound_predicate_on_form():
    ac = (
        "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError "
        "moves the offending file and returns an empty dict"
    )
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "on"


# ---------------------------------------------------------------------------
# Error cases — invalid input must raise ValueError
# ---------------------------------------------------------------------------

def test_empty_string_raises_value_error():
    with pytest.raises(ValueError):
        parse_behavior_ac("")


def test_whitespace_only_raises_value_error():
    with pytest.raises(ValueError):
        parse_behavior_ac("   ")


def test_missing_behavior_prefix_raises_value_error():
    with pytest.raises(ValueError):
        parse_behavior_ac("system logs error when disk is full")


def test_no_conditional_clause_raises_value_error():
    with pytest.raises(ValueError):
        parse_behavior_ac("behavior: system logs error to disk")


# ---------------------------------------------------------------------------
# BehaviorAC dataclass properties
# ---------------------------------------------------------------------------

def test_behavior_ac_is_frozen():
    ac = "behavior: runner emits DONE when task completes"
    result = parse_behavior_ac(ac)
    with pytest.raises((AttributeError, TypeError)):
        result.subject = "changed"  # type: ignore[misc]


def test_behavior_ac_fields_exist():
    ac = "behavior: scheduler enqueues job when trigger fires"
    result = parse_behavior_ac(ac)
    assert hasattr(result, "raw")
    assert hasattr(result, "subject")
    assert hasattr(result, "verb")
    assert hasattr(result, "object")
    assert hasattr(result, "condition")
    assert hasattr(result, "conditional_keyword")
