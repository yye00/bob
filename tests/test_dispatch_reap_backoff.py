"""Tests for bob3.dispatch.check_reap_backoff (feature df830312).

Covers:
  - Function defined: bob3.dispatch.check_reap_backoff
  - Function defined: bob3.stuck_executing_reaper.record_reap
  - integration: bob3.dispatch
  - behavior: handles boundary case of empty/zero input
  - behavior: raises ValueError or returns rejection for invalid input
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from bob3.dispatch import check_reap_backoff
from bob3.stuck_executing_reaper import record_reap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# check_reap_backoff — function-defined AC
# ---------------------------------------------------------------------------

class TestCheckReapBackoffExists:
    def test_importable_from_dispatch(self):
        """Function defined: bob3.dispatch.check_reap_backoff"""
        from bob3.dispatch import check_reap_backoff as fn
        assert callable(fn)

    def test_returns_bool(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = check_reap_backoff(feature)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# check_reap_backoff — invalid input raises ValueError
# ---------------------------------------------------------------------------

class TestCheckReapBackoffInvalidInput:
    def test_raises_on_none_feature(self):
        """behavior: raises ValueError for invalid input (None feature)"""
        with pytest.raises(ValueError):
            check_reap_backoff(None)

    def test_does_not_silently_succeed_on_none(self):
        """behavior: does not silently succeed with invalid input"""
        raised = False
        try:
            check_reap_backoff(None)
        except (ValueError, TypeError, AttributeError):
            raised = True
        assert raised, "Expected an exception for None feature, but none was raised"


# ---------------------------------------------------------------------------
# check_reap_backoff — boundary: zero/empty reap state
# ---------------------------------------------------------------------------

class TestCheckReapBackoffBoundary:
    def test_zero_reap_count_allowed(self):
        """behavior: handles empty/zero input — zero reap_count is dispatchable"""
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature)
        assert refused is False

    def test_none_last_reap_at_allowed(self):
        """behavior: handles empty/zero input — None last_reap_at is dispatchable"""
        feature = _feature(reap_count=1, last_reap_at=None)
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature)
        assert refused is False

    def test_none_reap_count_treated_as_zero(self):
        """behavior: handles empty/zero input — None reap_count treated as 0"""
        feature = _feature()
        feature.reap_count = None
        feature.last_reap_at = None
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature)
        assert refused is False


# ---------------------------------------------------------------------------
# check_reap_backoff — within backoff window
# ---------------------------------------------------------------------------

class TestCheckReapBackoffWindow:
    def test_refused_within_window_reap1(self):
        # reap_count=1 → backoff=120s; reaped 60s ago → refused
        last = datetime.now(timezone.utc) - timedelta(seconds=60)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature)
        assert refused is True

    def test_allowed_after_window_reap1(self):
        # reap_count=1 → backoff=120s; reaped 200s ago → allowed
        last = datetime.now(timezone.utc) - timedelta(seconds=200)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature)
        assert refused is False

    def test_refused_within_window_reap2(self):
        # reap_count=2 → backoff=240s; reaped 100s ago → refused
        last = datetime.now(timezone.utc) - timedelta(seconds=100)
        feature = _feature(reap_count=2, last_reap_at=last)
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature)
        assert refused is True

    def test_allowed_after_window_reap2(self):
        # reap_count=2 → backoff=240s; reaped 300s ago → allowed
        last = datetime.now(timezone.utc) - timedelta(seconds=300)
        feature = _feature(reap_count=2, last_reap_at=last)
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature)
        assert refused is False

    def test_backoff_cap_3600s(self):
        # reap_count=100 → backoff capped at 3600s; reaped 1800s ago → refused
        last = datetime.now(timezone.utc) - timedelta(seconds=1800)
        feature = _feature(reap_count=100, last_reap_at=last)
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature)
        assert refused is True


# ---------------------------------------------------------------------------
# check_reap_backoff — escalation after 3 reaps
# ---------------------------------------------------------------------------

class TestCheckReapBackoffEscalation:
    def test_refused_and_escalated_after_3_reaps(self):
        # reap_count >= 3 → escalate to needs_human, refuse dispatch
        feature = _feature(reap_count=3, last_reap_at=datetime.now(timezone.utc))
        with patch("bob3.reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            refused = check_reap_backoff(feature)
        assert refused is True

    def test_refused_after_5_reaps(self):
        feature = _feature(reap_count=5, last_reap_at=datetime.now(timezone.utc))
        with patch("bob3.reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            refused = check_reap_backoff(feature)
        assert refused is True

    def test_allowed_at_reap_count_2_outside_window(self):
        # reap_count=2 < 3, and outside the 240s window → allowed
        last = datetime.now(timezone.utc) - timedelta(seconds=300)
        feature = _feature(reap_count=2, last_reap_at=last)
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature)
        assert refused is False


# ---------------------------------------------------------------------------
# check_reap_backoff — now parameter
# ---------------------------------------------------------------------------

class TestCheckReapBackoffNowParam:
    def test_custom_now_within_window(self):
        # Reaped at T, check at T+60s, backoff=120s → still refused
        last = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        now = last + timedelta(seconds=60)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature, now=now)
        assert refused is True

    def test_custom_now_outside_window(self):
        # Reaped at T, check at T+200s, backoff=120s → allowed
        last = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        now = last + timedelta(seconds=200)
        feature = _feature(reap_count=1, last_reap_at=last)
        with patch("bob3.reaper.db"):
            refused = check_reap_backoff(feature, now=now)
        assert refused is False


# ---------------------------------------------------------------------------
# integration: bob3.dispatch — module exports check_reap_backoff
# ---------------------------------------------------------------------------

class TestDispatchIntegration:
    def test_check_reap_backoff_in_dispatch_all(self):
        """integration: bob3.dispatch exports check_reap_backoff"""
        import bob3.dispatch as dispatch_mod
        assert "check_reap_backoff" in dispatch_mod.__all__

    def test_dispatch_module_importable(self):
        import bob3.dispatch  # noqa: F401
        assert True


# ---------------------------------------------------------------------------
# record_reap — function-defined AC
# ---------------------------------------------------------------------------

class TestRecordReapExists:
    def test_importable_from_stuck_executing_reaper(self):
        """Function defined: bob3.stuck_executing_reaper.record_reap"""
        from bob3.stuck_executing_reaper import record_reap as fn
        assert callable(fn)

    def test_in_module_all(self):
        import bob3.stuck_executing_reaper as m
        assert "record_reap" in m.__all__


class TestRecordReapInvalidInput:
    def test_raises_on_empty_feature_id(self):
        """behavior: raises ValueError for empty feature_id"""
        with pytest.raises(ValueError):
            with patch("bob3.reaper.db"):
                record_reap("", 1)

    def test_raises_on_negative_reap_count(self):
        """behavior: raises ValueError for negative reap_count"""
        with pytest.raises(ValueError):
            with patch("bob3.reaper.db"):
                record_reap("aaaaaaaa-0000-0000-0000-000000000001", -1)

    def test_does_not_silently_succeed_on_empty_id(self):
        raised = False
        try:
            with patch("bob3.reaper.db"):
                record_reap("", 1)
        except (ValueError, TypeError):
            raised = True
        assert raised


class TestRecordReapBoundary:
    def test_zero_reap_count_is_valid(self):
        """behavior: handles zero reap_count boundary — does not crash"""
        fid = "aaaaaaaa-0000-0000-0000-000000000001"
        with patch("bob3.reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            record_reap(fid, 0)
        mock_db.update_feature.assert_called_once()

    def test_stamps_reap_metadata_via_db(self):
        fid = "aaaaaaaa-0000-0000-0000-000000000002"
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        with patch("bob3.reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            record_reap(fid, 2, now=now)
        call_kwargs = mock_db.update_feature.call_args
        assert call_kwargs is not None
        # Called with positional feature_id arg
        assert call_kwargs[0][0] == fid

    def test_accepts_explicit_now(self):
        fid = "aaaaaaaa-0000-0000-0000-000000000003"
        now = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch("bob3.reaper.db") as mock_db:
            mock_db.update_feature.return_value = None
            record_reap(fid, 1, now=now)
        mock_db.update_feature.assert_called_once()
