"""Tests that compute_backoff_seconds caps at 3600 seconds."""

from __future__ import annotations

import pytest

from bob3.orchestrator.reap_backoff import compute_backoff_seconds


class TestBackoffCapAt3600:
    def test_cap_reached_at_6_reaps(self):
        # 2^6 * 60 = 3840 → capped to 3600
        assert compute_backoff_seconds(6) == 3600

    def test_cap_reached_at_5_reaps_uncapped(self):
        # 2^5 * 60 = 1920 → not yet capped
        assert compute_backoff_seconds(5) == 1920

    def test_high_reap_count_still_3600(self):
        assert compute_backoff_seconds(10) == 3600
        assert compute_backoff_seconds(20) == 3600
        assert compute_backoff_seconds(100) == 3600

    def test_never_exceeds_3600(self):
        for n in range(0, 15):
            assert compute_backoff_seconds(n) <= 3600

    def test_cap_value_is_exactly_3600(self):
        # Verify the cap is not 3599 or 3601
        capped_values = [compute_backoff_seconds(n) for n in range(6, 10)]
        for v in capped_values:
            assert v == 3600

    def test_transition_point_at_reap_count_6(self):
        # Uncapped value at 6 would be 3840, but should be 3600
        uncapped = (2 ** 6) * 60
        assert uncapped > 3600
        assert compute_backoff_seconds(6) == 3600

    def test_compute_backoff_is_monotonically_non_decreasing(self):
        values = [compute_backoff_seconds(n) for n in range(0, 10)]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1], (
                f"Backoff not non-decreasing: {values[i-1]} → {values[i]} at index {i}"
            )
