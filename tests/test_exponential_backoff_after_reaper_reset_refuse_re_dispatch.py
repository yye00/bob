"""Tests for exponential backoff after reaper-reset (feature 769a08d6).

Covers bob3.exponential_backoff_after_reaper_reset_refuse_re_dispatch.
exponential_backoff_after_reaper_reset_refuse_re_dispatch
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from bob3.exponential_backoff_after_reaper_reset_refuse_re_dispatch import (
    BackoffDecision,
    exponential_backoff_after_reaper_reset_refuse_re_dispatch,
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


def test_exponential_backoff_after_reaper_reset_refuse_re_dispatch():
    """Primary AC test: function exists, is callable, returns BackoffDecision."""
    feature = _feature(reap_count=0, last_reap_at=None)
    with patch("bob3.reaper.db"):
        result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
    assert isinstance(result, BackoffDecision)
    assert result.refused is False
    assert result.reason == "allowed"


class TestNeverReapedFeature:
    def test_never_reaped_is_allowed(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert result.refused is False
        assert result.escalated is False

    def test_none_reap_count_treated_as_zero(self):
        feature = _feature()
        feature.reap_count = None
        with patch("bob3.reaper.db"):
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert result.refused is False


class TestWithinBackoffWindow:
    def test_refused_when_within_window_reap1(self):
        # reap_count=1 → backoff=120s; reaped 60s ago → refused
        last = datetime.now(timezone.utc) - timedelta(seconds=60)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert result.refused is True
        assert result.reason == "within_window"
        assert result.backoff_seconds == 120

    def test_refused_when_within_window_reap2(self):
        # reap_count=2 → backoff=240s; reaped 100s ago → refused
        last = datetime.now(timezone.utc) - timedelta(seconds=100)
        feature = _feature(reap_count=2, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert result.refused is True
        assert result.backoff_seconds == 240

    def test_allowed_after_window_elapsed(self):
        # reap_count=1 → backoff=120s; reaped 200s ago → allowed
        last = datetime.now(timezone.utc) - timedelta(seconds=200)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert result.refused is False
        assert result.reason == "allowed"


class TestEscalation:
    def test_escalates_at_threshold_3(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=1)
        feature = _feature(reap_count=3, last_reap_at=last)
        with patch("bob3.orchestrator.reap_backoff.db") as mock_db:
            mock_db.update_feature.return_value = None
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert result.refused is True
        assert result.escalated is True
        assert result.reason == "escalated"
        mock_db.update_feature.assert_called_once()
        assert mock_db.update_feature.call_args[1]["status"] == "needs_human"

    def test_escalates_above_threshold(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=1)
        feature = _feature(reap_count=5, last_reap_at=last)
        with patch("bob3.orchestrator.reap_backoff.db") as mock_db:
            mock_db.update_feature.return_value = None
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert result.refused is True
        assert result.escalated is True

    def test_not_escalated_below_threshold(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=5)
        feature = _feature(reap_count=2, last_reap_at=last)
        with patch("bob3.reaper.db") as mock_db:
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert result.escalated is False
        mock_db.update_feature.assert_not_called()


class TestCustomNow:
    def test_accepts_custom_now_refused(self):
        anchor = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        last = anchor - timedelta(seconds=50)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature, now=anchor)
        assert result.refused is True

    def test_accepts_custom_now_allowed(self):
        anchor = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        last = anchor - timedelta(seconds=200)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(
                feature, now=anchor
            )
        assert result.refused is False


class TestBackoffFormula:
    @pytest.mark.parametrize("reap_count,expected_backoff", [
        (0, 60),
        (1, 120),
        (2, 240),
        (3, 480),
        (5, 1920),
        (6, 3600),
        (10, 3600),
    ])
    def test_backoff_seconds_in_result(self, reap_count, expected_backoff):
        # Use a time far in the past so we don't hit the backoff window
        last = datetime.now(timezone.utc) - timedelta(seconds=7200)
        feature = _feature(reap_count=reap_count, last_reap_at=last)
        with patch("bob3.reaper.db"):
            with patch("bob3.orchestrator.reap_backoff.db"):
                result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert result.backoff_seconds == expected_backoff


class TestReapCount:
    def test_reap_count_reflected_in_result(self):
        feature = _feature(reap_count=2, last_reap_at=datetime.now(timezone.utc) - timedelta(seconds=10))
        with patch("bob3.reaper.db"):
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert result.reap_count == 2

    def test_returns_backoff_decision_dataclass(self):
        feature = _feature(reap_count=1, last_reap_at=datetime.now(timezone.utc) - timedelta(seconds=10))
        with patch("bob3.reaper.db"):
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        assert hasattr(result, "refused")
        assert hasattr(result, "escalated")
        assert hasattr(result, "reap_count")
        assert hasattr(result, "backoff_seconds")
        assert hasattr(result, "reason")


class TestStringLastReapAt:
    def test_accepts_iso_string_last_reap_at(self):
        last = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            result = exponential_backoff_after_reaper_reset_refuse_re_dispatch(feature)
        # 60s elapsed, window=120s → refused
        assert result.refused is True
