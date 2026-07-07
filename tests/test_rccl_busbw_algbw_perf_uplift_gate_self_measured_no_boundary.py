"""Boundary tests: empty / zero / minimum input returns a well-defined result.

Feature 1ce12ad4-3312-43a9-9720-1791c3f2aa0b
"""

from __future__ import annotations

from bob.rccl_perf_gate import (
    PerfGateResult,
    evaluate_perf_uplift_gate,
    parse_busbw_algbw_table,
)


def test_parse_empty_string_returns_empty_list():
    assert parse_busbw_algbw_table("") == []


def test_parse_only_comments_returns_empty_list():
    assert parse_busbw_algbw_table("# just a header\n#\n") == []


def test_gate_empty_reps_returns_result_not_raise():
    result = evaluate_perf_uplift_gate([], [])
    assert isinstance(result, PerfGateResult)
    assert result.passed is False
    assert "empty" in result.reason


def test_gate_empty_baseline_only():
    result = evaluate_perf_uplift_gate([], [{1024: 100.0}])
    assert isinstance(result, PerfGateResult)
    assert result.passed is False


def test_gate_single_rep_is_below_minimum():
    result = evaluate_perf_uplift_gate([{1024: 100.0}], [{1024: 200.0}])
    assert isinstance(result, PerfGateResult)
    assert result.passed is False
    assert "too few reps" in result.reason


def test_gate_result_shape_is_consistent():
    result = evaluate_perf_uplift_gate([], [])
    assert hasattr(result, "passed")
    assert hasattr(result, "reason")
    assert result.per_size == ()
    assert isinstance(result.warnings, tuple)
