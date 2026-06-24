"""Tests for exponential growth of reap_backoff.compute_backoff_seconds."""

from __future__ import annotations

import pytest

from bob.orchestrator.reap_backoff import compute_backoff_seconds


class TestComputeBackoffSecondsExponentialGrowth:
    def test_zero_reaps_returns_60(self):
        assert compute_backoff_seconds(0) == 60

    def test_one_reap_returns_120(self):
        assert compute_backoff_seconds(1) == 120

    def test_two_reaps_returns_240(self):
        assert compute_backoff_seconds(2) == 240

    def test_three_reaps_returns_480(self):
        assert compute_backoff_seconds(3) == 480

    def test_four_reaps_returns_960(self):
        assert compute_backoff_seconds(4) == 960

    def test_five_reaps_returns_1920(self):
        assert compute_backoff_seconds(5) == 1920

    def test_each_additional_reap_doubles_backoff(self):
        prev = compute_backoff_seconds(0)
        for n in range(1, 6):
            cur = compute_backoff_seconds(n)
            if cur < 3600:
                assert cur == prev * 2, f"reap_count={n}: expected {prev * 2}, got {cur}"
            prev = cur

    def test_negative_reap_count_treated_as_zero(self):
        assert compute_backoff_seconds(-1) == compute_backoff_seconds(0)
        assert compute_backoff_seconds(-5) == compute_backoff_seconds(0)
