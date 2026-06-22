"""Tests for the spec_quality behavior-AC parser integration.

AC: spec_quality behavior-AC parser MUST accept canonical clause forms beyond
strict "subject verb object when condition" — overly-tight regex blocks 70%+
of well-formed behavior ACs.

Verifies:
  - File exists: src/bob3/spec_quality.py
  - Function defined: bob3.spec_quality.parse_behavior_ac
  - integration: bob3.spec_quality
  - The parser accepts canonical 'when' form
  - The parser accepts 'on <event>' synonym form (F-R7-556 trigger case)
  - The parser accepts compound predicates
  - The parser rejects malformed ACs with ValueError
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# File / module existence
# ---------------------------------------------------------------------------

def test_spec_quality_py_file_exists():
    """src/bob3/spec_quality.py must exist on disk."""
    from pathlib import Path
    path = Path(__file__).parent.parent / "src" / "bob3" / "spec_quality.py"
    assert path.exists(), f"Expected file {path} to exist"


def test_spec_quality_module_importable():
    """bob3.spec_quality must be importable."""
    import bob3.spec_quality as sq
    assert sq is not None


def test_parse_behavior_ac_defined():
    """bob3.spec_quality.parse_behavior_ac must be defined and callable."""
    from bob3.spec_quality import parse_behavior_ac
    assert callable(parse_behavior_ac)


# ---------------------------------------------------------------------------
# Canonical 'when' form
# ---------------------------------------------------------------------------

def test_canonical_when_form_accepted():
    """Parser accepts the canonical 'when' conditional form."""
    from bob3.spec_quality import parse_behavior_ac
    result = parse_behavior_ac("behavior: system logs error when disk is full")
    assert result is not None
    assert result.conditional_keyword == "when"
    assert "disk is full" in result.condition


def test_when_form_returns_behavior_ac():
    """parse_behavior_ac returns a BehaviorAC dataclass on success."""
    from bob3.spec_quality import parse_behavior_ac, BehaviorAC
    result = parse_behavior_ac("behavior: runner emits DONE event when task completes")
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "when"


# ---------------------------------------------------------------------------
# 'on <event>' synonym — F-R7-556 trigger case
# ---------------------------------------------------------------------------

def test_on_synonym_verbatim_f_r7_556():
    """The exact F-R7-556 AC must be accepted by the parser."""
    from bob3.spec_quality import parse_behavior_ac
    ac = (
        "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves "
        "the offending file to <path>.corrupt.<unix_ts> and returns an "
        "empty findings dict so boot proceeds"
    )
    result = parse_behavior_ac(ac)
    assert result.conditional_keyword == "on"
    assert "yaml.scanner.ScannerError" in result.condition


def test_on_synonym_simple():
    """Parser accepts simple 'on <exception>' form."""
    from bob3.spec_quality import parse_behavior_ac
    result = parse_behavior_ac("behavior: cache invalidated on redis.TimeoutError")
    assert result.conditional_keyword == "on"


def test_on_synonym_sigterm():
    """Parser accepts 'on SIGTERM' form with compound predicate."""
    from bob3.spec_quality import parse_behavior_ac
    result = parse_behavior_ac("behavior: handler on SIGTERM flushes buffer and exits")
    assert result.conditional_keyword == "on"
    assert "SIGTERM" in result.condition


# ---------------------------------------------------------------------------
# Compound predicates
# ---------------------------------------------------------------------------

def test_compound_predicate_and():
    """Parser accepts compound predicates joined by 'and'."""
    from bob3.spec_quality import parse_behavior_ac
    result = parse_behavior_ac(
        "behavior: loader reads config and sets defaults when startup begins"
    )
    assert result.conditional_keyword == "when"


def test_compound_predicate_on_and():
    """Parser accepts compound predicates with 'on' conditional."""
    from bob3.spec_quality import parse_behavior_ac
    result = parse_behavior_ac(
        "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError "
        "moves the offending file and returns an empty dict"
    )
    assert result.conditional_keyword == "on"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_empty_string_raises_value_error():
    """Empty string must raise ValueError."""
    from bob3.spec_quality import parse_behavior_ac
    with pytest.raises(ValueError):
        parse_behavior_ac("")


def test_no_behavior_prefix_raises_value_error():
    """String without 'behavior:' prefix must raise ValueError."""
    from bob3.spec_quality import parse_behavior_ac
    with pytest.raises(ValueError):
        parse_behavior_ac("system logs error when disk is full")


def test_no_conditional_clause_raises_value_error():
    """String with 'behavior:' prefix but no 'when'/'on' must raise ValueError."""
    from bob3.spec_quality import parse_behavior_ac
    with pytest.raises(ValueError):
        parse_behavior_ac("behavior: system does something somewhere")


def test_error_message_is_non_empty():
    """ValueError message must be descriptive."""
    from bob3.spec_quality import parse_behavior_ac
    with pytest.raises(ValueError) as exc_info:
        parse_behavior_ac("")
    assert str(exc_info.value)


# ---------------------------------------------------------------------------
# Integration: accepts_synonym_conditional
# ---------------------------------------------------------------------------

def test_accepts_synonym_conditional_defined():
    """bob3.spec_quality.accepts_synonym_conditional must be callable."""
    from bob3.spec_quality import accepts_synonym_conditional
    assert callable(accepts_synonym_conditional)


def test_accepts_synonym_conditional_on_true():
    """accepts_synonym_conditional returns True for 'on' synonym form."""
    from bob3.spec_quality import accepts_synonym_conditional
    ac = "behavior: cache invalidated on redis.TimeoutError"
    assert accepts_synonym_conditional(ac) is True


def test_accepts_synonym_conditional_when_false():
    """accepts_synonym_conditional returns False for canonical 'when' form."""
    from bob3.spec_quality import accepts_synonym_conditional
    assert accepts_synonym_conditional("behavior: system logs error when disk full") is False


def test_accepts_synonym_conditional_no_prefix_false():
    """accepts_synonym_conditional returns False when no 'behavior:' prefix."""
    from bob3.spec_quality import accepts_synonym_conditional
    assert accepts_synonym_conditional("cache invalidated on redis.TimeoutError") is False


# ---------------------------------------------------------------------------
# BehaviorAC dataclass fields
# ---------------------------------------------------------------------------

def test_behavior_ac_raw_preserved():
    """BehaviorAC.raw preserves the original AC string."""
    from bob3.spec_quality import parse_behavior_ac
    ac = "behavior: system retries request when network error occurs"
    result = parse_behavior_ac(ac)
    assert result.raw == ac


def test_behavior_ac_has_condition_field():
    """BehaviorAC.condition is populated for valid ACs."""
    from bob3.spec_quality import parse_behavior_ac
    result = parse_behavior_ac("behavior: loader writes log when startup completes")
    assert result.condition
    assert "startup completes" in result.condition
