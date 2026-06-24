"""Tests for behavior_ac_parser synonym and canonical form parsing.

Covers:
- F-R7-556 AC string parses without warning (on-synonym form)
- Canonical 'when' form still parses (no regression)
- Compound predicates joined by 'and' are accepted
"""

from __future__ import annotations

import pytest
from bob.spec_quality.behavior_ac_parser import (
    BehaviorAC,
    parse_behavior_ac,
    accepts_synonym_conditional,
)

# The exact AC string from F-R7-556 that triggered the feature
_F_R7_556_AC = (
    "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves"
    " the offending file to <path>.corrupt.<unix_ts> and returns an"
    " empty findings dict so boot proceeds"
)


class TestFR7556AcParses:
    """The F-R7-556 AC string must parse without raising or returning partial results."""

    def test_fr7556_parses_without_exception(self):
        result = parse_behavior_ac(_F_R7_556_AC)
        assert isinstance(result, BehaviorAC)

    def test_fr7556_subject_is_populated(self):
        result = parse_behavior_ac(_F_R7_556_AC)
        assert result.subject, "subject must be non-empty"

    def test_fr7556_condition_is_populated(self):
        result = parse_behavior_ac(_F_R7_556_AC)
        assert result.condition, "condition must be non-empty"

    def test_fr7556_condition_contains_scanner_error(self):
        result = parse_behavior_ac(_F_R7_556_AC)
        assert "ScannerError" in result.condition or "scanner" in result.condition.lower()

    def test_fr7556_uses_on_keyword(self):
        result = parse_behavior_ac(_F_R7_556_AC)
        assert result.conditional_keyword == "on"

    def test_fr7556_accepts_synonym_conditional_returns_true(self):
        assert accepts_synonym_conditional(_F_R7_556_AC) is True


class TestCanonicalWhenFormRegression:
    """Canonical 'when' form must still parse correctly (no regression)."""

    def test_simple_when_form_parses(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_ac(ac)
        assert isinstance(result, BehaviorAC)

    def test_when_form_subject(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_ac(ac)
        assert result.subject == "parser"

    def test_when_form_verb(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_ac(ac)
        assert result.verb == "returns"

    def test_when_form_object(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_ac(ac)
        assert result.object == "BehaviorAC"

    def test_when_form_condition(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_ac(ac)
        assert result.condition == "AC matches grammar"

    def test_when_form_conditional_keyword(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        result = parse_behavior_ac(ac)
        assert result.conditional_keyword == "when"

    def test_accepts_synonym_conditional_false_for_when_form(self):
        ac = "behavior: parser returns BehaviorAC when AC matches grammar"
        assert accepts_synonym_conditional(ac) is False


class TestCompoundPredicates:
    """Compound predicates joined by 'and' must be accepted as a single clause."""

    def test_compound_and_verb_parses(self):
        ac = "behavior: writer moves file to dest and returns True when write succeeds"
        result = parse_behavior_ac(ac)
        assert isinstance(result, BehaviorAC)
        assert result.condition, "condition must be populated"

    def test_compound_on_form_parses(self):
        ac = "behavior: handler on KeyboardInterrupt flushes buffer and exits cleanly"
        result = parse_behavior_ac(ac)
        assert isinstance(result, BehaviorAC)
        assert result.condition, "condition must be populated"

    def test_compound_predicate_condition_populated(self):
        ac = "behavior: loader on FileNotFoundError logs error and returns empty dict"
        result = parse_behavior_ac(ac)
        assert result.condition

    def test_compound_predicate_subject_populated(self):
        ac = "behavior: loader on FileNotFoundError logs error and returns empty dict"
        result = parse_behavior_ac(ac)
        assert result.subject == "loader"


class TestOnSynonymVariants:
    """Various 'on <event>' synonym forms must be accepted."""

    def test_on_exception_class(self):
        ac = "behavior: cache on CacheMiss fetches from upstream"
        result = parse_behavior_ac(ac)
        assert isinstance(result, BehaviorAC)
        assert "CacheMiss" in result.condition

    def test_accepts_synonym_conditional_on_exception(self):
        ac = "behavior: cache on CacheMiss fetches from upstream"
        assert accepts_synonym_conditional(ac) is True

    def test_accepts_synonym_conditional_false_for_non_behavior(self):
        ac = "pytest: tests/test_foo.py"
        assert accepts_synonym_conditional(ac) is False
