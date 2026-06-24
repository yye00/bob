"""Tests that enforce_time_limit kills processes exceeding time_limit_sec — AC-19."""

from __future__ import annotations

import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from bob.verification.mutation_gate import (
    MutationReport,
    enforce_time_limit,
    run_mutation_test,
)


class TestEnforceTimeLimit:
    def test_does_not_kill_fast_process(self, tmp_path):
        # A process that exits immediately should not be killed
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.exit(0)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.wait()
        killed = enforce_time_limit(proc, time_limit_sec=10)
        assert killed is False

    def test_returns_false_for_already_finished_process(self, tmp_path):
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.wait()  # ensure it's done
        result = enforce_time_limit(proc, time_limit_sec=5)
        assert result is False

    def test_kills_long_running_process(self):
        # A process that sleeps for 30s should be killed after 0.5s limit
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        start = time.monotonic()
        killed = enforce_time_limit(proc, time_limit_sec=0.5)
        elapsed = time.monotonic() - start
        assert killed is True
        assert proc.poll() is not None  # process terminated
        assert elapsed < 5  # should not take long

    def test_returns_bool(self, tmp_path):
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.wait()
        result = enforce_time_limit(proc, time_limit_sec=1)
        assert isinstance(result, bool)


class TestRunMutationTestRespectsTimeLimit:
    def test_partial_report_when_timed_out(self, tmp_path):
        # Simulate mutmut taking too long by having the proc take forever
        # and watcher killing it after the limit
        with patch("bob.verification.mutation_gate.subprocess.Popen") as mock_popen, \
             patch("bob.verification.mutation_gate._parse_mutmut_results") as mock_parse, \
             patch("bob.verification.mutation_gate._collect_surviving_diffs") as mock_diffs, \
             patch("bob.verification.mutation_gate.enforce_time_limit") as mock_enforce:
            proc = MagicMock()
            proc.communicate.return_value = (b"", b"")
            proc.poll.return_value = None
            mock_popen.return_value = proc
            # Simulate the watcher killing the process
            mock_enforce.return_value = True
            mock_parse.return_value = {"total": 20, "killed": 10, "survived": 5, "timeout": 5}
            mock_diffs.return_value = []

            report = run_mutation_test(
                feature_id="feat-timeout",
                src_files=["src/x.py"],
                test_dir=tmp_path,
                workspace=tmp_path,
                time_limit_sec=180,
            )

        assert report.timed_out_early is True
        assert report.partial is True

    def test_non_partial_report_when_completed_in_time(self, tmp_path):
        with patch("bob.verification.mutation_gate.subprocess.Popen") as mock_popen, \
             patch("bob.verification.mutation_gate._parse_mutmut_results") as mock_parse, \
             patch("bob.verification.mutation_gate._collect_surviving_diffs") as mock_diffs, \
             patch("bob.verification.mutation_gate.enforce_time_limit") as mock_enforce:
            proc = MagicMock()
            proc.communicate.return_value = (b"", b"")
            proc.poll.return_value = 0
            mock_popen.return_value = proc
            mock_enforce.return_value = False  # not killed
            mock_parse.return_value = {"total": 10, "killed": 9, "survived": 1, "timeout": 0}
            mock_diffs.return_value = []

            report = run_mutation_test(
                feature_id="feat-ok",
                src_files=["src/x.py"],
                test_dir=tmp_path,
                workspace=tmp_path,
                time_limit_sec=180,
            )

        assert report.timed_out_early is False
        assert report.partial is False
