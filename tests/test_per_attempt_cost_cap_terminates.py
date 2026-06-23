"""Tests for terminate_subagent_on_cost_cap (27eaa1de).

AC assertion:
- subagent is SIGTERM'd when reported_cost > cap.
- SIGKILL is sent when process does not exit within grace period.
- Audit log sentinel is written.
- Refinement attempt is charged (no free retry).
- Safety: own PID and PID ≤ 1 are never signalled.
"""

from __future__ import annotations

import os
import signal
from unittest.mock import MagicMock, call, patch

import pytest

from bob3.orchestrator.per_attempt_cost_cap import terminate_subagent_on_cost_cap


class TestTerminateOnCostCapSIGTERM:
    """AC: subagent receives SIGTERM when reported_cost > cap."""

    def test_sigterm_sent_to_pid(self, monkeypatch):
        """Confirmed SIGTERM is sent to the subagent PID."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        target_pid = 99999  # unlikely to be a real process

        signals_sent = []

        def fake_send_signal(pid, sig):
            signals_sent.append((pid, sig))

        def fake_wait_for_exit(pid, timeout_s):
            return True  # process exits cleanly after SIGTERM

        with (
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._send_signal",
                side_effect=fake_send_signal,
            ),
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._wait_for_exit",
                side_effect=fake_wait_for_exit,
            ),
            patch("bob3.orchestrator.per_attempt_cost_cap.db") as mock_db,
        ):
            mock_db.increment_refinement_attempts.return_value = None
            terminate_subagent_on_cost_cap(
                feature_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                pid=target_pid,
                reported_cost=15.0,
            )

        assert len(signals_sent) >= 1, "At least one signal must have been sent"
        first_signal = signals_sent[0]
        assert first_signal[0] == target_pid
        assert first_signal[1] == signal.SIGTERM

    def test_sigkill_sent_when_process_does_not_exit(self, monkeypatch):
        """SIGKILL is sent when the process survives the SIGTERM grace window."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        target_pid = 99998
        signals_sent = []

        def fake_send_signal(pid, sig):
            signals_sent.append((pid, sig))

        def fake_wait_for_exit(pid, timeout_s):
            return False  # process does NOT exit — force SIGKILL path

        with (
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._send_signal",
                side_effect=fake_send_signal,
            ),
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._wait_for_exit",
                side_effect=fake_wait_for_exit,
            ),
            patch("bob3.orchestrator.per_attempt_cost_cap.db") as mock_db,
        ):
            mock_db.increment_refinement_attempts.return_value = None
            terminate_subagent_on_cost_cap(
                feature_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                pid=target_pid,
                reported_cost=15.0,
            )

        # Expect SIGTERM then SIGKILL
        sigs = [s[1] for s in signals_sent if s[0] == target_pid]
        assert signal.SIGTERM in sigs, "SIGTERM must be sent first"
        assert signal.SIGKILL in sigs, "SIGKILL must be sent when process survives grace period"
        term_idx = sigs.index(signal.SIGTERM)
        kill_idx = sigs.index(signal.SIGKILL)
        assert term_idx < kill_idx, "SIGTERM must precede SIGKILL"

    def test_no_sigkill_when_process_exits_cleanly(self, monkeypatch):
        """When process exits after SIGTERM, SIGKILL is NOT sent."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        target_pid = 99997
        signals_sent = []

        def fake_send_signal(pid, sig):
            signals_sent.append((pid, sig))

        def fake_wait_for_exit(pid, timeout_s):
            return True  # process exits cleanly

        with (
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._send_signal",
                side_effect=fake_send_signal,
            ),
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._wait_for_exit",
                side_effect=fake_wait_for_exit,
            ),
            patch("bob3.orchestrator.per_attempt_cost_cap.db") as mock_db,
        ):
            mock_db.increment_refinement_attempts.return_value = None
            terminate_subagent_on_cost_cap(
                feature_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                pid=target_pid,
                reported_cost=15.0,
            )

        sigs = [s[1] for s in signals_sent if s[0] == target_pid]
        assert signal.SIGKILL not in sigs, "SIGKILL must NOT be sent when process exits cleanly"


class TestTerminateOnCostCapAuditLog:
    """AC: sentinel is appended to feature audit log."""

    def test_sentinel_written_to_audit_log(self, monkeypatch):
        """db.create_evidence called with sentinel string."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        feature_id = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
        target_pid = 88888

        with (
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._send_signal",
            ),
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._wait_for_exit",
                return_value=True,
            ),
            patch("bob3.orchestrator.per_attempt_cost_cap.db") as mock_db,
        ):
            mock_db.increment_refinement_attempts.return_value = None
            terminate_subagent_on_cost_cap(
                feature_id=feature_id,
                pid=target_pid,
                reported_cost=25.0,
            )

        assert mock_db.create_evidence.called, "db.create_evidence must be called"
        call_kwargs = mock_db.create_evidence.call_args
        # Check that sentinel contains feature_id
        content_str = str(call_kwargs)
        assert feature_id in content_str or "attempt_cost_cap_kill" in content_str


class TestTerminateOnCostCapChargesAttempt:
    """AC: refinement attempt is charged (F-R7-561 lossless-cost)."""

    def test_increment_refinement_attempts_called(self, monkeypatch):
        """db.increment_refinement_attempts must be called for the feature."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        feature_id = "cccccccc-dddd-eeee-ffff-000000000000"
        target_pid = 77777

        with (
            patch("bob3.orchestrator.per_attempt_cost_cap._send_signal"),
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._wait_for_exit",
                return_value=True,
            ),
            patch("bob3.orchestrator.per_attempt_cost_cap.db") as mock_db,
        ):
            mock_db.increment_refinement_attempts.return_value = None
            terminate_subagent_on_cost_cap(
                feature_id=feature_id,
                pid=target_pid,
                reported_cost=12.0,
            )

        mock_db.increment_refinement_attempts.assert_called_once_with(feature_id)


class TestTerminateOnCostCapSafetyGuards:
    """Safety: own PID and system PIDs must never be signalled."""

    def test_own_pid_never_signalled(self, monkeypatch):
        """terminate_subagent_on_cost_cap refuses to signal os.getpid()."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with (
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._send_signal",
            ) as mock_send,
            patch("bob3.orchestrator.per_attempt_cost_cap.db"),
        ):
            terminate_subagent_on_cost_cap(
                feature_id="dddddddd-eeee-ffff-0000-111111111111",
                pid=os.getpid(),
                reported_cost=50.0,
            )

        mock_send.assert_not_called(), "own PID must NEVER be signalled"

    def test_pid_1_never_signalled(self, monkeypatch):
        """terminate_subagent_on_cost_cap refuses to signal PID 1 (init)."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with (
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._send_signal",
            ) as mock_send,
            patch("bob3.orchestrator.per_attempt_cost_cap.db"),
        ):
            terminate_subagent_on_cost_cap(
                feature_id="eeeeeeee-ffff-0000-1111-222222222222",
                pid=1,
                reported_cost=50.0,
            )

        mock_send.assert_not_called(), "PID 1 must NEVER be signalled"

    def test_pid_0_never_signalled(self, monkeypatch):
        """PID 0 (kernel) is guarded by pid <= 1 check."""
        monkeypatch.delenv("BOB3_PER_ATTEMPT_COST_CAP", raising=False)

        with (
            patch(
                "bob3.orchestrator.per_attempt_cost_cap._send_signal",
            ) as mock_send,
            patch("bob3.orchestrator.per_attempt_cost_cap.db"),
        ):
            terminate_subagent_on_cost_cap(
                feature_id="ffffffff-0000-1111-2222-333333333333",
                pid=0,
                reported_cost=50.0,
            )

        mock_send.assert_not_called(), "PID 0 must NEVER be signalled"
