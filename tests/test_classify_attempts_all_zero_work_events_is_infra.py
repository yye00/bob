"""Tests: classify_attempts returns infra_only when all failures show no work events.

Heuristic: if no real work events in progress.jsonl + stderrs match infra patterns
→ 2/4 heuristics → infra_only verdict.
"""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from bob.orchestrator.rca_infra_recovery import classify_attempts


class TestClassifyAttemptsAllZeroWorkEventsIsInfra(unittest.TestCase):
    """Classify_attempts returns infra_only when there are no work events."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self.tmp.name)
        self.agent_logs_dir = self.tmpdir / ".bob" / "agent_logs"
        self.agent_logs_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_stderr_log(self, name: str, content: str) -> pathlib.Path:
        p = self.agent_logs_dir / name
        p.write_text(content)
        return p

    def test_no_work_events_with_infra_stderr_is_infra_only(self):
        """No progress.jsonl + infra stderr → infra_only."""
        fid = "feat-zero-work-001"
        self._write_stderr_log(
            f"20260101T000000_{fid[:8]}_implement.stderr.log",
            "Error: ECONNRESET connection reset by peer\nretrying...",
        )
        self._write_stderr_log(
            f"20260101T000100_{fid[:8]}_implement.stderr.log",
            "Error: ETIMEDOUT connection timed out\ngiving up",
        )

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
        ):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        self.assertEqual(verdict, "infra_only")

    def test_empty_progress_no_stderr_matches_infra_heuristic(self):
        """Empty progress.jsonl (no work events) contributes h2 heuristic."""
        fid = "feat-zero-work-002"
        # Write empty progress.jsonl
        progress_dir = self.tmpdir / ".bob"
        progress_dir.mkdir(parents=True, exist_ok=True)
        (progress_dir / "progress.jsonl").write_text("")

        self._write_stderr_log(
            f"20260101T000000_{fid[:8]}_implement.stderr.log",
            "self signed certificate in certificate chain\nAPI call failed",
        )

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
        ):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        self.assertEqual(verdict, "infra_only")

    def test_no_tool_use_events_in_progress_is_no_work(self):
        """Progress.jsonl with only non-work events → no work events detected."""
        fid = "feat-zero-work-003"
        progress_dir = self.tmpdir / ".bob"
        progress_dir.mkdir(parents=True, exist_ok=True)
        # Write non-work events only
        events = [
            {"type": "session_start", "ts": "2026-01-01T00:00:00Z"},
            {"type": "feature_claimed", "ts": "2026-01-01T00:00:01Z"},
        ]
        (progress_dir / "progress.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        self._write_stderr_log(
            f"20260101T000000_{fid[:8]}_implement.stderr.log",
            "rate_limit_error: You have exceeded your rate limit",
        )

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
        ):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        self.assertEqual(verdict, "infra_only")

    def test_multiple_infra_stderrs_no_work_returns_infra_only(self):
        """Multiple infra-pattern stderrs with no work → definitely infra_only."""
        fid = "feat-zero-work-004"
        infra_errors = [
            "overloaded_error: The server is currently overloaded",
            "APIStatusError 529: Server overloaded",
            "getaddrinfo ENOTFOUND api.anthropic.com",
        ]
        for i, err in enumerate(infra_errors):
            self._write_stderr_log(
                f"20260101T0000{i:02d}_{fid[:8]}_implement.stderr.log",
                err,
            )

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
        ):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        self.assertEqual(verdict, "infra_only")
