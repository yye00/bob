"""Tests for bob3.reaper.handle_exponential_backoff (feature c5859f93).

Verifies the top-level API in bob3.reaper:
  - handle_exponential_backoff returns BackoffDecision with correct fields
  - should_refuse_redispatch correctly enforces backoff and escalation
  - stamp_reap_metadata stamps DB fields
  - integration: orchestrator dispatch loop is informed by BackoffDecision
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from bob3.reaper import (
    BackoffDecision,
    handle_exponential_backoff,
    should_refuse_redispatch,
    stamp_reap_metadata,
)
from bob3.orchestrator.reap_backoff import compute_backoff_seconds


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _feature(
    fid: str = "deadbeef-0000-0000-0000-000000000001",
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
# compute_backoff_seconds
# ---------------------------------------------------------------------------

class TestComputeBackoffSeconds:
    def test_zero_reaps_returns_60(self):
        assert compute_backoff_seconds(0) == 60

    def test_one_reap_returns_120(self):
        assert compute_backoff_seconds(1) == 120

    def test_two_reaps_returns_240(self):
        assert compute_backoff_seconds(2) == 240

    def test_three_reaps_returns_480(self):
        assert compute_backoff_seconds(3) == 480

    def test_cap_at_3600(self):
        assert compute_backoff_seconds(100) == 3600

    def test_negative_reap_count_treated_as_zero(self):
        assert compute_backoff_seconds(-1) == 60


# ---------------------------------------------------------------------------
# handle_exponential_backoff — allowed path
# ---------------------------------------------------------------------------

class TestHandleExponentialBackoffAllowed:
    def test_no_prior_reap_allowed(self):
        f = _feature(reap_count=0, last_reap_at=None)
        result = handle_exponential_backoff(f)
        assert isinstance(result, BackoffDecision)
        assert result.refused is False
        assert result.escalated is False
        assert result.reason == "allowed"

    def test_backoff_window_elapsed_allowed(self):
        now = _now()
        last_reap = now - timedelta(seconds=200)
        f = _feature(reap_count=1, last_reap_at=last_reap.isoformat())
        # backoff for reap_count=1 is 120s; 200s has elapsed → allowed
        result = handle_exponential_backoff(f, now=now)
        assert result.refused is False
        assert result.reason == "allowed"

    def test_returns_backoff_decision_dataclass(self):
        f = _feature(reap_count=0)
        result = handle_exponential_backoff(f)
        assert hasattr(result, "refused")
        assert hasattr(result, "escalated")
        assert hasattr(result, "reap_count")
        assert hasattr(result, "backoff_seconds")
        assert hasattr(result, "reason")


# ---------------------------------------------------------------------------
# handle_exponential_backoff — within_window path
# ---------------------------------------------------------------------------

class TestHandleExponentialBackoffWithinWindow:
    def test_within_60s_window_refused(self):
        now = _now()
        last_reap = now - timedelta(seconds=30)
        f = _feature(reap_count=1, last_reap_at=last_reap.isoformat())
        result = handle_exponential_backoff(f, now=now)
        assert result.refused is True
        assert result.escalated is False
        assert result.reason == "within_window"

    def test_within_120s_window_refused(self):
        now = _now()
        last_reap = now - timedelta(seconds=100)
        f = _feature(reap_count=1, last_reap_at=last_reap.isoformat())
        result = handle_exponential_backoff(f, now=now)
        assert result.refused is True
        assert result.reason == "within_window"

    def test_backoff_seconds_reflects_reap_count(self):
        now = _now()
        last_reap = now - timedelta(seconds=10)
        f = _feature(reap_count=2, last_reap_at=last_reap.isoformat())
        result = handle_exponential_backoff(f, now=now)
        assert result.backoff_seconds == 240  # 2^2 * 60


# ---------------------------------------------------------------------------
# handle_exponential_backoff — escalation path
# ---------------------------------------------------------------------------

class TestHandleExponentialBackoffEscalation:
    @patch("bob3.reaper.escalate_after_n_reaps", return_value=True)
    def test_three_reaps_escalates(self, mock_escalate):
        f = _feature(reap_count=3)
        result = handle_exponential_backoff(f)
        assert result.refused is True
        assert result.escalated is True
        assert result.reason == "escalated"

    @patch("bob3.reaper.escalate_after_n_reaps", return_value=True)
    def test_four_reaps_escalates(self, mock_escalate):
        f = _feature(reap_count=4)
        result = handle_exponential_backoff(f)
        assert result.escalated is True
        assert result.reason == "escalated"

    @patch("bob3.reaper.escalate_after_n_reaps", return_value=True)
    def test_reap_count_propagated_correctly(self, mock_escalate):
        f = _feature(reap_count=3)
        result = handle_exponential_backoff(f)
        assert result.reap_count == 3


# ---------------------------------------------------------------------------
# should_refuse_redispatch
# ---------------------------------------------------------------------------

class TestShouldRefuseRedispatch:
    def test_no_prior_reap_returns_false(self):
        f = _feature(reap_count=0, last_reap_at=None)
        assert should_refuse_redispatch(f) is False

    def test_within_window_returns_true(self):
        now = _now()
        last_reap = now - timedelta(seconds=30)
        f = _feature(reap_count=1, last_reap_at=last_reap.isoformat())
        assert should_refuse_redispatch(f, now=now) is True

    def test_window_elapsed_returns_false(self):
        now = _now()
        last_reap = now - timedelta(seconds=200)
        f = _feature(reap_count=1, last_reap_at=last_reap.isoformat())
        assert should_refuse_redispatch(f, now=now) is False

    @patch("bob3.reaper.escalate_after_n_reaps", return_value=True)
    def test_three_reaps_escalated_refuses(self, _mock):
        f = _feature(reap_count=3)
        assert should_refuse_redispatch(f) is True

    def test_none_feature_raises(self):
        with pytest.raises(ValueError):
            should_refuse_redispatch(None)

    def test_non_feature_raises(self):
        with pytest.raises(ValueError):
            should_refuse_redispatch("not-a-feature")


# ---------------------------------------------------------------------------
# stamp_reap_metadata
# ---------------------------------------------------------------------------

class TestStampReapMetadata:
    @patch("bob3.reaper.db")
    def test_calls_update_feature_with_reap_count(self, mock_db):
        now = _now()
        stamp_reap_metadata("feat-id-1", reap_count=2, now=now)
        mock_db.update_feature.assert_called_once_with(
            "feat-id-1",
            last_reap_at=now.isoformat(),
            reap_count=2,
        )

    @patch("bob3.reaper.db")
    def test_defaults_now_to_utc(self, mock_db):
        stamp_reap_metadata("feat-id-2", reap_count=1)
        assert mock_db.update_feature.called
        _, kwargs = mock_db.update_feature.call_args
        assert "last_reap_at" in kwargs

    @patch("bob3.reaper.db")
    def test_zero_reap_count_valid(self, mock_db):
        now = _now()
        stamp_reap_metadata("feat-id-3", reap_count=0, now=now)
        mock_db.update_feature.assert_called_once()


# ---------------------------------------------------------------------------
# Integration: orchestrator dispatch loop uses BackoffDecision
# ---------------------------------------------------------------------------

class TestOrchestratorIntegration:
    """Verify that handle_exponential_backoff output can gate dispatch."""

    def test_dispatch_skipped_when_refused(self):
        """Simulate dispatch loop checking BackoffDecision before dispatching."""
        now = _now()
        last_reap = now - timedelta(seconds=10)
        f = _feature(reap_count=1, last_reap_at=last_reap.isoformat())

        decision = handle_exponential_backoff(f, now=now)
        dispatched = not decision.refused
        assert dispatched is False

    def test_dispatch_proceeds_when_allowed(self):
        f = _feature(reap_count=0, last_reap_at=None)
        decision = handle_exponential_backoff(f)
        dispatched = not decision.refused
        assert dispatched is True

    @patch("bob3.reaper.escalate_after_n_reaps", return_value=True)
    def test_escalation_prevents_dispatch(self, _mock):
        f = _feature(reap_count=3)
        decision = handle_exponential_backoff(f)
        assert decision.refused is True
        assert decision.escalated is True
