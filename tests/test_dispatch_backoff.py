"""Tests for bob3.dispatch_backoff — exponential backoff after reaper-reset.

AC: pytest: tests/test_dispatch_backoff.py
AC: integration: bob3.dispatch

Verifies:
- bob3.dispatch_backoff.should_refuse_recent_reap exists and delegates to reaper
- bob3.dispatch_backoff.stamp_reap_metadata exists and delegates to reaper
- bob3.dispatch.should_refuse_recent_reap is available (integration AC)
- Error paths raise ValueError
- Boundary cases return well-defined results
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from bob3.dispatch_backoff import should_refuse_recent_reap, stamp_reap_metadata


def _feature(
    fid: str = "aaaabbbb-0000-0000-0000-000000000001",
    reap_count: int = 0,
    last_reap_at=None,
    status: str = "ready",
) -> MagicMock:
    f = MagicMock()
    f.id = fid
    f.reap_count = reap_count
    f.last_reap_at = last_reap_at
    f.status = status
    return f


# ── should_refuse_recent_reap ─────────────────────────────────────────────────


class TestShouldRefuseRecentReap:
    def test_none_feature_raises_value_error(self):
        with pytest.raises(ValueError, match="must not be None"):
            should_refuse_recent_reap(None)

    def test_non_feature_lacking_id_raises_value_error(self):
        with pytest.raises(ValueError, match="id"):
            should_refuse_recent_reap("not-a-feature")

    def test_zero_reap_count_no_last_reap_returns_false(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = should_refuse_recent_reap(feature)
        assert result is False

    def test_within_backoff_window_returns_true(self):
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=30)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = should_refuse_recent_reap(feature, now=now)
        assert result is True

    def test_outside_backoff_window_returns_false(self):
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=200)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = should_refuse_recent_reap(feature, now=now)
        assert result is False

    def test_reap_count_at_escalation_threshold_escalates(self):
        feature = _feature(reap_count=3, last_reap_at=datetime.now(timezone.utc))
        with patch("bob3.orchestrator.reap_backoff.db") as mock_db:
            result = should_refuse_recent_reap(feature)
        assert result is True
        mock_db.update_feature.assert_called_once()

    def test_returns_bool(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = should_refuse_recent_reap(feature)
        assert isinstance(result, bool)

    def test_now_defaults_to_utc(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = should_refuse_recent_reap(feature, now=None)
        assert isinstance(result, bool)


# ── stamp_reap_metadata ───────────────────────────────────────────────────────


class TestStampReapMetadata:
    def test_empty_feature_id_raises(self):
        with pytest.raises(ValueError, match="feature_id"):
            stamp_reap_metadata("", reap_count=1)

    def test_none_feature_id_raises(self):
        with pytest.raises(ValueError):
            stamp_reap_metadata(None, reap_count=1)

    def test_negative_reap_count_raises(self):
        with pytest.raises(ValueError, match="reap_count"):
            stamp_reap_metadata("some-feature-id", reap_count=-1)

    def test_non_int_reap_count_raises(self):
        with pytest.raises(ValueError):
            stamp_reap_metadata("some-feature-id", reap_count="three")

    def test_valid_call_delegates_to_reaper(self):
        with patch("bob3.dispatch_backoff.bob3.reaper" if False else "bob3.reaper.db") as mock_db:
            with patch("bob3.reaper.stamp_reap_metadata") as mock_stamp:
                stamp_reap_metadata("feature-uuid-0001", reap_count=2)
        mock_stamp.assert_called_once_with("feature-uuid-0001", reap_count=2, now=None)

    def test_zero_reap_count_accepted(self):
        with patch("bob3.reaper.stamp_reap_metadata") as mock_stamp:
            stamp_reap_metadata("feature-uuid-0002", reap_count=0)
        mock_stamp.assert_called_once()

    def test_custom_now_passed_through(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with patch("bob3.reaper.stamp_reap_metadata") as mock_stamp:
            stamp_reap_metadata("feature-uuid-0003", reap_count=1, now=now)
        mock_stamp.assert_called_once_with("feature-uuid-0003", reap_count=1, now=now)


# ── Integration: bob3.dispatch exposes should_refuse_recent_reap ──────────────


class TestDispatchIntegration:
    def test_should_refuse_recent_reap_importable_from_dispatch(self):
        import bob3.dispatch as dispatch_mod
        assert hasattr(dispatch_mod, "should_refuse_recent_reap")
        assert callable(dispatch_mod.should_refuse_recent_reap)

    def test_dispatch_should_refuse_recent_reap_works(self):
        import bob3.dispatch as dispatch_mod
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = dispatch_mod.should_refuse_recent_reap(feature)
        assert isinstance(result, bool)

    def test_dispatch_backoff_module_importable(self):
        import bob3.dispatch_backoff
        assert hasattr(bob3.dispatch_backoff, "should_refuse_recent_reap")
        assert hasattr(bob3.dispatch_backoff, "stamp_reap_metadata")
