"""Tests for exponential backoff reaper — feature 265ff52b.

Verifies that:
- calculate_backoff_delay returns correct exponential delay capped at 3600s
- should_refuse_redispatch correctly refuses features within backoff window
- should_refuse_redispatch escalates to needs_human after 3 reaps
- Integration: functions are callable from bob.dispatch context
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from bob.exponential_backoff_reaper import calculate_backoff_delay, should_refuse_redispatch


def _make_feature(
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


class TestCalculateBackoffDelay:
    def test_reap_count_zero_returns_60(self):
        result = calculate_backoff_delay(0)
        assert result == 60

    def test_reap_count_one_returns_120(self):
        result = calculate_backoff_delay(1)
        assert result == 120

    def test_reap_count_two_returns_240(self):
        result = calculate_backoff_delay(2)
        assert result == 240

    def test_reap_count_three_returns_480(self):
        result = calculate_backoff_delay(3)
        assert result == 480

    def test_reap_count_large_capped_at_3600(self):
        result = calculate_backoff_delay(100)
        assert result == 3600

    def test_reap_count_6_hits_cap(self):
        result = calculate_backoff_delay(6)
        assert result == 3600

    def test_reap_count_5_just_below_cap(self):
        result = calculate_backoff_delay(5)
        assert result == 1920

    def test_returns_integer(self):
        result = calculate_backoff_delay(2)
        assert isinstance(result, int)

    def test_negative_treated_as_zero(self):
        result = calculate_backoff_delay(-1)
        assert result == 60

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            calculate_backoff_delay(None)

    def test_string_raises_type_error(self):
        with pytest.raises(TypeError):
            calculate_backoff_delay("1")

    def test_float_raises_type_error(self):
        with pytest.raises(TypeError):
            calculate_backoff_delay(1.5)


class TestShouldRefuseRedispatch:
    def test_no_reap_history_allows_dispatch(self):
        feature = _make_feature(reap_count=0, last_reap_at=None)
        with patch("bob.orchestrator.reap_backoff.db"):
            result = should_refuse_redispatch(feature)
        assert result is False

    def test_recently_reaped_within_window_refused(self):
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=30)  # 30s ago, window is 120s (reap_count=1)
        feature = _make_feature(reap_count=1, last_reap_at=last)
        with patch("bob.orchestrator.reap_backoff.db"):
            result = should_refuse_redispatch(feature, now=now)
        assert result is True

    def test_after_backoff_window_allows_dispatch(self):
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=200)  # 200s ago, window is 120s (reap_count=1)
        feature = _make_feature(reap_count=1, last_reap_at=last)
        with patch("bob.orchestrator.reap_backoff.db"):
            result = should_refuse_redispatch(feature, now=now)
        assert result is False

    def test_exactly_3_reaps_escalates_to_needs_human(self):
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=600)
        feature = _make_feature(reap_count=3, last_reap_at=last)
        with patch("bob.orchestrator.reap_backoff.db") as mock_db:
            result = should_refuse_redispatch(feature, now=now)
        assert result is True
        mock_db.update_feature.assert_called_once()

    def test_more_than_3_reaps_escalates(self):
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=3700)
        feature = _make_feature(reap_count=5, last_reap_at=last)
        with patch("bob.orchestrator.reap_backoff.db") as mock_db:
            result = should_refuse_redispatch(feature, now=now)
        assert result is True
        mock_db.update_feature.assert_called_once()

    def test_none_feature_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            should_refuse_redispatch(None)

    def test_string_feature_raises_type_error(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            should_refuse_redispatch("not-a-feature")

    def test_int_feature_raises_type_error(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            should_refuse_redispatch(42)

    def test_returns_bool(self):
        feature = _make_feature(reap_count=0, last_reap_at=None)
        with patch("bob.orchestrator.reap_backoff.db"):
            result = should_refuse_redispatch(feature)
        assert isinstance(result, bool)

    def test_two_reaps_within_window_refused(self):
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=100)  # 100s ago, window is 240s (reap_count=2)
        feature = _make_feature(reap_count=2, last_reap_at=last)
        with patch("bob.orchestrator.reap_backoff.db"):
            result = should_refuse_redispatch(feature, now=now)
        assert result is True

    def test_none_last_reap_at_always_allows(self):
        feature = _make_feature(reap_count=2, last_reap_at=None)
        with patch("bob.orchestrator.reap_backoff.db"):
            result = should_refuse_redispatch(feature)
        assert result is False


class TestDispatchIntegration:
    """Integration tests: verify functions can be used from bob.dispatch context."""

    def test_import_from_module(self):
        from bob.exponential_backoff_reaper import (
            calculate_backoff_delay,
            should_refuse_redispatch,
        )
        assert callable(calculate_backoff_delay)
        assert callable(should_refuse_redispatch)

    def test_dispatch_skips_within_backoff_feature(self):
        """Simulate dispatch loop checking a recently-reaped feature."""
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=30)
        feature = _make_feature(reap_count=1, last_reap_at=last)

        with patch("bob.orchestrator.reap_backoff.db"):
            refused = should_refuse_redispatch(feature, now=now)

        assert refused is True, "Dispatch loop should skip this feature"

    def test_dispatch_allows_expired_backoff_feature(self):
        """Simulate dispatch loop checking a feature whose backoff expired."""
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=200)  # reap_count=1 → 120s window elapsed
        feature = _make_feature(reap_count=1, last_reap_at=last)

        with patch("bob.orchestrator.reap_backoff.db"):
            refused = should_refuse_redispatch(feature, now=now)

        assert refused is False, "Dispatch loop should allow this feature"

    def test_dispatch_escalates_repeated_reaper_cycle(self):
        """After 3 reaps, the feature must be escalated to needs_human."""
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=3700)  # well past any window
        feature = _make_feature(reap_count=3, last_reap_at=last)

        with patch("bob.orchestrator.reap_backoff.db") as mock_db:
            refused = should_refuse_redispatch(feature, now=now)

        assert refused is True
        mock_db.update_feature.assert_called_once_with(
            feature.id,
            status="needs_human",
            last_improvement_type="repeated_reap_cycle",
        )
