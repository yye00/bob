"""Error-path tests for bob.skip_ratio_gate (4d296524).

Invalid input must raise ValueError and the function must not silently succeed.
"""
from __future__ import annotations

import pytest

from bob.skip_ratio_gate import (
    classify_skip_reason,
    compute_skip_ratio,
    emit_skip_ratio_bound,
    evaluate_skip_ratio,
)


def test_emit_non_list_raises():
    with pytest.raises(ValueError):
        emit_skip_ratio_bound("not a list", title="x")


def test_emit_non_string_element_raises():
    with pytest.raises(ValueError):
        emit_skip_ratio_bound(["ok", 123], title="x")


def test_classify_non_string_raises():
    with pytest.raises(ValueError):
        classify_skip_reason(None)


def test_compute_ratio_negative_raises():
    with pytest.raises(ValueError):
        compute_skip_ratio(skipped=-1, xfailed=0, total_collected=10)


def test_compute_ratio_skips_exceed_total_raises():
    with pytest.raises(ValueError):
        compute_skip_ratio(skipped=8, xfailed=5, total_collected=10)


def test_evaluate_negative_baseline_raises():
    with pytest.raises(ValueError):
        evaluate_skip_ratio(
            skipped=1, xfailed=0, total_collected=10, baseline_ratio=-0.5
        )
