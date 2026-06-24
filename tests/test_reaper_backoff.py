"""Tests for exponential backoff after reaper-reset (b75a279b).

Covers:
  - bob.reaper.stamp_reap_metadata
  - bob.reaper.should_refuse_redispatch
  - bob.dispatch.should_refuse_redispatch (integration AC)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from bob.reaper import (
    BackoffDecision,
    handle_exponential_backoff,
    should_refuse_redispatch,
    stamp_reap_metadata,
)
from bob.dispatch import should_refuse_redispatch as dispatch_should_refuse


# ── Helpers ────────────────────────────────────────────────────────────────────


def _feature(
    fid: str = "aaaaaaaa-0000-0000-0000-000000000001",
    reap_count: int = 0,
    last_reap_at: datetime | str | None = None,
    status: str = "ready",
) -> MagicMock:
    f = MagicMock()
    f.id = fid
    f.reap_count = reap_count
    f.last_reap_at = last_reap_at
    f.status = status
    return f


# ── stamp_reap_metadata ────────────────────────────────────────────────────────


class TestStampReapMetadata:
    def test_calls_db_update_feature_with_reap_fields(self):
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        fid = "bbbbbbbb-0000-0000-0000-000000000002"

        with patch("bob.reaper.db") as mock_db:
            stamp_reap_metadata(fid, reap_count=2, now=now)

        mock_db.update_feature.assert_called_once_with(
            fid,
            last_reap_at=now.isoformat(),
            reap_count=2,
        )

    def test_defaults_now_to_utc_when_not_provided(self):
        fid = "cccccccc-0000-0000-0000-000000000003"
        with patch("bob.reaper.db") as mock_db:
            before = datetime.now(timezone.utc)
            stamp_reap_metadata(fid, reap_count=1)
            after = datetime.now(timezone.utc)

        call_kwargs = mock_db.update_feature.call_args
        stamped_iso = call_kwargs[1]["last_reap_at"]
        stamped = datetime.fromisoformat(stamped_iso)
        if stamped.tzinfo is None:
            stamped = stamped.replace(tzinfo=timezone.utc)
        assert before <= stamped <= after

    def test_stamps_reap_count_zero(self):
        fid = "dddddddd-0000-0000-0000-000000000004"
        now = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch("bob.reaper.db") as mock_db:
            stamp_reap_metadata(fid, reap_count=0, now=now)
        mock_db.update_feature.assert_called_once_with(
            fid,
            last_reap_at=now.isoformat(),
            reap_count=0,
        )

    def test_stamps_high_reap_count(self):
        fid = "eeeeeeee-0000-0000-0000-000000000005"
        now = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch("bob.reaper.db") as mock_db:
            stamp_reap_metadata(fid, reap_count=10, now=now)
        call_kwargs = mock_db.update_feature.call_args[1]
        assert call_kwargs["reap_count"] == 10


# ── should_refuse_redispatch (bob.reaper) ────────────────────────────────────


class TestShouldRefuseRedispatch:
    def test_never_reaped_feature_is_allowed(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob.reaper.db"):
            result = should_refuse_redispatch(feature)
        assert result is False

    def test_allows_when_backoff_window_elapsed(self):
        # reap_count=1 → backoff=120s; 130s ago → allowed
        last = datetime.now(timezone.utc) - timedelta(seconds=130)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob.reaper.db"):
            result = should_refuse_redispatch(feature)
        assert result is False

    def test_refuses_when_within_backoff_window(self):
        # reap_count=1 → backoff=120s; 60s ago → refused
        last = datetime.now(timezone.utc) - timedelta(seconds=60)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob.reaper.db"):
            result = should_refuse_redispatch(feature)
        assert result is True

    def test_escalates_to_needs_human_after_3_reaps(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=5)
        feature = _feature(reap_count=3, last_reap_at=last)
        with patch("bob.orchestrator.reap_backoff.db") as mock_db:
            mock_db.update_feature.return_value = feature
            result = should_refuse_redispatch(feature)
        assert result is True
        mock_db.update_feature.assert_called_once()
        call_kwargs = mock_db.update_feature.call_args
        assert call_kwargs[1]["status"] == "needs_human"

    def test_escalates_above_threshold_too(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=1)
        feature = _feature(reap_count=5, last_reap_at=last)
        with patch("bob.orchestrator.reap_backoff.db") as mock_db:
            mock_db.update_feature.return_value = feature
            result = should_refuse_redispatch(feature)
        assert result is True

    def test_does_not_escalate_below_threshold(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=5)
        feature = _feature(reap_count=2, last_reap_at=last)
        with patch("bob.reaper.db") as mock_db:
            result = should_refuse_redispatch(feature)
        # Within backoff (2^2 * 60 = 240s), so refused but no escalation
        assert result is True
        mock_db.update_feature.assert_not_called()

    def test_accepts_custom_now(self):
        anchor = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        last = anchor - timedelta(seconds=50)
        feature = _feature(reap_count=1, last_reap_at=last)
        # 50s elapsed, window=120s → refused at anchor
        with patch("bob.reaper.db"):
            assert should_refuse_redispatch(feature, now=anchor) is True
        # 200s elapsed → allowed
        now_later = anchor + timedelta(seconds=150)
        with patch("bob.reaper.db"):
            assert should_refuse_redispatch(feature, now=now_later) is False

    def test_accepts_string_last_reap_at(self):
        last = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob.reaper.db"):
            result = should_refuse_redispatch(feature)
        # 60s elapsed, window=120s → refused
        assert result is True

    def test_none_reap_count_treated_as_zero(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        feature.reap_count = None
        with patch("bob.reaper.db"):
            result = should_refuse_redispatch(feature)
        assert result is False


# ── should_refuse_redispatch via bob.dispatch (integration AC) ───────────────


class TestDispatchShouldRefuseRedispatch:
    def test_function_exists_in_dispatch_module(self):
        from bob import dispatch as _dispatch_mod
        assert hasattr(_dispatch_mod, "should_refuse_redispatch"), (
            "bob.dispatch must export should_refuse_redispatch"
        )

    def test_dispatch_delegates_to_reaper(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=60)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob.reaper.db"):
            result = dispatch_should_refuse(feature)
        assert result is True

    def test_dispatch_allows_when_cleared(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob.reaper.db"):
            result = dispatch_should_refuse(feature)
        assert result is False

    def test_dispatch_escalates_after_threshold(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=1)
        feature = _feature(reap_count=3, last_reap_at=last)
        with patch("bob.orchestrator.reap_backoff.db") as mock_db:
            mock_db.update_feature.return_value = feature
            result = dispatch_should_refuse(feature)
        assert result is True
        mock_db.update_feature.assert_called_once()


# ── handle_exponential_backoff ────────────────────────────────────────────────


class TestHandleExponentialBackoff:
    def test_returns_backoff_decision(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob.reaper.db"):
            result = handle_exponential_backoff(feature)
        assert isinstance(result, BackoffDecision)

    def test_never_reaped_is_allowed(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob.reaper.db"):
            result = handle_exponential_backoff(feature)
        assert result.refused is False
        assert result.escalated is False
        assert result.reason == "allowed"

    def test_within_window_is_refused(self):
        # reap_count=1 → backoff=120s; reaped 30s ago → refused
        last = datetime.now(timezone.utc) - timedelta(seconds=30)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob.reaper.db"):
            result = handle_exponential_backoff(feature)
        assert result.refused is True
        assert result.escalated is False
        assert result.reason == "within_window"
        assert result.backoff_seconds == 120

    def test_after_window_elapsed_is_allowed(self):
        # reap_count=1 → backoff=120s; reaped 200s ago → allowed
        last = datetime.now(timezone.utc) - timedelta(seconds=200)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob.reaper.db"):
            result = handle_exponential_backoff(feature)
        assert result.refused is False
        assert result.reason == "allowed"

    def test_escalates_at_threshold_3(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=1)
        feature = _feature(reap_count=3, last_reap_at=last)
        with patch("bob.orchestrator.reap_backoff.db") as mock_db:
            mock_db.update_feature.return_value = None
            result = handle_exponential_backoff(feature)
        assert result.refused is True
        assert result.escalated is True
        assert result.reason == "escalated"
        mock_db.update_feature.assert_called_once()
        assert mock_db.update_feature.call_args[1]["status"] == "needs_human"

    def test_escalates_above_threshold(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=1)
        feature = _feature(reap_count=5, last_reap_at=last)
        with patch("bob.orchestrator.reap_backoff.db") as mock_db:
            mock_db.update_feature.return_value = None
            result = handle_exponential_backoff(feature)
        assert result.refused is True
        assert result.escalated is True
        assert result.reap_count == 5

    def test_reap_count_and_backoff_in_result(self):
        last = datetime.now(timezone.utc) - timedelta(seconds=10)
        feature = _feature(reap_count=2, last_reap_at=last)
        with patch("bob.reaper.db"):
            result = handle_exponential_backoff(feature)
        assert result.reap_count == 2
        assert result.backoff_seconds == 240  # 2^2 * 60

    def test_accepts_custom_now(self):
        anchor = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        last = anchor - timedelta(seconds=50)
        feature = _feature(reap_count=1, last_reap_at=last)
        # 50s elapsed, window=120s → refused
        with patch("bob.reaper.db"):
            r = handle_exponential_backoff(feature, now=anchor)
        assert r.refused is True
        # 200s later → allowed
        with patch("bob.reaper.db"):
            r2 = handle_exponential_backoff(feature, now=anchor + timedelta(seconds=200))
        assert r2.refused is False


# ── compute_backoff_seconds cross-checks ──────────────────────────────────────


class TestBackoffFormula:
    @pytest.mark.parametrize("reap_count,expected", [
        (0, 60),
        (1, 120),
        (2, 240),
        (3, 480),
        (4, 960),
        (5, 1920),
        (6, 3600),   # capped
        (10, 3600),  # capped
    ])
    def test_compute_backoff_seconds(self, reap_count, expected):
        from bob.orchestrator.reap_backoff import compute_backoff_seconds
        assert compute_backoff_seconds(reap_count) == expected

    def test_negative_reap_count_treated_as_zero(self):
        from bob.orchestrator.reap_backoff import compute_backoff_seconds
        assert compute_backoff_seconds(-1) == 60
