"""Tests for the RCCL busbw/algbw perf-uplift gate.

Feature 1ce12ad4-3312-43a9-9720-1791c3f2aa0b
"""

from __future__ import annotations

import pytest

from bob.rccl_perf_gate import (
    MIN_REPS,
    PerfGateResult,
    PerfRow,
    SizeStats,
    compute_size_stats,
    evaluate_perf_uplift_gate,
    parse_busbw_algbw_table,
)


# A realistic rccl-tests all_reduce table fragment.
SAMPLE_TABLE = """\
#
# out-of-place                       in-place
#       size         count      type   redop    root     time   algbw   busbw #wrong     time   algbw   busbw #wrong
#        (B)    (elements)                                (us)  (GB/s)  (GB/s)            (us)  (GB/s)  (GB/s)
      1048576        262144     float     sum      -1    25.10   41.77   78.32      0    24.90   42.11   78.95      0
      4194304       1048576     float     sum      -1    68.20   61.50  115.31      0    67.10   62.51  117.20      0
"""


def _reps(size_to_busbw_first, n=MIN_REPS, jitter=0.0):
    """Build n {size: busbw} reps, adding a tiny deterministic jitter."""
    reps = []
    for i in range(n):
        rep = {}
        for size, base in size_to_busbw_first.items():
            rep[size] = base + (jitter if i % 2 else -jitter)
        reps.append(rep)
    return reps


def test_parse_extracts_both_oop_and_inplace():
    rows = parse_busbw_algbw_table(SAMPLE_TABLE)
    assert len(rows) == 2
    r0 = rows[0]
    assert isinstance(r0, PerfRow)
    assert r0.size == 1048576
    assert r0.count == 262144
    assert r0.dtype == "float"
    assert r0.redop == "sum"
    assert r0.root == -1
    assert r0.oop_busbw == pytest.approx(78.32)
    assert r0.ip_busbw == pytest.approx(78.95)
    assert rows[1].size == 4194304
    assert rows[1].oop_busbw == pytest.approx(115.31)


def test_parse_skips_comments_and_blanks():
    text = "# header\n\n# another\n"
    assert parse_busbw_algbw_table(text) == []


def test_compute_size_stats_median_and_noise_band():
    stats = compute_size_stats(1024, [100.0, 102.0, 98.0, 101.0, 99.0])
    assert isinstance(stats, SizeStats)
    assert stats.median == pytest.approx(100.0)
    assert stats.n == 5
    assert stats.noise_half_band >= 0.0
    assert stats.ci_low <= stats.median <= stats.ci_high


def test_gate_passes_on_clear_uplift():
    old = _reps({1048576: 78.0}, jitter=0.1)
    new = _reps({1048576: 120.0}, jitter=0.1)
    result = evaluate_perf_uplift_gate(old, new)
    assert isinstance(result, PerfGateResult)
    assert result.passed is True
    assert len(result.per_size) == 1
    assert result.per_size[0].is_win is True


def test_gate_fails_when_new_within_noise():
    # New is essentially identical to old — no uplift beyond noise.
    old = _reps({1048576: 78.0}, jitter=2.0)
    new = _reps({1048576: 78.3}, jitter=2.0)
    result = evaluate_perf_uplift_gate(old, new)
    assert result.passed is False


def test_gate_fails_when_new_slower():
    old = _reps({1048576: 120.0}, jitter=0.1)
    new = _reps({1048576: 78.0}, jitter=0.1)
    result = evaluate_perf_uplift_gate(old, new)
    assert result.passed is False
    assert result.per_size[0].new_beats_old is False


def test_gate_rejects_non_self_measured_baseline():
    old = _reps({1048576: 78.0})
    new = _reps({1048576: 120.0})
    result = evaluate_perf_uplift_gate(old, new, baseline_is_self_measured=False)
    assert result.passed is False
    assert "self-measured" in result.reason


def test_gate_rejects_size_range_change():
    old = _reps({1048576: 78.0, 4194304: 115.0})
    new = _reps({1048576: 120.0})  # dropped a size — cheat guard
    result = evaluate_perf_uplift_gate(old, new)
    assert result.passed is False
    assert "size range changed" in result.reason


def test_gate_rejects_too_few_reps():
    old = _reps({1048576: 78.0}, n=3)
    new = _reps({1048576: 120.0}, n=3)
    result = evaluate_perf_uplift_gate(old, new)
    assert result.passed is False
    assert "too few reps" in result.reason


def test_gate_accepts_raw_table_string_reps():
    old = [SAMPLE_TABLE] * MIN_REPS
    faster = SAMPLE_TABLE.replace("78.32", "150.0").replace("115.31", "200.0")
    new = [faster] * MIN_REPS
    result = evaluate_perf_uplift_gate(old, new)
    assert result.passed is True


def test_threshold_requires_larger_margin():
    old = _reps({1048576: 100.0}, jitter=0.01)
    new = _reps({1048576: 101.0}, jitter=0.01)
    # 1% uplift; require 5% threshold => fails.
    result = evaluate_perf_uplift_gate(old, new, threshold=0.05)
    assert result.passed is False


def test_integration_regression_detector_importable():
    import bob.regression_detector  # noqa: F401
