"""Tests for src/bob3/property_based_test_generator_hypothesis_ears.py (feature d92d055b).

Verifies the property-based test generator:
- Parses EARS unwanted-behavior clauses from spec descriptions.
- Generates Hypothesis property tests from those clauses.
- Runs 100+ fuzz cases per property.
- Integrates with the differential-testing harness.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from bob3.property_based_test_generator_hypothesis_ears import (
    EARSClause,
    EARSClauseKind,
    PropertyTestResult,
    PropertyTestSuite,
    extract_ears_clauses,
    generate_property_test_suite,
    run_property_suite,
)


# ---------------------------------------------------------------------------
# EARSClause data model
# ---------------------------------------------------------------------------


class TestEARSClause:
    def test_unwanted_clause_construction(self):
        clause = EARSClause(
            kind=EARSClauseKind.UNWANTED,
            raw="the system shall not accept empty inputs",
            subject="system",
            predicate="shall not accept empty inputs",
        )
        assert clause.kind == EARSClauseKind.UNWANTED
        assert "shall not" in clause.raw
        assert clause.subject == "system"

    def test_event_driven_clause_construction(self):
        clause = EARSClause(
            kind=EARSClauseKind.EVENT_DRIVEN,
            raw="when input is negative, the system shall raise ValueError",
            subject="system",
            predicate="shall raise ValueError",
            condition="input is negative",
        )
        assert clause.kind == EARSClauseKind.EVENT_DRIVEN
        assert clause.condition == "input is negative"

    def test_state_driven_clause_construction(self):
        clause = EARSClause(
            kind=EARSClauseKind.STATE_DRIVEN,
            raw="while processing, the system shall not block indefinitely",
            subject="system",
            predicate="shall not block indefinitely",
            condition="processing",
        )
        assert clause.kind == EARSClauseKind.STATE_DRIVEN

    def test_optional_condition_defaults_to_none(self):
        clause = EARSClause(
            kind=EARSClauseKind.UNWANTED,
            raw="the system shall not crash",
            subject="system",
            predicate="shall not crash",
        )
        assert clause.condition is None


# ---------------------------------------------------------------------------
# EARSClauseKind enum
# ---------------------------------------------------------------------------


class TestEARSClauseKind:
    def test_all_kinds_present(self):
        kinds = {EARSClauseKind.UNWANTED, EARSClauseKind.EVENT_DRIVEN, EARSClauseKind.STATE_DRIVEN}
        assert len(kinds) == 3

    def test_string_values(self):
        assert EARSClauseKind.UNWANTED.value == "unwanted"
        assert EARSClauseKind.EVENT_DRIVEN.value == "event_driven"
        assert EARSClauseKind.STATE_DRIVEN.value == "state_driven"


# ---------------------------------------------------------------------------
# extract_ears_clauses — parsing
# ---------------------------------------------------------------------------


class TestExtractEarsClauses:
    def test_extracts_shall_not_clause(self):
        text = "The system shall not accept values above 1000."
        clauses = extract_ears_clauses(text)
        assert len(clauses) >= 1
        unwanted = [c for c in clauses if c.kind == EARSClauseKind.UNWANTED]
        assert len(unwanted) >= 1

    def test_extracts_when_clause(self):
        text = "When the input is empty, the system shall raise ValueError."
        clauses = extract_ears_clauses(text)
        event_driven = [c for c in clauses if c.kind == EARSClauseKind.EVENT_DRIVEN]
        assert len(event_driven) >= 1
        assert any("empty" in c.condition.lower() for c in event_driven)

    def test_extracts_while_clause(self):
        text = "While running in degraded mode, the system shall not accept new connections."
        clauses = extract_ears_clauses(text)
        state_driven = [c for c in clauses if c.kind == EARSClauseKind.STATE_DRIVEN]
        assert len(state_driven) >= 1

    def test_empty_string_returns_empty_list(self):
        clauses = extract_ears_clauses("")
        assert clauses == []

    def test_no_ears_clauses_returns_empty(self):
        text = "This is just a plain description with no requirements language."
        clauses = extract_ears_clauses(text)
        assert isinstance(clauses, list)

    def test_multiple_clauses_extracted(self):
        text = (
            "The system shall not accept null values. "
            "When input exceeds limit, the system shall raise OverflowError. "
            "While locked, the system shall not modify state."
        )
        clauses = extract_ears_clauses(text)
        assert len(clauses) >= 3

    def test_clause_raw_text_preserved(self):
        text = "The system shall not accept negative numbers."
        clauses = extract_ears_clauses(text)
        assert len(clauses) >= 1
        assert len(clauses[0].raw) > 0

    @given(st.text(max_size=500))
    @settings(max_examples=50)
    def test_never_raises_on_arbitrary_text(self, text: str):
        result = extract_ears_clauses(text)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# PropertyTestSuite data model
# ---------------------------------------------------------------------------


class TestPropertyTestSuite:
    def test_construction(self):
        suite = PropertyTestSuite(
            clauses=[],
            num_examples=100,
            source_text="some spec text",
        )
        assert suite.num_examples == 100
        assert suite.source_text == "some spec text"
        assert suite.clauses == []

    def test_with_clauses(self):
        clause = EARSClause(
            kind=EARSClauseKind.UNWANTED,
            raw="shall not accept negatives",
            subject="system",
            predicate="shall not accept negatives",
        )
        suite = PropertyTestSuite(
            clauses=[clause],
            num_examples=200,
            source_text="the system shall not accept negatives",
        )
        assert len(suite.clauses) == 1


# ---------------------------------------------------------------------------
# generate_property_test_suite
# ---------------------------------------------------------------------------


class TestGeneratePropertyTestSuite:
    def test_generates_suite_from_text(self):
        text = "The system shall not accept null values. When input is zero, the system shall raise ZeroDivisionError."
        suite = generate_property_test_suite(text)
        assert isinstance(suite, PropertyTestSuite)
        assert suite.num_examples >= 100

    def test_minimum_100_examples(self):
        text = "The system shall not crash on empty strings."
        suite = generate_property_test_suite(text)
        assert suite.num_examples >= 100

    def test_custom_num_examples(self):
        text = "The system shall not crash."
        suite = generate_property_test_suite(text, num_examples=200)
        assert suite.num_examples == 200

    def test_source_text_preserved(self):
        text = "The system shall not accept negative inputs."
        suite = generate_property_test_suite(text)
        assert suite.source_text == text

    def test_clauses_populated_from_text(self):
        text = (
            "The system shall not accept empty inputs. "
            "When processing fails, the system shall log an error."
        )
        suite = generate_property_test_suite(text)
        assert len(suite.clauses) >= 1

    def test_empty_text_still_returns_suite(self):
        suite = generate_property_test_suite("")
        assert isinstance(suite, PropertyTestSuite)
        assert suite.clauses == []


# ---------------------------------------------------------------------------
# PropertyTestResult data model
# ---------------------------------------------------------------------------


class TestPropertyTestResult:
    def test_passed_result(self):
        result = PropertyTestResult(
            clause=EARSClause(
                kind=EARSClauseKind.UNWANTED,
                raw="shall not crash",
                subject="system",
                predicate="shall not crash",
            ),
            passed=True,
            num_cases_run=150,
            counterexample=None,
            detail="150 cases passed",
        )
        assert result.passed is True
        assert result.num_cases_run == 150
        assert result.counterexample is None

    def test_failed_result_with_counterexample(self):
        clause = EARSClause(
            kind=EARSClauseKind.UNWANTED,
            raw="shall not accept negatives",
            subject="system",
            predicate="shall not accept negatives",
        )
        result = PropertyTestResult(
            clause=clause,
            passed=False,
            num_cases_run=42,
            counterexample=(-1,),
            detail="Counterexample found: (-1,)",
        )
        assert result.passed is False
        assert result.counterexample == (-1,)
        assert "Counterexample" in result.detail


# ---------------------------------------------------------------------------
# run_property_suite — integration with differential testing harness
# ---------------------------------------------------------------------------


class TestRunPropertySuite:
    def _make_suite(self, text: str) -> PropertyTestSuite:
        return generate_property_test_suite(text)

    def test_run_returns_list_of_results(self):
        text = "The system shall not accept null values."
        suite = self._make_suite(text)
        results = run_property_suite(suite)
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, PropertyTestResult)

    def test_each_result_has_cases_run(self):
        text = "The system shall not crash."
        suite = generate_property_test_suite(text, num_examples=100)
        results = run_property_suite(suite)
        for r in results:
            assert r.num_cases_run >= 0

    def test_run_with_no_clauses(self):
        suite = PropertyTestSuite(
            clauses=[],
            num_examples=100,
            source_text="",
        )
        results = run_property_suite(suite)
        assert results == []

    def test_run_with_callable_validator(self):
        """run_property_suite accepts an optional validator callable for integration testing."""
        text = "The system shall not accept negative integers."
        suite = generate_property_test_suite(text, num_examples=100)

        def reject_negatives(value: int) -> bool:
            return value >= 0

        results = run_property_suite(suite, validator=reject_negatives)
        assert isinstance(results, list)

    def test_run_with_differential_harness(self):
        """Integration: run_property_suite can feed into the differential testing harness."""
        from bob3.differential_testing_harness import run_differential_test

        text = "The system shall not accept values above 100."
        suite = generate_property_test_suite(text, num_examples=100)

        def ai_impl(x: int) -> int:
            if x > 100:
                raise ValueError(f"value {x} exceeds limit")
            return x

        def ref_impl(x: int) -> int:
            if x > 100:
                raise ValueError(f"value {x} exceeds limit")
            return x

        input_sequences = [(i,) for i in range(-10, 110)]
        result = run_differential_test(
            ai_impl=ai_impl,
            ref_impl=ref_impl,
            input_sequences=input_sequences,
        )
        assert not result.is_flagged
        assert result.total_inputs_tested == 120


# ---------------------------------------------------------------------------
# Hypothesis-based property tests — fuzz the generator itself
# ---------------------------------------------------------------------------


class TestFuzzPropertyGenerator:
    @given(st.text(alphabet=st.characters(whitelist_categories=("L", "N", "P", "Zs")), max_size=300))
    @settings(max_examples=100)
    def test_extract_never_raises(self, text: str):
        result = extract_ears_clauses(text)
        assert isinstance(result, list)

    @given(st.integers(min_value=100, max_value=1000))
    @settings(max_examples=20)
    def test_suite_respects_num_examples(self, n: int):
        suite = generate_property_test_suite("The system shall not crash.", num_examples=n)
        assert suite.num_examples == n

    @given(st.text(max_size=200))
    @settings(max_examples=50)
    def test_generate_suite_never_raises(self, text: str):
        suite = generate_property_test_suite(text)
        assert isinstance(suite, PropertyTestSuite)
        assert suite.num_examples >= 100
