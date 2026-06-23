"""Tests that may_redispatch blocks re-dispatch while within backoff window."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from bob3.orchestrator.reap_backoff import compute_backoff_seconds, may_redispatch


def _feature(reap_count: int, last_reap_at: datetime | None) -> MagicMock:
    f = MagicMock()
    f.id = "abcdef00-0000-0000-0000-000000000001"
    f.reap_count = reap_count
    f.last_reap_at = last_reap_at
    return f


class TestMayRedispatchBlocksWithinWindow:
    def test_no_last_reap_at_allows_dispatch(self):
        feature = _feature(reap_count=2, last_reap_at=None)
        assert may_redispatch(feature) is True

    def test_zero_reap_count_allows_dispatch_even_with_last_reap_at(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=1)
        feature = _feature(reap_count=0, last_reap_at=last)
        assert may_redispatch(feature) is True

    def test_blocks_when_within_window(self):
        # reap_count=1 → backoff=120s; set last_reap_at to 60s ago → blocked
        last = datetime.now(timezone.utc) - timedelta(seconds=60)
        feature = _feature(reap_count=1, last_reap_at=last)
        assert may_redispatch(feature) is False

    def test_allows_when_window_elapsed(self):
        # reap_count=1 → backoff=120s; set last_reap_at to 130s ago → allowed
        last = datetime.now(timezone.utc) - timedelta(seconds=130)
        feature = _feature(reap_count=1, last_reap_at=last)
        assert may_redispatch(feature) is True

    def test_blocks_at_exact_window_boundary(self):
        # exactly at the backoff boundary should still block (elapsed < backoff)
        backoff = compute_backoff_seconds(2)
        last = datetime.now(timezone.utc) - timedelta(seconds=backoff - 1)
        feature = _feature(reap_count=2, last_reap_at=last)
        assert may_redispatch(feature) is False

    def test_allows_just_after_window_boundary(self):
        backoff = compute_backoff_seconds(2)
        last = datetime.now(timezone.utc) - timedelta(seconds=backoff + 1)
        feature = _feature(reap_count=2, last_reap_at=last)
        assert may_redispatch(feature) is True

    def test_accepts_string_iso_last_reap_at(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=60)
        feature = _feature(reap_count=1, last_reap_at=last.isoformat())
        # within 120s window → blocked
        assert may_redispatch(feature) is False

    def test_accepts_naive_datetime_treated_as_utc(self):
        last = datetime.utcnow() - timedelta(seconds=60)
        feature = _feature(reap_count=1, last_reap_at=last)
        assert may_redispatch(feature) is False

    def test_custom_now_parameter(self):
        anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        last = anchor - timedelta(seconds=50)
        feature = _feature(reap_count=1, last_reap_at=last)
        # 50s elapsed, window=120 → blocked when now=anchor
        assert may_redispatch(feature, now=anchor) is False
        # 200s elapsed → allowed
        now_later = anchor + timedelta(seconds=150)
        assert may_redispatch(feature, now=now_later) is True
