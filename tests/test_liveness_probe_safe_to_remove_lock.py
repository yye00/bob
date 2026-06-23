"""Tests: safe_to_remove_lock returns False while any signal still indicates liveness.

Acceptance criterion:
    pytest: tests/test_liveness_probe_safe_to_remove_lock.py asserts
    safe_to_remove_lock returns False while any signal still indicates
    liveness (safety boundary).
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch, MagicMock

import pytest

from bob3.orchestrator.liveness_probe import safe_to_remove_lock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_all_dead(db_path: str | None = None):
    """Return a context-manager stack that makes ALL signals dead."""
    return [
        patch("bob3.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe._has_recent_executing_rows", return_value=False),
    ]


# ---------------------------------------------------------------------------
# Tests: safety boundary — any ONE signal alive → False
# ---------------------------------------------------------------------------

def test_safe_to_remove_lock_false_when_orchestrator_alive(tmp_path):
    """safe_to_remove_lock returns False when is_orchestrator_alive is True."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("99999\n")
    with (
        patch("bob3.orchestrator.liveness_probe.is_orchestrator_alive", return_value=True),
        patch("bob3.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe._has_recent_executing_rows", return_value=False),
    ):
        assert safe_to_remove_lock(lock_file) is False


def test_safe_to_remove_lock_false_when_lock_pid_alive(tmp_path):
    """safe_to_remove_lock returns False when lock_holder_pid_alive is True."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("99999\n")
    with (
        patch("bob3.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=True),
        patch("bob3.orchestrator.liveness_probe._has_recent_executing_rows", return_value=False),
    ):
        assert safe_to_remove_lock(lock_file) is False


def test_safe_to_remove_lock_false_when_executing_rows_recent(tmp_path):
    """safe_to_remove_lock returns False when DB has recent executing rows."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("99999\n")
    with (
        patch("bob3.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe._has_recent_executing_rows", return_value=True),
    ):
        assert safe_to_remove_lock(lock_file) is False


def test_safe_to_remove_lock_true_only_when_all_signals_dead(tmp_path):
    """safe_to_remove_lock returns True ONLY when all three signals are dead."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("99999\n")
    with (
        patch("bob3.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe._has_recent_executing_rows", return_value=False),
    ):
        assert safe_to_remove_lock(lock_file) is True


def test_safe_to_remove_lock_false_all_three_alive(tmp_path):
    """safe_to_remove_lock returns False when all signals indicate alive."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("99999\n")
    with (
        patch("bob3.orchestrator.liveness_probe.is_orchestrator_alive", return_value=True),
        patch("bob3.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=True),
        patch("bob3.orchestrator.liveness_probe._has_recent_executing_rows", return_value=True),
    ):
        assert safe_to_remove_lock(lock_file) is False


def test_safe_to_remove_lock_two_of_three_alive(tmp_path):
    """safe_to_remove_lock is False when only 2 of 3 signals show dead."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("99999\n")
    with (
        patch("bob3.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=True),
        patch("bob3.orchestrator.liveness_probe._has_recent_executing_rows", return_value=True),
    ):
        assert safe_to_remove_lock(lock_file) is False


def test_safe_to_remove_lock_accepts_string_path(tmp_path):
    """safe_to_remove_lock accepts str lock_path."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("99999\n")
    with (
        patch("bob3.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe._has_recent_executing_rows", return_value=False),
    ):
        assert safe_to_remove_lock(str(lock_file)) is True


def test_safe_to_remove_lock_absent_lock_file_still_checks_all_signals(tmp_path):
    """safe_to_remove_lock checks all signals even when lock file is absent."""
    lock_file = tmp_path / ".bob3.lock"
    # No file created — lock_holder_pid_alive will return False
    with (
        patch("bob3.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe._has_recent_executing_rows", return_value=False),
    ):
        assert safe_to_remove_lock(lock_file) is True


def test_safe_to_remove_lock_db_error_is_conservative(tmp_path):
    """safe_to_remove_lock returns False (conservative) on DB errors."""
    lock_file = tmp_path / ".bob3.lock"
    lock_file.write_text("99999\n")
    with (
        patch("bob3.orchestrator.liveness_probe.is_orchestrator_alive", return_value=False),
        patch("bob3.orchestrator.liveness_probe.lock_holder_pid_alive", return_value=False),
        patch(
            "bob3.orchestrator.liveness_probe._has_recent_executing_rows",
            side_effect=Exception("DB error"),
        ),
    ):
        assert safe_to_remove_lock(lock_file) is False
