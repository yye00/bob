"""Tests: exponential_backoff_seconds caps at 1800 and grows correctly."""

from __future__ import annotations

import pytest

from bob.startup_crash_exempt import exponential_backoff_seconds


class TestExponentialBackoffSeconds:
    """exponential_backoff_seconds(n) = min(60 * 2^n, 1800)."""

    def test_first_attempt_sixty_seconds(self) -> None:
        """At exempt_counter=0, backoff must be exactly 60 seconds."""
        assert exponential_backoff_seconds(0) == 60

    def test_second_attempt_one_twenty(self) -> None:
        assert exponential_backoff_seconds(1) == 120

    def test_third_attempt_two_forty(self) -> None:
        assert exponential_backoff_seconds(2) == 240

    def test_fourth_attempt_four_eighty(self) -> None:
        assert exponential_backoff_seconds(3) == 480

    def test_fifth_attempt_nine_sixty(self) -> None:
        assert exponential_backoff_seconds(4) == 960

    def test_cap_at_1800_seconds(self) -> None:
        """60 * 2^5 = 1920 → capped to 1800."""
        assert exponential_backoff_seconds(5) == 1800

    def test_high_counter_still_1800(self) -> None:
        for n in (6, 10, 20, 100):
            assert exponential_backoff_seconds(n) == 1800

    def test_never_exceeds_1800(self) -> None:
        for n in range(0, 20):
            assert exponential_backoff_seconds(n) <= 1800

    def test_monotonically_non_decreasing(self) -> None:
        values = [exponential_backoff_seconds(n) for n in range(0, 10)]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_negative_counter_treated_as_zero(self) -> None:
        assert exponential_backoff_seconds(-1) == 60
        assert exponential_backoff_seconds(-99) == 60

    def test_returns_int(self) -> None:
        result = exponential_backoff_seconds(0)
        assert isinstance(result, int)

    def test_boundary_counter_4_below_cap(self) -> None:
        """60 * 2^4 = 960 < 1800."""
        assert exponential_backoff_seconds(4) == 960

    def test_boundary_counter_5_at_cap(self) -> None:
        """60 * 2^5 = 1920 > 1800 → 1800."""
        assert exponential_backoff_seconds(5) == 1800

    def test_cap_is_exactly_1800_not_1799_or_1801(self) -> None:
        capped = [exponential_backoff_seconds(n) for n in range(5, 10)]
        for v in capped:
            assert v == 1800
