"""Error-path tests: invalid input raises ValueError, no silent success.

Feature 1ce12ad4-3312-43a9-9720-1791c3f2aa0b
"""

from __future__ import annotations

import pytest

from bob.rccl_perf_gate import (
    compute_size_stats,
    evaluate_perf_uplift_gate,
    parse_busbw_algbw_table,
)


def test_parse_non_string_raises():
    with pytest.raises(ValueError):
        parse_busbw_algbw_table(12345)  # type: ignore[arg-type]


def test_parse_too_few_columns_raises():
    with pytest.raises(ValueError):
        parse_busbw_algbw_table("1048576 262144 float sum -1\n")


def test_parse_non_numeric_size_raises():
    bad = "notanumber 262144 float sum -1 25.1 41.7 78.3 0 24.9 42.1 78.9 0\n"
    with pytest.raises(ValueError):
        parse_busbw_algbw_table(bad)


def test_gate_negative_threshold_raises():
    with pytest.raises(ValueError):
        evaluate_perf_uplift_gate([{1: 1.0}], [{1: 1.0}], threshold=-0.1)


def test_gate_zero_min_reps_raises():
    with pytest.raises(ValueError):
        evaluate_perf_uplift_gate([{1: 1.0}], [{1: 1.0}], min_reps=0)


def test_gate_none_reps_raises():
    with pytest.raises(ValueError):
        evaluate_perf_uplift_gate(None, [{1: 1.0}])  # type: ignore[arg-type]


def test_gate_string_reps_raises():
    # A raw table string passed where a *sequence of reps* is expected.
    with pytest.raises(ValueError):
        evaluate_perf_uplift_gate("1 2 3", [{1: 1.0}])


def test_gate_bad_rep_row_type_raises():
    reps = [["not-a-perfrow"]] * 10
    with pytest.raises(ValueError):
        evaluate_perf_uplift_gate(reps, reps)


def test_compute_size_stats_empty_raises():
    with pytest.raises(ValueError):
        compute_size_stats(1024, [])
