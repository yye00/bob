"""Tests: classify_attempts returns feature_defect when there is evidence of real work."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from bob.orchestrator.rca_infra_recovery import classify_attempts


class TestClassifyAttemptsWithRealWorkIsFeatureDefect(unittest.TestCase):
    """When real work events exist and stderr shows no infra patterns → feature_defect."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self.tmp.name)
        self.agent_logs_dir = self.tmpdir / ".bob" / "agent_logs"
        self.agent_logs_dir.mkdir(parents=True)
        self.progress_dir = self.tmpdir / ".bob"
        self.progress_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_progress(self, events: list[dict]) -> None:
        (self.progress_dir / "progress.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

    def _write_stderr_log(self, fid: str, idx: int, content: str) -> None:
        p = self.agent_logs_dir / f"20260101T0000{idx:02d}_{fid[:8]}_implement.stderr.log"
        p.write_text(content)

    def test_tool_use_event_in_progress_marks_real_work(self):
        """A 'tool_use' event in progress.jsonl means real work happened."""
        fid = "feat-real-work-001"
        self._write_progress([
            {"type": "session_start"},
            {"type": "tool_use", "tool": "Read", "input": {"file_path": "src/main.py"}},
        ])
        self._write_stderr_log(fid, 0, "AssertionError: expected 42 got 0\nTraceback (most recent call last):")

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        self.assertEqual(verdict, "feature_defect")

    def test_tool_result_event_in_progress_marks_real_work(self):
        """A 'tool_result' event means a tool completed — real work."""
        fid = "feat-real-work-002"
        self._write_progress([
            {"type": "tool_use", "tool": "Bash"},
            {"type": "tool_result", "content": "test output"},
        ])
        self._write_stderr_log(fid, 0, "TypeError: unsupported operand type(s) for +: 'int' and 'str'")

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        self.assertEqual(verdict, "feature_defect")

    def test_progress_updated_event_marks_real_work(self):
        """A 'progress_updated' event means real work was done."""
        fid = "feat-real-work-003"
        self._write_progress([
            {"type": "progress_updated", "step": 1, "total": 3},
        ])
        self._write_stderr_log(fid, 0, "ImportError: cannot import name 'foo' from 'bar'")

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        self.assertEqual(verdict, "feature_defect")

    def test_non_infra_stderr_with_real_work_is_feature_defect(self):
        """Real work + non-infra error = feature_defect regardless of stderr length."""
        fid = "feat-real-work-004"
        self._write_progress([
            {"type": "tool_use", "tool": "Write"},
            {"type": "tool_result", "content": "Written"},
            {"type": "tool_use", "tool": "Bash", "command": "pytest"},
            {"type": "tool_result", "content": "5 failed, 10 passed"},
        ])
        self._write_stderr_log(
            fid, 0,
            "FAILED tests/test_foo.py::test_bar - AssertionError: assert 1 == 2\n"
            "FAILED tests/test_foo.py::test_baz - ValueError: invalid value\n"
        )

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        self.assertEqual(verdict, "feature_defect")
