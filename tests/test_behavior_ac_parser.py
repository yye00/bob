"""Tests for bob.parser.behavior_ac_parser.

AC: spec_quality behavior-AC parser MUST accept canonical clause forms beyond strict
"subject verb object when condition" — overly-tight regex blocks 70%+ of well-formed
behavior ACs.

Covers:
  - Module importable from bob.parser.behavior_ac_parser
  - parse_behavior_ac defined and callable
  - F-R7-556 AC string accepted (on-synonym form)
  - Canonical 'when' form accepted
  - Compound predicates accepted
  - Empty / malformed inputs raise ValueError
"""

from __future__ import annotations

import pytest
from bob.parser.behavior_ac_parser import (
    BehaviorAC,
    parse_behavior_ac,
    accepts_synonym_conditional,
)

_F_R7_556_AC = (
    "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves "
    "the offending file to <path>.corrupt.<unix_ts> and returns an "
    "empty findings dict so boot proceeds"
)


class TestModuleAPI:
    def test_parse_behavior_ac_callable(self):
        assert callable(parse_behavior_ac)

    def test_accepts_synonym_conditional_callable(self):
        assert callable(accepts_synonym_conditional)

    def test_behavior_ac_dataclass(self):
        ac = BehaviorAC(
            raw="behavior: x does y when z",
            subject="x",
            verb="does",
            object="y",
            condition="z",
            conditional_keyword="when",
        )
        assert ac.subject == "x"


class TestFR7556TriggerCase:
    """The exact AC from F-R7-556 must parse without raising."""

    def test_parses_without_exception(self):
        result = parse_behavior_ac(_F_R7_556_AC)
        assert isinstance(result, BehaviorAC)

    def test_uses_on_keyword(self):
        result = parse_behavior_ac(_F_R7_556_AC)
        assert result.conditional_keyword == "on"

    def test_subject_populated(self):
        result = parse_behavior_ac(_F_R7_556_AC)
        assert result.subject

    def test_condition_populated(self):
        result = parse_behavior_ac(_F_R7_556_AC)
        assert result.condition

    def test_condition_contains_scanner_error(self):
        result = parse_behavior_ac(_F_R7_556_AC)
        assert "ScannerError" in result.condition or "scanner" in result.condition.lower()

    def test_accepts_synonym_conditional_true(self):
        assert accepts_synonym_conditional(_F_R7_556_AC) is True


class TestCanonicalWhenForm:
    def test_simple_when_form(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_ac(ac)
        assert isinstance(result, BehaviorAC)
        assert result.conditional_keyword == "when"

    def test_when_condition_populated(self):
        ac = "behavior: scheduler enqueues job when trigger fires"
        result = parse_behavior_ac(ac)
        assert "trigger fires" in result.condition

    def test_when_subject_populated(self):
        ac = "behavior: runner emits DONE event when task completes"
        result = parse_behavior_ac(ac)
        assert result.subject


class TestOnSynonymForm:
    def test_on_dotted_exception(self):
        ac = "behavior: loader on ValueError returns None"
        result = parse_behavior_ac(ac)
        assert result.conditional_keyword == "on"

    def test_on_sigterm(self):
        ac = "behavior: handler on SIGTERM flushes buffer and exits"
        result = parse_behavior_ac(ac)
        assert result.conditional_keyword == "on"
        assert "SIGTERM" in result.condition

    def test_on_suffix_form(self):
        ac = "behavior: cache invalidated on redis.TimeoutError"
        result = parse_behavior_ac(ac)
        assert result.conditional_keyword == "on"


class TestCompoundPredicates:
    def test_compound_and_when(self):
        ac = "behavior: loader reads config and sets defaults when startup begins"
        result = parse_behavior_ac(ac)
        assert result.conditional_keyword == "when"

    def test_compound_and_on(self):
        ac = (
            "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError "
            "moves the offending file and returns an empty dict"
        )
        result = parse_behavior_ac(ac)
        assert result.conditional_keyword == "on"


class TestErrorPaths:
    def test_empty_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("")

    def test_no_behavior_prefix_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("system logs error when disk is full")

    def test_no_conditional_clause_raises(self):
        with pytest.raises(ValueError):
            parse_behavior_ac("behavior: system does something somewhere")

    def test_error_message_non_empty(self):
        with pytest.raises(ValueError) as exc_info:
            parse_behavior_ac("")
        assert str(exc_info.value)
