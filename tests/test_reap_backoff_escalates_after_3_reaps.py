"""Tests that escalate_after_n_reaps transitions feature to needs_human."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from bob.orchestrator.reap_backoff import escalate_after_n_reaps


class TestEscalateAfterNReaps:
    def test_no_escalation_below_threshold(self):
        result = escalate_after_n_reaps("feat-id-1", reap_count=2, threshold=3)
        assert result is False

    def test_no_escalation_at_zero(self):
        result = escalate_after_n_reaps("feat-id-2", reap_count=0, threshold=3)
        assert result is False

    def test_escalates_at_threshold(self):
        with patch("bob.db.update_feature") as mock_update:
            result = escalate_after_n_reaps("feat-abc", reap_count=3, threshold=3)

        assert result is True
        mock_update.assert_called_once_with(
            "feat-abc",
            status="needs_human",
            last_improvement_type="repeated_reap_cycle",
        )

    def test_escalates_above_threshold(self):
        with patch("bob.db.update_feature") as mock_update:
            result = escalate_after_n_reaps("feat-xyz", reap_count=5, threshold=3)

        assert result is True
        mock_update.assert_called_once()

    def test_custom_threshold_2(self):
        with patch("bob.db.update_feature") as mock_update:
            result = escalate_after_n_reaps("feat-t2", reap_count=2, threshold=2)

        assert result is True

    def test_custom_threshold_1_no_escalation_at_zero(self):
        result = escalate_after_n_reaps("feat-t1", reap_count=0, threshold=1)
        assert result is False

    def test_custom_threshold_1_escalates_at_one(self):
        with patch("bob.db.update_feature") as mock_update:
            result = escalate_after_n_reaps("feat-t1b", reap_count=1, threshold=1)

        assert result is True

    def test_sets_status_needs_human(self):
        with patch("bob.db.update_feature") as mock_update:
            escalate_after_n_reaps("feat-nh", reap_count=3)

        call_kwargs = mock_update.call_args
        assert call_kwargs.kwargs.get("status") == "needs_human"

    def test_sets_last_improvement_type_repeated_reap_cycle(self):
        with patch("bob.db.update_feature") as mock_update:
            escalate_after_n_reaps("feat-lrc", reap_count=3)

        call_kwargs = mock_update.call_args
        assert call_kwargs.kwargs.get("last_improvement_type") == "repeated_reap_cycle"
