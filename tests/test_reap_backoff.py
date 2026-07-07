"""Tests for orchestrator.reap_backoff (feature 01d07a40).

Exponential backoff after reaper-reset: refuse re-dispatch of a recently reaped
feature until min(2^reap_count * 60s, 3600s) has elapsed since last_reap_at.

Covers the two AC-required entry points:
  - orchestrator.reap_backoff.next_dispatch_allowed_at
  - orchestrator.reap_backoff.should_refuse_redispatch
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.reap_backoff import (
    next_dispatch_allowed_at,
    should_refuse_redispatch,
)


class _FakeFeature:
    def __init__(self, id="feat-1234abcd", reap_count=0, last_reap_at=None):
        self.id = id
        self.reap_count = reap_count
        self.last_reap_at = last_reap_at


class TestNextDispatchAllowedAt:
    def test_never_reaped_returns_epoch(self):
        f = _FakeFeature(reap_count=0, last_reap_at=None)
        allowed = next_dispatch_allowed_at(f)
        assert allowed <= datetime.now(timezone.utc)

    def test_one_reap_adds_120s(self):
        reaped = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        f = _FakeFeature(reap_count=1, last_reap_at=reaped)
        allowed = next_dispatch_allowed_at(f)
        assert allowed == reaped + timedelta(seconds=120)

    def test_backoff_capped_at_3600s(self):
        reaped = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        f = _FakeFeature(reap_count=20, last_reap_at=reaped)
        allowed = next_dispatch_allowed_at(f)
        assert allowed == reaped + timedelta(seconds=3600)

    def test_naive_last_reap_at_treated_as_utc(self):
        reaped = datetime(2026, 1, 1, 12, 0, 0)  # naive
        f = _FakeFeature(reap_count=1, last_reap_at=reaped)
        allowed = next_dispatch_allowed_at(f)
        assert allowed.tzinfo is not None
        assert allowed == reaped.replace(tzinfo=timezone.utc) + timedelta(seconds=120)

    def test_none_feature_raises_value_error(self):
        with pytest.raises(ValueError):
            next_dispatch_allowed_at(None)


class TestShouldRefuseRedispatch:
    def test_never_reaped_not_refused(self):
        f = _FakeFeature(reap_count=0, last_reap_at=None)
        assert should_refuse_redispatch(f) is False

    def test_within_backoff_window_refused(self):
        now = datetime(2026, 1, 1, 12, 0, 30, tzinfo=timezone.utc)
        reaped = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)  # 30s ago
        f = _FakeFeature(reap_count=1, last_reap_at=reaped)  # needs 120s
        assert should_refuse_redispatch(f, now=now) is True

    def test_after_backoff_window_allowed(self):
        now = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)  # 300s later
        reaped = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        f = _FakeFeature(reap_count=1, last_reap_at=reaped)  # needs 120s
        assert should_refuse_redispatch(f, now=now) is False

    def test_none_feature_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            should_refuse_redispatch(None)
