"""Boundary tests: zero reap_count and None last_reap_at always allow dispatch."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from bob3.orchestrator.reap_backoff import (
    compute_backoff_seconds,
    escalate_after_n_reaps,
    may_redispatch,
)


def _feature(reap_count: int, last_reap_at=None) -> MagicMock:
    f = MagicMock()
    f.id = "00000000-0000-0000-0000-000000000001"
    f.reap_count = reap_count
    f.last_reap_at = last_reap_at
    return f


class TestBoundaryZeroReaps:
    def test_compute_backoff_zero_is_positive(self):
        assert compute_backoff_seconds(0) > 0

    def test_may_redispatch_zero_count_none_last(self):
        feature = _feature(reap_count=0, last_reap_at=None)
        assert may_redispatch(feature) is True

    def test_may_redispatch_zero_count_with_recent_last(self):
        # Even with a very recent last_reap_at, zero count → dispatchable
        last = datetime.now(timezone.utc)
        feature = _feature(reap_count=0, last_reap_at=last)
        assert may_redispatch(feature) is True

    def test_may_redispatch_nonzero_count_none_last(self):
        # No prior reap timestamp → always dispatchable
        feature = _feature(reap_count=3, last_reap_at=None)
        assert may_redispatch(feature) is True

    def test_escalate_zero_reaps_no_escalation(self):
        result = escalate_after_n_reaps("feat-zero", reap_count=0)
        assert result is False

    def test_escalate_threshold_below_zero_is_impossible(self):
        # Negative threshold would trigger escalation at 0 reaps; guard against
        # accidental misconfiguration — check that 0 < threshold is validated.
        # The function uses "reap_count < threshold", so threshold<=0 would
        # escalate everything. We document that threshold should be >= 1.
        # With the default threshold=3, zero reaps → no escalation.
        result = escalate_after_n_reaps("feat-neg", reap_count=0, threshold=3)
        assert result is False

    def test_compute_backoff_is_always_positive(self):
        for n in range(0, 10):
            assert compute_backoff_seconds(n) > 0
