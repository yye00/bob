"""Tests for bob.spec_quality.behavior_ac_parser.parse_behavior_ac.

AC: spec_quality behavior-AC parser MUST accept canonical clause forms beyond
strict "subject verb object when condition".

Covers:
  - File existence: src/bob/spec_quality/behavior_ac_parser.py
  - Function: bob.spec_quality.behavior_ac_parser.parse_behavior_ac
  - Integration: bob.spec_quality exposes parse_behavior_ac
  - Canonical 'when' form
  - 'on <event>' synonym for 'when' (the F-R7-556 trigger case)
  - Compound predicates joined by 'and'
  - Edge cases: empty, missing prefix, no conditional clause
  - BehaviorAC dataclass properties
"""

import pytest

from bob.spec_quality.behavior_ac_parser import (
    parse_behavior_ac,
    accepts_synonym_conditional,
    BehaviorAC,
)


# ---------------------------------------------------------------------------
# File / module existence (AC: "File exists: src/bob/spec_quality/behavior_ac_parser.py")
# ---------------------------------------------------------------------------

def test_module_importable():
    """Module bob.spec_quality.behavior_ac_parser must be importable."""
    import bob.spec_quality.behavior_ac_parser as m
    assert m is not None


def test_parse_behavior_ac_defined():
    """Function parse_behavior_ac must exist in the module."""
    import bob.spec_quality.behavior_ac_parser as m
    assert hasattr(m, "parse_behavior_ac")
    assert callable(m.parse_behavior_ac)


# ---------------------------------------------------------------------------
# Integration AC: importable from bob.spec_quality
# ---------------------------------------------------------------------------

def test_parse_behavior_ac_importable_from_package():
    """parse_behavior_ac must be accessible as bob.spec_quality.parse_behavior_ac."""
    import bob.spec_quality as sq
    assert hasattr(sq, "parse_behavior_ac")
    assert callable(sq.parse_behavior_ac)


def test_package_import_same_object():
    """Package-level import and direct module import must resolve to the same function."""
    from bob.spec_quality import parse_behavior_ac as pkg_fn
    assert pkg_fn is parse_behavior_ac


def test_behavior_ac_importable_from_package():
    """BehaviorAC dataclass must be importable from bob.spec_quality."""
    from bob.spec_quality import BehaviorAC as pkg_cls
    assert pkg_cls is BehaviorAC


# ---------------------------------------------------------------------------
# Canonical "when" form
# ---------------------------------------------------------------------------

def test_canonical_when_simple():
    ac = "behavior: system logs error when disk is full"
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "when"
    assert "disk is full" in result.condition
    assert result.subject != ""
    assert result.verb != ""


def test_canonical_when_returns_raw():
    ac = "behavior: runner emits DONE event when task completes"
    result = parse_behavior_ac(ac)
    assert result.raw == ac


def test_canonical_when_multiline():
    ac = (
        "behavior: quarantine_corrupt_findings moves the file when "
        "yaml.scanner.ScannerError is raised"
    )
    result = parse_behavior_ac(ac)
    assert result.conditional_keyword == "when"
    assert "yaml.scanner.ScannerError" in result.condition


def test_canonical_when_case_insensitive_prefix():
    ac = "BEHAVIOR: system retries request when timeout occurs"
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "when"


def test_canonical_when_object_populated():
    ac = "behavior: scheduler enqueues job when trigger fires"
    result = parse_behavior_ac(ac)
    assert result.raw == ac
    assert result.condition != ""


# ---------------------------------------------------------------------------
# "on <event>" synonym — the F-R7-556 trigger case
# ---------------------------------------------------------------------------

def test_on_synonym_f_r7_556_verbatim():
    """The exact AC that triggered F-R7-556 must parse without raising."""
    ac = (
        "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves "
        "the offending file to <path>.corrupt.<unix_ts> and returns an "
        "empty findings dict so boot proceeds"
    )
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "on"
    assert "yaml.scanner.ScannerError" in result.condition
    assert result.subject != ""


def test_on_synonym_dotted_condition():
    """'on' with a dotted exception name is the canonical use-case (F-R7-556)."""
    ac = "behavior: cache invalidated on redis.TimeoutError"
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "on"
    assert "redis.TimeoutError" in result.condition


def test_on_subject_verb_object():
    ac = "behavior: handler on SIGTERM flushes buffer and exits"
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "on"
    assert "SIGTERM" in result.condition


def test_on_synonym_single_word_event():
    ac = "behavior: loader on ValueError returns None"
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "on"
    assert "ValueError" in result.condition


# ---------------------------------------------------------------------------
# Compound predicate with "and"
# ---------------------------------------------------------------------------

def test_compound_predicate_and_returns_when():
    """'and' in object/predicate must not confuse the parser."""
    ac = "behavior: loader reads config and sets defaults when startup begins"
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "when"
    assert "startup begins" in result.condition


def test_compound_predicate_on_synonym():
    """Compound 'and' predicate with 'on' synonym must parse cleanly."""
    ac = (
        "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError "
        "moves the offending file and returns an empty dict"
    )
    result = parse_behavior_ac(ac)
    assert isinstance(result, BehaviorAC)
    assert result.conditional_keyword == "on"


# ---------------------------------------------------------------------------
# accepts_synonym_conditional helper
# ---------------------------------------------------------------------------

def test_accepts_synonym_on_returns_true():
    ac = "behavior: handler on SIGTERM flushes buffer"
    assert accepts_synonym_conditional(ac) is True


def test_accepts_synonym_when_returns_false():
    """'when' form is not an 'on'-synonym — helper must return False."""
    ac = "behavior: system logs error when disk is full"
    assert accepts_synonym_conditional(ac) is False


def test_accepts_synonym_no_prefix_returns_false():
    assert accepts_synonym_conditional("handler on SIGTERM does something") is False


def test_accepts_synonym_no_on_returns_false():
    ac = "behavior: system does something somewhere"
    assert accepts_synonym_conditional(ac) is False


def test_accepts_synonym_f_r7_556_example_returns_true():
    """The F-R7-556 exact AC must be recognized as an 'on' synonym."""
    ac = (
        "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves "
        "the offending file to <path>.corrupt.<unix_ts> and returns an empty findings dict"
    )
    assert accepts_synonym_conditional(ac) is True


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_empty_string_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_behavior_ac("")


def test_whitespace_only_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_behavior_ac("   ")


def test_missing_behavior_prefix_raises():
    with pytest.raises(ValueError, match="behavior:"):
        parse_behavior_ac("system logs error when disk is full")


def test_no_conditional_clause_raises():
    with pytest.raises(ValueError):
        parse_behavior_ac("behavior: system logs error to disk")


# ---------------------------------------------------------------------------
# BehaviorAC dataclass
# ---------------------------------------------------------------------------

def test_behavior_ac_is_frozen():
    ac = "behavior: runner emits DONE when task completes"
    result = parse_behavior_ac(ac)
    with pytest.raises((AttributeError, TypeError)):
        result.subject = "changed"  # type: ignore[misc]


def test_behavior_ac_fields_populated():
    ac = "behavior: scheduler enqueues job when trigger fires"
    result = parse_behavior_ac(ac)
    assert result.raw == ac
    assert result.subject
    assert result.condition


def test_behavior_ac_raw_preserved():
    """raw must equal the original input string, not a normalized form."""
    ac = "behavior: system retries the request when network error occurs"
    result = parse_behavior_ac(ac)
    assert result.raw == ac


def test_behavior_ac_default_conditional_keyword():
    """conditional_keyword must default to 'when' for 'when' forms."""
    ac = "behavior: system retries the request when timeout occurs"
    result = parse_behavior_ac(ac)
    assert result.conditional_keyword == "when"


def test_behavior_ac_on_conditional_keyword():
    """conditional_keyword must be 'on' for 'on <event>' forms."""
    ac = "behavior: loader on ValueError returns empty dict"
    result = parse_behavior_ac(ac)
    assert result.conditional_keyword == "on"
