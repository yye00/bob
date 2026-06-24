"""Tests: is_orchestrator_alive returns True for bob[0-9]+ run processes.

Acceptance criterion:
    pytest: tests/test_liveness_probe_regex_matches_bobN.py asserts
    is_orchestrator_alive returns True for a fixture process argv
    containing 'bob14 run --all'
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from bob.orchestrator.liveness_probe import is_orchestrator_alive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_process_list(cmdlines: list[str]) -> list[tuple[int, str]]:
    """Return fake (pid, cmdline) tuples for testing."""
    return [(999_000 + i, cmd) for i, cmd in enumerate(cmdlines)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_is_orchestrator_alive_matches_bob14_run_all():
    """is_orchestrator_alive returns True when a process has 'bob14 run --all' argv."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=_fake_process_list(["bob14 run --all"]),
    ):
        assert is_orchestrator_alive() is True


def test_is_orchestrator_alive_matches_bob_run():
    """is_orchestrator_alive returns True for legacy 'bob run' process."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=_fake_process_list(["bob run --all"]),
    ):
        assert is_orchestrator_alive() is True


def test_is_orchestrator_alive_matches_any_gen_number():
    """is_orchestrator_alive matches bob[0-9]+ pattern (bob1 through bob99+)."""
    for gen in [1, 2, 5, 10, 14, 15, 99, 100]:
        cmdline = f"bob{gen} run --feature abc"
        with patch(
            "bob.orchestrator.liveness_probe._iter_candidate_pids",
            return_value=_fake_process_list([cmdline]),
        ):
            assert is_orchestrator_alive() is True, f"Expected True for cmdline: {cmdline!r}"


def test_is_orchestrator_alive_false_when_no_matching_process():
    """is_orchestrator_alive returns False when no bob[0-9]+ run processes exist."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=_fake_process_list(["python some_script.py", "claude --help"]),
    ):
        assert is_orchestrator_alive() is False


def test_is_orchestrator_alive_false_when_process_list_empty():
    """is_orchestrator_alive returns False on empty process list."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=[],
    ):
        assert is_orchestrator_alive() is False


def test_is_orchestrator_alive_does_not_match_bob_without_run():
    """'bob14 status' does not count as a running orchestrator."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=_fake_process_list(["bob14 status", "bob plan --create"]),
    ):
        assert is_orchestrator_alive() is False


def test_is_orchestrator_alive_does_not_match_just_bob():
    """A process named just 'bob' without a number doesn't match bob[0-9]+."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=_fake_process_list(["bob run --all"]),
    ):
        assert is_orchestrator_alive() is False


def test_is_orchestrator_alive_excludes_own_pid():
    """is_orchestrator_alive never matches its own process."""
    own_pid = os.getpid()
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=[(own_pid, "bob14 run --all")],
    ):
        # Own PID should be excluded even if cmdline matches
        assert is_orchestrator_alive() is False


def test_is_orchestrator_alive_matches_bob_run_variant():
    """'bob run' (without gen suffix) also triggers is_orchestrator_alive=True."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=_fake_process_list(["/usr/local/bin/bob run --all --fresh"]),
    ):
        assert is_orchestrator_alive() is True


def test_is_orchestrator_alive_full_path_works():
    """Full-path binary like '/home/user/.venv/bin/bob14 run' matches."""
    with patch(
        "bob.orchestrator.liveness_probe._iter_candidate_pids",
        return_value=_fake_process_list(["/home/user/.venv/bin/bob14 run --all"]),
    ):
        assert is_orchestrator_alive() is True
