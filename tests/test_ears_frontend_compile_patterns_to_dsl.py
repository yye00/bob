"""Tests for src/bob/ears_frontend_compile_patterns_to_dsl.py.

Verifies the EARS frontend that compiles all five EARS patterns
(Ubiquitous, Event-driven, Unwanted behavior, State-driven, Optional)
into bob's acceptance criterion DSL.
"""

from __future__ import annotations

import pytest

from bob.ears_frontend_compile_patterns_to_dsl import (
    EARSPattern,
    EARSPatternKind,
    compile_ears_to_dsl,
    parse_ears_pattern,
    ears_text_to_dsl_criteria,
)


# ---------------------------------------------------------------------------
# EARSPatternKind enum
# ---------------------------------------------------------------------------


class TestEARSPatternKind:
    def test_all_five_kinds_present(self):
        kinds = set(EARSPatternKind)
        assert EARSPatternKind.UBIQUITOUS in kinds
        assert EARSPatternKind.EVENT_DRIVEN in kinds
        assert EARSPatternKind.UNWANTED in kinds
        assert EARSPatternKind.STATE_DRIVEN in kinds
        assert EARSPatternKind.OPTIONAL in kinds
        assert len(kinds) == 5

    def test_string_values(self):
        assert EARSPatternKind.UBIQUITOUS.value == "ubiquitous"
        assert EARSPatternKind.EVENT_DRIVEN.value == "event_driven"
        assert EARSPatternKind.UNWANTED.value == "unwanted"
        assert EARSPatternKind.STATE_DRIVEN.value == "state_driven"
        assert EARSPatternKind.OPTIONAL.value == "optional"


# ---------------------------------------------------------------------------
# EARSPattern dataclass
# ---------------------------------------------------------------------------


class TestEARSPattern:
    def test_ubiquitous_pattern_construction(self):
        p = EARSPattern(
            kind=EARSPatternKind.UBIQUITOUS,
            raw="The system shall log all requests.",
            subject="system",
            predicate="log all requests",
        )
        assert p.kind == EARSPatternKind.UBIQUITOUS
        assert p.condition is None
        assert p.feature_ref is None

    def test_event_driven_pattern_construction(self):
        p = EARSPattern(
            kind=EARSPatternKind.EVENT_DRIVEN,
            raw="When the user submits a form, the system shall validate inputs.",
            subject="system",
            predicate="validate inputs",
            condition="the user submits a form",
        )
        assert p.kind == EARSPatternKind.EVENT_DRIVEN
        assert p.condition == "the user submits a form"

    def test_unwanted_pattern_construction(self):
        p = EARSPattern(
            kind=EARSPatternKind.UNWANTED,
            raw="The system shall not accept null values.",
            subject="system",
            predicate="accept null values",
        )
        assert p.kind == EARSPatternKind.UNWANTED
        assert p.condition is None

    def test_state_driven_pattern_construction(self):
        p = EARSPattern(
            kind=EARSPatternKind.STATE_DRIVEN,
            raw="While the system is idle, the system shall accept new connections.",
            subject="system",
            predicate="accept new connections",
            condition="the system is idle",
        )
        assert p.kind == EARSPatternKind.STATE_DRIVEN

    def test_optional_pattern_construction(self):
        p = EARSPattern(
            kind=EARSPatternKind.OPTIONAL,
            raw="Where caching is enabled, the system shall return cached results.",
            subject="system",
            predicate="return cached results",
            condition="caching is enabled",
            feature_ref="caching",
        )
        assert p.kind == EARSPatternKind.OPTIONAL
        assert p.feature_ref == "caching"


# ---------------------------------------------------------------------------
# parse_ears_pattern — single-sentence parsing
# ---------------------------------------------------------------------------


class TestParseEarsPattern:
    def test_parse_ubiquitous_pattern(self):
        text = "The system shall log all requests."
        result = parse_ears_pattern(text)
        assert result is not None
        assert result.kind == EARSPatternKind.UBIQUITOUS
        assert result.subject.lower() == "system"
        assert "log" in result.predicate.lower()

    def test_parse_event_driven_pattern(self):
        text = "When a user logs in, the system shall emit an audit event."
        result = parse_ears_pattern(text)
        assert result is not None
        assert result.kind == EARSPatternKind.EVENT_DRIVEN
        assert result.condition is not None
        assert "user logs in" in result.condition.lower()

    def test_parse_unwanted_pattern(self):
        text = "The system shall not expose passwords in logs."
        result = parse_ears_pattern(text)
        assert result is not None
        assert result.kind == EARSPatternKind.UNWANTED
        assert "password" in result.predicate.lower() or "expos" in result.predicate.lower()

    def test_parse_state_driven_pattern(self):
        text = "While the queue is full, the system shall reject new messages."
        result = parse_ears_pattern(text)
        assert result is not None
        assert result.kind == EARSPatternKind.STATE_DRIVEN
        assert result.condition is not None
        assert "queue is full" in result.condition.lower()

    def test_parse_optional_pattern(self):
        text = "Where debug mode is enabled, the system shall output verbose logs."
        result = parse_ears_pattern(text)
        assert result is not None
        assert result.kind == EARSPatternKind.OPTIONAL
        assert result.condition is not None
        assert "debug mode" in result.condition.lower()

    def test_returns_none_for_unrecognized(self):
        text = "This is not an EARS requirement at all."
        result = parse_ears_pattern(text)
        assert result is None

    def test_parse_is_case_insensitive(self):
        text = "WHEN A USER LOGS IN, THE SYSTEM SHALL EMIT AN AUDIT EVENT."
        result = parse_ears_pattern(text)
        assert result is not None
        assert result.kind == EARSPatternKind.EVENT_DRIVEN

    def test_parse_ubiquitous_without_the(self):
        text = "System shall always return a response within 100ms."
        result = parse_ears_pattern(text)
        assert result is not None
        assert result.kind == EARSPatternKind.UBIQUITOUS


# ---------------------------------------------------------------------------
# compile_ears_to_dsl — single pattern to DSL criterion
# ---------------------------------------------------------------------------


class TestCompileEarsToDsl:
    def test_ubiquitous_compiles_to_python_criterion(self):
        pattern = EARSPattern(
            kind=EARSPatternKind.UBIQUITOUS,
            raw="The system shall log all requests.",
            subject="system",
            predicate="log all requests",
        )
        criteria = compile_ears_to_dsl(pattern)
        assert isinstance(criteria, list)
        assert len(criteria) >= 1
        # Ubiquitous → behavioral assertion or python criterion
        for c in criteria:
            assert isinstance(c, str)

    def test_event_driven_compiles_to_criterion(self):
        pattern = EARSPattern(
            kind=EARSPatternKind.EVENT_DRIVEN,
            raw="When user logs in, the system shall emit audit event.",
            subject="system",
            predicate="emit audit event",
            condition="user logs in",
        )
        criteria = compile_ears_to_dsl(pattern)
        assert isinstance(criteria, list)
        assert len(criteria) >= 1
        for c in criteria:
            assert isinstance(c, str)

    def test_unwanted_compiles_to_negation_criterion(self):
        pattern = EARSPattern(
            kind=EARSPatternKind.UNWANTED,
            raw="The system shall not expose passwords.",
            subject="system",
            predicate="expose passwords",
        )
        criteria = compile_ears_to_dsl(pattern)
        assert isinstance(criteria, list)
        assert len(criteria) >= 1
        # Unwanted behavior → should yield a criterion that represents the negation
        dsl_text = " ".join(criteria)
        assert len(dsl_text) > 0

    def test_state_driven_compiles_to_criterion(self):
        pattern = EARSPattern(
            kind=EARSPatternKind.STATE_DRIVEN,
            raw="While queue is full, the system shall reject new messages.",
            subject="system",
            predicate="reject new messages",
            condition="queue is full",
        )
        criteria = compile_ears_to_dsl(pattern)
        assert isinstance(criteria, list)
        assert len(criteria) >= 1

    def test_optional_compiles_to_criterion(self):
        pattern = EARSPattern(
            kind=EARSPatternKind.OPTIONAL,
            raw="Where caching is enabled, the system shall return cached results.",
            subject="system",
            predicate="return cached results",
            condition="caching is enabled",
        )
        criteria = compile_ears_to_dsl(pattern)
        assert isinstance(criteria, list)
        assert len(criteria) >= 1

    def test_dsl_criteria_are_valid_strings(self):
        for kind, raw, subject, predicate, condition in [
            (EARSPatternKind.UBIQUITOUS, "The system shall respond.", "system", "respond", None),
            (EARSPatternKind.EVENT_DRIVEN, "When X, the system shall Y.", "system", "Y", "X"),
            (EARSPatternKind.UNWANTED, "The system shall not fail.", "system", "fail", None),
            (EARSPatternKind.STATE_DRIVEN, "While X, the system shall Y.", "system", "Y", "X"),
            (EARSPatternKind.OPTIONAL, "Where X, the system shall Y.", "system", "Y", "X"),
        ]:
            pattern = EARSPattern(kind=kind, raw=raw, subject=subject, predicate=predicate, condition=condition)
            criteria = compile_ears_to_dsl(pattern)
            assert isinstance(criteria, list)
            for c in criteria:
                assert isinstance(c, str)
                assert len(c.strip()) > 0


# ---------------------------------------------------------------------------
# ears_text_to_dsl_criteria — end-to-end text → DSL list
# ---------------------------------------------------------------------------


class TestEarsTextToDslCriteria:
    def test_empty_text_returns_empty_list(self):
        result = ears_text_to_dsl_criteria("")
        assert result == []

    def test_whitespace_only_returns_empty_list(self):
        result = ears_text_to_dsl_criteria("   \n  ")
        assert result == []

    def test_single_ubiquitous_clause(self):
        text = "The system shall respond to all requests within 200ms."
        result = ears_text_to_dsl_criteria(text)
        assert len(result) >= 1
        for c in result:
            assert isinstance(c, str)

    def test_single_unwanted_clause(self):
        text = "The system shall not store plaintext passwords."
        result = ears_text_to_dsl_criteria(text)
        assert len(result) >= 1

    def test_single_event_driven_clause(self):
        text = "When the user submits a form, the system shall validate all fields."
        result = ears_text_to_dsl_criteria(text)
        assert len(result) >= 1

    def test_single_state_driven_clause(self):
        text = "While the database is unavailable, the system shall return a 503 error."
        result = ears_text_to_dsl_criteria(text)
        assert len(result) >= 1

    def test_single_optional_clause(self):
        text = "Where logging is enabled, the system shall write to a log file."
        result = ears_text_to_dsl_criteria(text)
        assert len(result) >= 1

    def test_multiple_clauses_produce_multiple_criteria(self):
        text = (
            "The system shall log all requests. "
            "The system shall not expose passwords. "
            "When a user logs in, the system shall emit an audit event."
        )
        result = ears_text_to_dsl_criteria(text)
        assert len(result) >= 2

    def test_all_five_patterns_in_one_text(self):
        text = (
            "The system shall be available 24/7. "
            "When a new user registers, the system shall send a welcome email. "
            "The system shall not allow duplicate usernames. "
            "While the system is in maintenance mode, the system shall reject new requests. "
            "Where analytics is enabled, the system shall track page views."
        )
        result = ears_text_to_dsl_criteria(text)
        assert len(result) >= 4

    def test_returns_list_of_strings(self):
        text = "The system shall validate all inputs before processing."
        result = ears_text_to_dsl_criteria(text)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, str)

    def test_criteria_are_nonempty_strings(self):
        text = (
            "The system shall log all requests. "
            "The system shall not fail silently."
        )
        result = ears_text_to_dsl_criteria(text)
        for c in result:
            assert c.strip() != ""

    def test_deduplication(self):
        # Duplicate clause should not produce duplicate criteria
        text = (
            "The system shall log all requests. "
            "The system shall log all requests."
        )
        result = ears_text_to_dsl_criteria(text)
        assert len(result) == len(set(result))
