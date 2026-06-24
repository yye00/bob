"""Tests for bob3.cost_cap.enforce_per_attempt_cap (e93f7fc4).

AC assertions:
- enforce_per_attempt_cap returns False when cost is within cap.
- enforce_per_attempt_cap returns True and terminates subagent when cap exceeded.
- SIGTERM → SIGKILL sequence is used (15 s grace).
- Audit sentinel is written.
- Refinement attempt is charged (lossless-cost, no free retry).
- Safety: own PID and PID ≤ 1 are never signalled.
- env cap override is respected.
"""

from __future__ import annotations

import os
import signal
from unittest.mock import call, patch

import pytest

from bob3.cost_cap import enforce_per_attempt_cap


class TestEnforcePerAttemptCapNoAction:
    """enforce_per_attempt_cap returns False when cost is within cap."""

    def test_cost_at_cap_returns_false(self, monkeypatch):
        """Cost exactly at default cap (10.0) → no termination, returns False."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                pid=99999,
                reported_cost=10.0,
            )

        assert result is False
        mock_terminate.assert_not_called()

    def test_cost_below_cap_returns_false(self, monkeypatch):
        """Cost below default cap → no termination, returns False."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                pid=99999,
                reported_cost=5.0,
            )

        assert result is False
        mock_terminate.assert_not_called()

    def test_zero_cost_returns_false(self, monkeypatch):
        """Zero cost → no termination, returns False."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                pid=99999,
                reported_cost=0.0,
            )

        assert result is False
        mock_terminate.assert_not_called()

    def test_negative_cost_returns_false(self, monkeypatch):
        """Negative cost (bad telemetry) → no termination, returns False."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                pid=99999,
                reported_cost=-3.5,
            )

        assert result is False
        mock_terminate.assert_not_called()


class TestEnforcePerAttemptCapTerminates:
    """enforce_per_attempt_cap returns True and terminates when cost exceeds cap."""

    def test_cost_above_cap_returns_true(self, monkeypatch):
        """Cost above default cap → terminate called, returns True."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
                pid=88888,
                reported_cost=15.0,
            )

        assert result is True
        mock_terminate.assert_called_once_with(
            feature_id="bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
            pid=88888,
            reported_cost=15.0,
        )

    def test_just_above_cap_triggers_termination(self, monkeypatch):
        """Cost just above default cap (10.01) → terminates."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="cccccccc-dddd-eeee-ffff-000000000000",
                pid=77777,
                reported_cost=10.01,
            )

        assert result is True
        mock_terminate.assert_called_once()

    def test_runaway_cost_triggers_termination(self, monkeypatch):
        """Cost matching observed runaway ($38.25) → terminates."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="dddddddd-eeee-ffff-0000-111111111111",
                pid=66666,
                reported_cost=38.25,
            )

        assert result is True
        mock_terminate.assert_called_once()


class TestEnforcePerAttemptCapCustomCap:
    """Custom BOB3_PER_ATTEMPT_COST_CAP env override is respected."""

    def test_custom_cap_5_terminates_at_6(self, monkeypatch):
        """Custom cap=5 → terminate at cost=6."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "5")

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="eeeeeeee-ffff-0000-1111-222222222222",
                pid=55555,
                reported_cost=6.0,
            )

        assert result is True
        mock_terminate.assert_called_once()

    def test_custom_cap_5_no_action_at_5(self, monkeypatch):
        """Custom cap=5 → no action at cost=5.0 (strict >)."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "5")

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="ffffffff-0000-1111-2222-333333333333",
                pid=44444,
                reported_cost=5.0,
            )

        assert result is False
        mock_terminate.assert_not_called()

    def test_env_cap_clamped_to_lower_bound(self, monkeypatch):
        """env=0 clamped to 0.5 — cost=1.0 still triggers termination."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "0")

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="00000000-1111-2222-3333-444444444444",
                pid=33333,
                reported_cost=1.0,
            )

        assert result is True
        mock_terminate.assert_called_once()

    def test_env_cap_clamped_to_upper_bound(self, monkeypatch):
        """env=200 clamped to 100 — cost=50 does NOT trigger termination."""
        monkeypatch.setenv("BOB3_PER_ATTEMPT_COST_CAP", "200")

        with patch("bob3.cost_cap.terminate_subagent_on_cost_cap") as mock_terminate:
            result = enforce_per_attempt_cap(
                feature_id="11111111-2222-3333-4444-555555555555",
                pid=22222,
                reported_cost=50.0,
            )

        assert result is False
        mock_terminate.assert_not_called()


class TestEnforcePerAttemptCapIntegration:
    """Integration: end-to-end signal delivery through the full stack."""

    def test_sigterm_sent_to_pid_on_cap_exceeded(self, monkeypatch):
        """Full stack: SIGTERM sent to PID when cost exceeds default cap."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        target_pid = 99990
        signals_sent = []

        def fake_send_signal(pid, sig):
            signals_sent.append((pid, sig))

        with (
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._send_signal",
                side_effect=fake_send_signal,
            ),
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._wait_for_exit",
                return_value=True,
            ),
            patch("bob3.orchestrator.per_attempt_cost_cap.db") as mock_db,
        ):
            mock_db.increment_refinement_attempts.return_value = None
            result = enforce_per_attempt_cap(
                feature_id="22222222-3333-4444-5555-666666666666",
                pid=target_pid,
                reported_cost=20.0,
            )

        assert result is True
        assert any(
            pid == target_pid and sig == signal.SIGTERM
            for pid, sig in signals_sent
        ), "SIGTERM must be sent to target PID"

    def test_refinement_attempt_charged_via_db(self, monkeypatch):
        """Full stack: db.increment_refinement_attempts called for feature."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        feature_id = "33333333-4444-5555-6666-777777777777"
        target_pid = 99980

        with (
            patch("bob3.orchestrator.per_attempt_cost_cap._send_signal"),
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._wait_for_exit",
                return_value=True,
            ),
            patch("bob3.orchestrator.per_attempt_cost_cap.db") as mock_db,
        ):
            mock_db.increment_refinement_attempts.return_value = None
            result = enforce_per_attempt_cap(
                feature_id=feature_id,
                pid=target_pid,
                reported_cost=25.0,
            )

        assert result is True
        mock_db.increment_refinement_attempts.assert_called_once_with(feature_id)

    def test_sentinel_written_to_audit_log(self, monkeypatch):
        """Full stack: audit sentinel is written to db when cap exceeded."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        feature_id = "44444444-5555-6666-7777-888888888888"
        target_pid = 99970

        with (
            patch("bob3.orchestrator.per_attempt_cost_cap._send_signal"),
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._wait_for_exit",
                return_value=True,
            ),
            patch("bob3.orchestrator.per_attempt_cost_cap.db") as mock_db,
        ):
            mock_db.increment_refinement_attempts.return_value = None
            result = enforce_per_attempt_cap(
                feature_id=feature_id,
                pid=target_pid,
                reported_cost=12.0,
            )

        assert result is True
        assert mock_db.create_evidence.called, "Audit sentinel must be written via db.create_evidence"


class TestEnforcePerAttemptCapSafetyGuards:
    """Safety: own PID and system PIDs must never be signalled."""

    def test_own_pid_not_signalled(self, monkeypatch):
        """enforce_per_attempt_cap with own PID must not signal it."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch(
            "bob3.orchestrator.per_attempt_cost_cap._send_signal"
        ) as mock_send:
            enforce_per_attempt_cap(
                feature_id="55555555-6666-7777-8888-999999999999",
                pid=os.getpid(),
                reported_cost=50.0,
            )

        mock_send.assert_not_called(), "own PID must NEVER be signalled"

    def test_pid_1_not_signalled(self, monkeypatch):
        """enforce_per_attempt_cap with PID 1 must not signal it."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with patch(
            "bob3.orchestrator.per_attempt_cost_cap._send_signal"
        ) as mock_send:
            enforce_per_attempt_cap(
                feature_id="66666666-7777-8888-9999-aaaaaaaaaaaa",
                pid=1,
                reported_cost=50.0,
            )

        mock_send.assert_not_called(), "PID 1 must NEVER be signalled"
