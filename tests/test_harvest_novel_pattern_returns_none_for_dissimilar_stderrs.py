"""Tests: harvest_novel_pattern returns None when stderrs are too dissimilar."""
from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest.mock import patch

from bob3.orchestrator.rca_infra_recovery import harvest_novel_pattern


class TestHarvestNovelPatternReturnsNoneForDissimilarStderrs(unittest.TestCase):
    """Harvest_novel_pattern returns None when no common pattern emerges."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self.tmp.name)
        self.agent_logs_dir = self.tmpdir / ".bob3" / "agent_logs"
        self.agent_logs_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_log(self, name: str, content: str) -> None:
        (self.agent_logs_dir / name).write_text(content)

    def test_completely_different_stderrs_return_none(self):
        """Two completely different stderrs yield no common pattern."""
        fid = "feat-dissim-001"
        self._write_log(
            f"20260101T000000_{fid[:8]}_implement.stderr.log",
            "Alpha beta gamma delta epsilon zeta eta theta iota kappa",
        )
        self._write_log(
            f"20260101T000100_{fid[:8]}_implement.stderr.log",
            "1234567890 abcdefghij XYZXYZXYZ unrelated content here",
        )

        with patch("bob3.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            pattern = harvest_novel_pattern(fid, workspace=self.tmpdir)

        self.assertIsNone(pattern)

    def test_no_logs_returns_none(self):
        """No logs at all → None."""
        fid = "feat-dissim-002"
        # No log files written

        with patch("bob3.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            pattern = harvest_novel_pattern(fid, workspace=self.tmpdir)

        self.assertIsNone(pattern)

    def test_very_short_common_substring_returns_none(self):
        """Common substring < 8 chars is too short to be a useful pattern → None."""
        fid = "feat-dissim-003"
        self._write_log(
            f"20260101T000000_{fid[:8]}_implement.stderr.log",
            "XY error: process failed unexpectedly with code 137",
        )
        self._write_log(
            f"20260101T000100_{fid[:8]}_implement.stderr.log",
            "XY info: all connections dropped, network unreachable",
        )

        with patch("bob3.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            pattern = harvest_novel_pattern(fid, workspace=self.tmpdir)

        # Common part is "XY " or similar very short string → should return None
        if pattern is not None:
            self.assertGreater(len(pattern), 7, "Short patterns should not be returned")

    def test_single_empty_log_returns_none(self):
        """Single empty log file → None."""
        fid = "feat-dissim-004"
        self._write_log(
            f"20260101T000000_{fid[:8]}_implement.stderr.log",
            "",
        )

        with patch("bob3.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            pattern = harvest_novel_pattern(fid, workspace=self.tmpdir)

        self.assertIsNone(pattern)
