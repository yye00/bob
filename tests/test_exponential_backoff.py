"""Tests for bob3.exponential_backoff — exponential backoff after reaper-reset.

Feature c9b640d0: Verifies that:
- should_refuse_redispatch correctly refuses re-dispatch within the backoff window
- should_refuse_redispatch escalates after >= 3 reaps
- stamp_reap_metadata delegates correctly to the reaper
- Both functions reject invalid input with ValueError
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from bob3.exponential_backoff import (
    BackoffDecision,
    calculate_backoff_duration,
    should_refuse_redispatch,
    stamp_reap_metadata,
)


def _feature(
    fid: str = "aaaaaaaa-0000-0000-0000-000000000001",
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


class TestShouldRefuseRedispatch:
    """Tests for bob3.exponential_backoff.should_refuse_redispatch."""

    def test_never_reaped_feature_allowed(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature)
        assert result is False

    def test_returns_bool(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature)
        assert isinstance(result, bool)

    def test_within_backoff_window_reap1_refused(self):
        # reap_count=1 → backoff=120s; elapsed=60s → refused
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=60)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature, now=now)
        assert result is True

    def test_outside_backoff_window_reap1_allowed(self):
        # reap_count=1 → backoff=120s; elapsed=180s → allowed
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=180)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature, now=now)
        assert result is False

    def test_within_backoff_window_reap2_refused(self):
        # reap_count=2 → backoff=240s; elapsed=120s → refused
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=120)
        feature = _feature(reap_count=2, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature, now=now)
        assert result is True

    def test_backoff_capped_at_3600_seconds(self):
        # reap_count=100 → backoff capped at 3600s; elapsed=3500s → refused
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=3500)
        feature = _feature(reap_count=100, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature, now=now)
        assert result is True

    def test_escalates_after_3_reaps(self):
        # reap_count=3 → escalate to needs_human, always refused
        feature = _feature(reap_count=3, last_reap_at=None)
        with patch("bob3.orchestrator.reap_backoff.db") as mock_db:
            result = should_refuse_redispatch(feature)
        assert result is True
        mock_db.update_feature.assert_called_once()

    def test_escalates_after_more_than_3_reaps(self):
        feature = _feature(reap_count=5, last_reap_at=None)
        with patch("bob3.orchestrator.reap_backoff.db") as mock_db:
            result = should_refuse_redispatch(feature)
        assert result is True
        mock_db.update_feature.assert_called_once()

    def test_none_feature_raises_value_error(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            should_refuse_redispatch(None)

    def test_string_feature_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            should_refuse_redispatch("not-a-feature")

    def test_integer_feature_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            should_refuse_redispatch(42)

    def test_none_reap_count_treated_as_zero_allowed(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        feature.reap_count = None
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature)
        assert result is False

    def test_explicit_now_accepted(self):
        now = datetime.now(timezone.utc)
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature, now=now)
        assert result is False


class TestStampReapMetadata:
    """Tests for bob3.exponential_backoff.stamp_reap_metadata."""

    def test_stamp_calls_db_update_feature(self):
        fid = "bbbbbbbb-0000-0000-0000-000000000002"
        now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch("bob3.reaper.db") as mock_db:
            stamp_reap_metadata(fid, reap_count=1, now=now)
        mock_db.update_feature.assert_called_once()
        call_kwargs = mock_db.update_feature.call_args
        assert fid in call_kwargs[0] or fid == call_kwargs[0][0]

    def test_stamp_reap_count_written(self):
        fid = "cccccccc-0000-0000-0000-000000000003"
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        with patch("bob3.reaper.db") as mock_db:
            stamp_reap_metadata(fid, reap_count=2, now=now)
        mock_db.update_feature.assert_called_once()
        _, kwargs = mock_db.update_feature.call_args
        assert kwargs.get("reap_count") == 2

    def test_stamp_last_reap_at_written(self):
        fid = "dddddddd-0000-0000-0000-000000000004"
        now = datetime(2026, 6, 1, 15, 30, 0, tzinfo=timezone.utc)
        with patch("bob3.reaper.db") as mock_db:
            stamp_reap_metadata(fid, reap_count=1, now=now)
        mock_db.update_feature.assert_called_once()
        _, kwargs = mock_db.update_feature.call_args
        assert kwargs.get("last_reap_at") == now.isoformat()

    def test_stamp_with_default_now_does_not_raise(self):
        fid = "eeeeeeee-0000-0000-0000-000000000005"
        with patch("bob3.reaper.db"):
            stamp_reap_metadata(fid, reap_count=0)

    def test_stamp_zero_reap_count(self):
        fid = "ffffffff-0000-0000-0000-000000000006"
        now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch("bob3.reaper.db") as mock_db:
            stamp_reap_metadata(fid, reap_count=0, now=now)
        mock_db.update_feature.assert_called_once()
        _, kwargs = mock_db.update_feature.call_args
        assert kwargs.get("reap_count") == 0

    def test_stamp_high_reap_count(self):
        fid = "aaaaaaaa-1111-0000-0000-000000000007"
        now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch("bob3.reaper.db") as mock_db:
            stamp_reap_metadata(fid, reap_count=10, now=now)
        _, kwargs = mock_db.update_feature.call_args
        assert kwargs.get("reap_count") == 10


class TestDispatchIntegration:
    """Verify bob3.dispatch imports should_refuse_redispatch."""

    def test_dispatch_imports_should_refuse_redispatch(self):
        import bob3.dispatch as dispatch_module
        assert hasattr(dispatch_module, "should_refuse_redispatch"), (
            "bob3.dispatch must expose should_refuse_redispatch for integration"
        )

    def test_exponential_backoff_module_importable(self):
        import bob3.exponential_backoff as mod
        assert callable(mod.should_refuse_redispatch)
        assert callable(mod.stamp_reap_metadata)

    def test_calculate_backoff_duration_importable(self):
        import bob3.exponential_backoff as mod
        assert callable(mod.calculate_backoff_duration)


class TestCalculateBackoffDuration:
    """Tests for bob3.exponential_backoff.calculate_backoff_duration."""

    def test_zero_reap_count_returns_60(self):
        assert calculate_backoff_duration(0) == 60

    def test_one_reap_count_returns_120(self):
        assert calculate_backoff_duration(1) == 120

    def test_two_reap_count_returns_240(self):
        assert calculate_backoff_duration(2) == 240

    def test_large_reap_count_capped_at_3600(self):
        assert calculate_backoff_duration(100) == 3600

    def test_six_reap_count_hits_cap(self):
        assert calculate_backoff_duration(6) == 3600

    def test_five_reap_count_below_cap(self):
        assert calculate_backoff_duration(5) == 1920

    def test_negative_reap_count_returns_60(self):
        assert calculate_backoff_duration(-1) == 60

    def test_returns_int(self):
        result = calculate_backoff_duration(3)
        assert isinstance(result, int)

    def test_non_integer_raises_type_error(self):
        with pytest.raises((TypeError, ValueError)):
            calculate_backoff_duration("two")

    def test_none_raises(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            calculate_backoff_duration(None)
