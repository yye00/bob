"""Tests for src/bob/differential_testing_harness.py (feature 02ea5520).

Verifies the differential testing harness:
- Compares AI implementation vs. reference implementation on fuzzed inputs.
- Uses hypothesis-generated inputs for fuzzing.
- Reports divergences as reward-hacking findings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from bob.differential_testing_harness import (
    DifferentialFinding,
    DifferentialResult,
    DivergenceKind,
    compare_outputs,
    run_differential_test,
    summarize_findings,
)


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestDifferentialFinding:
    def test_constructible(self):
        finding = DifferentialFinding(
            input_args=(1, 2),
            input_kwargs={},
            ai_output=3,
            ref_output=5,
            kind=DivergenceKind.VALUE_MISMATCH,
            detail="outputs differ: 3 != 5",
        )
        assert finding.input_args == (1, 2)
        assert finding.ai_output == 3
        assert finding.ref_output == 5
        assert finding.kind == DivergenceKind.VALUE_MISMATCH
        assert "differ" in finding.detail

    def test_exception_kind(self):
        finding = DifferentialFinding(
            input_args=(-1,),
            input_kwargs={},
            ai_output=None,
            ref_output=1,
            kind=DivergenceKind.EXCEPTION_VS_RESULT,
            detail="AI raised ValueError, ref returned 1",
        )
        assert finding.kind == DivergenceKind.EXCEPTION_VS_RESULT


class TestDifferentialResult:
    def test_clean_result(self):
        result = DifferentialResult(
            is_flagged=False,
            findings=[],
            total_inputs_tested=100,
            summary="All 100 inputs matched.",
        )
        assert result.is_flagged is False
        assert result.findings == []
        assert result.total_inputs_tested == 100
        assert "100" in result.summary

    def test_flagged_result(self):
        finding = DifferentialFinding(
            input_args=(0,),
            input_kwargs={},
            ai_output=None,
            ref_output=0,
            kind=DivergenceKind.VALUE_MISMATCH,
            detail="outputs differ",
        )
        result = DifferentialResult(
            is_flagged=True,
            findings=[finding],
            total_inputs_tested=50,
            summary="1 divergence found in 50 inputs.",
        )
        assert result.is_flagged is True
        assert len(result.findings) == 1


class TestDivergenceKind:
    def test_all_kinds_accessible(self):
        assert DivergenceKind.VALUE_MISMATCH
        assert DivergenceKind.EXCEPTION_VS_RESULT
        assert DivergenceKind.RESULT_VS_EXCEPTION
        assert DivergenceKind.EXCEPTION_TYPE_MISMATCH


# ---------------------------------------------------------------------------
# compare_outputs tests
# ---------------------------------------------------------------------------


class TestCompareOutputs:
    def test_identical_outputs_no_divergence(self):
        finding = compare_outputs(
            input_args=(1, 2),
            input_kwargs={},
            ai_output=3,
            ref_output=3,
            ai_exc=None,
            ref_exc=None,
        )
        assert finding is None

    def test_value_mismatch_detected(self):
        finding = compare_outputs(
            input_args=(1, 2),
            input_kwargs={},
            ai_output=3,
            ref_output=5,
            ai_exc=None,
            ref_exc=None,
        )
        assert finding is not None
        assert finding.kind == DivergenceKind.VALUE_MISMATCH

    def test_ai_exception_vs_ref_result(self):
        finding = compare_outputs(
            input_args=(0,),
            input_kwargs={},
            ai_output=None,
            ref_output=42,
            ai_exc=ZeroDivisionError("division by zero"),
            ref_exc=None,
        )
        assert finding is not None
        assert finding.kind == DivergenceKind.EXCEPTION_VS_RESULT

    def test_ref_exception_vs_ai_result(self):
        finding = compare_outputs(
            input_args=(0,),
            input_kwargs={},
            ai_output=42,
            ref_output=None,
            ai_exc=None,
            ref_exc=ZeroDivisionError("division by zero"),
        )
        assert finding is not None
        assert finding.kind == DivergenceKind.RESULT_VS_EXCEPTION

    def test_same_exception_no_divergence(self):
        finding = compare_outputs(
            input_args=(0,),
            input_kwargs={},
            ai_output=None,
            ref_output=None,
            ai_exc=ZeroDivisionError("division by zero"),
            ref_exc=ZeroDivisionError("division by zero"),
        )
        assert finding is None

    def test_different_exception_types(self):
        finding = compare_outputs(
            input_args=(-1,),
            input_kwargs={},
            ai_output=None,
            ref_output=None,
            ai_exc=ValueError("bad"),
            ref_exc=TypeError("wrong type"),
        )
        assert finding is not None
        assert finding.kind == DivergenceKind.EXCEPTION_TYPE_MISMATCH

    def test_float_outputs_approximately_equal(self):
        finding = compare_outputs(
            input_args=(1.0,),
            input_kwargs={},
            ai_output=1.0000000001,
            ref_output=1.0,
            ai_exc=None,
            ref_exc=None,
        )
        assert finding is None

    def test_float_outputs_significantly_different(self):
        finding = compare_outputs(
            input_args=(1.0,),
            input_kwargs={},
            ai_output=2.0,
            ref_output=1.0,
            ai_exc=None,
            ref_exc=None,
        )
        assert finding is not None
        assert finding.kind == DivergenceKind.VALUE_MISMATCH

    def test_none_vs_value_is_divergence(self):
        finding = compare_outputs(
            input_args=(),
            input_kwargs={},
            ai_output=None,
            ref_output=42,
            ai_exc=None,
            ref_exc=None,
        )
        assert finding is not None

    def test_both_none_no_divergence(self):
        finding = compare_outputs(
            input_args=(),
            input_kwargs={},
            ai_output=None,
            ref_output=None,
            ai_exc=None,
            ref_exc=None,
        )
        assert finding is None


# ---------------------------------------------------------------------------
# run_differential_test tests
# ---------------------------------------------------------------------------


class TestRunDifferentialTest:
    def test_identical_implementations_no_findings(self):
        def ref(x: int) -> int:
            return x * 2

        def ai(x: int) -> int:
            return x * 2

        inputs = [(i,) for i in range(10)]
        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=inputs,
        )
        assert isinstance(result, DifferentialResult)
        assert result.is_flagged is False
        assert result.total_inputs_tested == 10

    def test_buggy_ai_flagged(self):
        def ref(x: int) -> int:
            return x * x

        def ai(x: int) -> int:
            return x * 2  # wrong for x > 2

        inputs = [(i,) for i in range(10)]
        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=inputs,
        )
        assert result.is_flagged is True
        assert len(result.findings) > 0

    def test_ai_spec_gaming_detected(self):
        """AI only handles test inputs 0 and 1 correctly."""
        def ref(x: int) -> int:
            return x + 10

        def ai(x: int) -> int:
            if x == 0:
                return 10
            elif x == 1:
                return 11
            else:
                return x  # wrong for x > 1

        inputs = [(i,) for i in range(5)]
        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=inputs,
        )
        assert result.is_flagged is True

    def test_exception_vs_normal_is_finding(self):
        def ref(x: int) -> int:
            if x < 0:
                raise ValueError("negative")
            return x

        def ai(x: int) -> int:
            return abs(x)  # swallows the exception

        inputs = [(-1,), (-5,)]
        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=inputs,
        )
        assert result.is_flagged is True

    def test_returns_result_with_total_count(self):
        def ref(x: int) -> int:
            return x

        def ai(x: int) -> int:
            return x

        inputs = [(i,) for i in range(25)]
        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=inputs,
        )
        assert result.total_inputs_tested == 25

    def test_empty_inputs_returns_clean(self):
        def ref(x: int) -> int:
            return x

        def ai(x: int) -> int:
            return x

        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=[],
        )
        assert result.is_flagged is False
        assert result.total_inputs_tested == 0

    def test_kwargs_forwarded_correctly(self):
        def ref(x: int, *, multiplier: int = 1) -> int:
            return x * multiplier

        def ai(x: int, *, multiplier: int = 1) -> int:
            return x * multiplier

        inputs_with_kwargs = [
            {"args": (2,), "kwargs": {"multiplier": 3}},
            {"args": (5,), "kwargs": {"multiplier": 2}},
        ]
        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=inputs_with_kwargs,
        )
        assert result.is_flagged is False

    def test_max_findings_limits_output(self):
        def ref(x: int) -> int:
            return x * x

        def ai(x: int) -> int:
            return x  # always wrong for x != 0 and x != 1

        inputs = [(i,) for i in range(2, 50)]
        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=inputs,
            max_findings=5,
        )
        assert len(result.findings) <= 5

    def test_finding_contains_input_info(self):
        def ref(x: int) -> int:
            return x + 100

        def ai(x: int) -> int:
            return x  # wrong

        inputs = [(42,)]
        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=inputs,
        )
        assert result.is_flagged is True
        finding = result.findings[0]
        assert finding.input_args == (42,)
        assert finding.ref_output == 142
        assert finding.ai_output == 42


# ---------------------------------------------------------------------------
# Hypothesis-based fuzz tests
# ---------------------------------------------------------------------------


class TestWithHypothesis:
    @given(st.integers())
    def test_identical_integer_functions_never_diverge(self, x: int):
        def ref(n: int) -> int:
            return n * 2

        def ai(n: int) -> int:
            return n * 2

        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=[(x,)],
        )
        assert result.is_flagged is False

    @given(st.lists(st.integers(), min_size=0, max_size=20))
    def test_identical_list_functions_never_diverge(self, lst: list[int]):
        def ref(items: list) -> list:
            return sorted(items)

        def ai(items: list) -> list:
            return sorted(items)

        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=[(lst,)],
        )
        assert result.is_flagged is False

    @given(st.integers(min_value=1, max_value=100))
    def test_wrong_implementation_detected(self, x: int):
        """An AI that always returns 0 should be caught on nonzero inputs."""
        def ref(n: int) -> int:
            return n

        def ai(n: int) -> int:
            return 0  # always wrong for nonzero

        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=[(x,)],
        )
        if x != 0:
            assert result.is_flagged is True

    @given(st.text(min_size=0, max_size=50))
    @settings(max_examples=50)
    def test_string_functions_compared(self, s: str):
        def ref(text: str) -> str:
            return text.strip().lower()

        def ai(text: str) -> str:
            return text.strip().lower()

        result = run_differential_test(
            ai_impl=ai,
            ref_impl=ref,
            input_sequences=[(s,)],
        )
        assert result.is_flagged is False


# ---------------------------------------------------------------------------
# summarize_findings tests
# ---------------------------------------------------------------------------


class TestSummarizeFindings:
    def test_empty_findings_summary(self):
        summary = summarize_findings([], total_tested=100)
        assert isinstance(summary, str)
        assert "100" in summary
        assert len(summary) > 0

    def test_divergences_mentioned_in_summary(self):
        finding = DifferentialFinding(
            input_args=(1,),
            input_kwargs={},
            ai_output=2,
            ref_output=3,
            kind=DivergenceKind.VALUE_MISMATCH,
            detail="outputs differ",
        )
        summary = summarize_findings([finding], total_tested=10)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_summary_mentions_count(self):
        findings = [
            DifferentialFinding(
                input_args=(i,),
                input_kwargs={},
                ai_output=i,
                ref_output=i + 1,
                kind=DivergenceKind.VALUE_MISMATCH,
                detail=f"differ at {i}",
            )
            for i in range(3)
        ]
        summary = summarize_findings(findings, total_tested=20)
        assert "3" in summary or "divergen" in summary.lower()
