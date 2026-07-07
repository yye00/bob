"""Boundary tests for bob.skip_ratio_gate (4d296524).

Empty, zero, or minimum input must return a well-defined result rather than
raising. In particular a first run with no prior baseline must initialize the
ratio baseline cleanly (no false flag).
"""
from __future__ import annotations

from bob.skip_ratio_gate import (
    classify_skip_reason,
    compute_skip_ratio,
    emit_skip_ratio_bound,
    evaluate_skip_ratio,
)


def test_emit_empty_list_returns_empty():
    assert emit_skip_ratio_bound([], title="") == []


def test_compute_ratio_zero_collected_is_zero_not_division_error():
    """Zero collected tests must yield ratio 0.0, not ZeroDivisionError."""
    assert compute_skip_ratio(skipped=0, xfailed=0, total_collected=0) == 0.0


def test_first_run_no_baseline_initializes_clean():
    """A first run with no prior baseline must not raise a false flag."""
    result = evaluate_skip_ratio(
        skipped=5, xfailed=0, total_collected=100, baseline_ratio=None
    )
    assert result.flagged is False
    assert result.baseline_initialized is True


def test_classify_blank_reason_is_untagged_not_raise():
    assert classify_skip_reason("") == "UNTAGGED"


def test_compute_ratio_minimum_single_test():
    assert compute_skip_ratio(skipped=0, xfailed=0, total_collected=1) == 0.0
    assert compute_skip_ratio(skipped=1, xfailed=0, total_collected=1) == 1.0
