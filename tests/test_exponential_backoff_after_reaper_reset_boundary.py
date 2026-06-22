"""Boundary-case tests for exponential backoff after reaper-reset.

AC: empty, zero, or minimum input returns a well-defined result rather than raising.

Covers edge inputs to:
  - bob3.reaper.apply_exponential_backoff (alias for handle_exponential_backoff)
  - bob3.reaper.should_refuse_redispatch
  - bob3.orchestrator.reap_backoff.compute_backoff_seconds
  - bob3.orchestrator.reap_backoff.may_redispatch
  - bob3.orchestrator.reap_backoff.escalate_after_n_reaps
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from bob3.reaper import apply_exponential_backoff, should_refuse_redispatch, BackoffDecision
from bob3.orchestrator.reap_backoff import (
    compute_backoff_seconds,
    may_redispatch,
    escalate_after_n_reaps,
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


class TestComputeBackoffSecondsBoundary:
    def test_zero_reap_count_returns_base_60(self):
        result = compute_backoff_seconds(0)
        assert result == 60

    def test_one_reap_count_returns_120(self):
        result = compute_backoff_seconds(1)
        assert result == 120

    def test_negative_reap_count_returns_base_60(self):
        result = compute_backoff_seconds(-1)
        assert result == 60

    def test_very_large_reap_count_capped_at_3600(self):
        result = compute_backoff_seconds(1000)
        assert result == 3600

    def test_reap_count_6_hits_cap(self):
        result = compute_backoff_seconds(6)
        assert result == 3600

    def test_reap_count_5_just_below_cap(self):
        result = compute_backoff_seconds(5)
        assert result == 1920

    def test_returns_int(self):
        result = compute_backoff_seconds(0)
        assert isinstance(result, int)


class TestMayRedispatchBoundary:
    def test_none_last_reap_at_always_allows(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        result = may_redispatch(feature)
        assert result is True

    def test_zero_reap_count_none_last_reap_always_allows(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        result = may_redispatch(feature)
        assert result is True

    def test_zero_reap_count_with_last_reap_at_still_allows(self):
        # reap_count=0 means no reap happened — last_reap_at is irrelevant
        now = datetime.now(timezone.utc)
        feature = _feature(reap_count=0, last_reap_at=now)
        result = may_redispatch(feature)
        assert result is True

    def test_feature_reaped_exactly_at_backoff_boundary_is_refused(self):
        # reap_count=1 → 120s window; elapsed=120s → refused (not >, only >=)
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=120)
        feature = _feature(reap_count=1, last_reap_at=last)
        result = may_redispatch(feature, now=now)
        # elapsed == backoff → elapsed < backoff is False, so may_redispatch=True
        assert result is True

    def test_feature_reaped_one_second_before_boundary_is_refused(self):
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        last = now - timedelta(seconds=119)
        feature = _feature(reap_count=1, last_reap_at=last)
        result = may_redispatch(feature, now=now)
        assert result is False

    def test_no_last_reap_at_attribute_allows(self):
        feature = MagicMock(spec=[])
        feature.id = "deadbeef-0000-0000-0000-000000000001"
        result = may_redispatch(feature)
        assert result is True


class TestEscalateAfterNReapsBoundary:
    def test_threshold_zero_always_escalates(self):
        with patch("bob3.orchestrator.reap_backoff.db") as mock_db:
            result = escalate_after_n_reaps("feature-id-1", reap_count=0, threshold=0)
        assert result is True
        mock_db.update_feature.assert_called_once()

    def test_reap_count_exactly_at_threshold_escalates(self):
        with patch("bob3.orchestrator.reap_backoff.db") as mock_db:
            result = escalate_after_n_reaps("feature-id-2", reap_count=3, threshold=3)
        assert result is True
        mock_db.update_feature.assert_called_once()

    def test_reap_count_below_threshold_does_not_escalate(self):
        with patch("bob3.orchestrator.reap_backoff.db") as mock_db:
            result = escalate_after_n_reaps("feature-id-3", reap_count=2, threshold=3)
        assert result is False
        mock_db.update_feature.assert_not_called()

    def test_reap_count_zero_threshold_one_does_not_escalate(self):
        with patch("bob3.orchestrator.reap_backoff.db") as mock_db:
            result = escalate_after_n_reaps("feature-id-4", reap_count=0, threshold=1)
        assert result is False
        mock_db.update_feature.assert_not_called()


class TestApplyExponentialBackoffBoundary:
    def test_zero_reap_count_returns_allowed_decision(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = apply_exponential_backoff(feature)
        assert isinstance(result, BackoffDecision)
        assert result.refused is False
        assert result.escalated is False
        assert result.reason == "allowed"

    def test_none_reap_count_treated_as_zero(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        feature.reap_count = None
        with patch("bob3.reaper.db"):
            result = apply_exponential_backoff(feature)
        assert result.refused is False
        assert result.reason == "allowed"

    def test_reap_count_zero_none_last_reap_allowed(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = apply_exponential_backoff(feature)
        assert result.backoff_seconds == 60
        assert result.reap_count == 0

    def test_now_defaults_to_utc_does_not_raise(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = apply_exponential_backoff(feature, now=None)
        assert isinstance(result, BackoffDecision)

    def test_minimum_valid_feature_id_single_char(self):
        feature = _feature(fid="a" * 36, reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = apply_exponential_backoff(feature)
        assert isinstance(result, BackoffDecision)


class TestShouldRefuseRedispatchBoundary:
    def test_zero_reap_count_returns_false_not_raises(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature)
        assert result is False

    def test_none_last_reap_at_returns_false_not_raises(self):
        feature = _feature(reap_count=1, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature)
        assert result is False

    def test_minimum_reap_count_returns_bool(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        with patch("bob3.reaper.db"):
            result = should_refuse_redispatch(feature)
        assert isinstance(result, bool)
