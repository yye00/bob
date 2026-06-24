"""Tests: harvest_novel_pattern extracts a regex from similar stderr tails via LCS."""
from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest.mock import patch

from bob.orchestrator.rca_infra_recovery import harvest_novel_pattern


class TestHarvestNovelPatternExtractsLCS(unittest.TestCase):
    """Harvest_novel_pattern returns a pattern from N similar stderr tails."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self.tmp.name)
        self.agent_logs_dir = self.tmpdir / ".bob" / "agent_logs"
        self.agent_logs_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_log(self, name: str, content: str) -> None:
        (self.agent_logs_dir / name).write_text(content)

    def test_two_similar_stderrs_produce_common_pattern(self):
        """Two stderrs sharing a long common substring → pattern extracted."""
        fid = "feat-lcs-001"
        self._write_log(
            f"20260101T000000_{fid[:8]}_implement.stderr.log",
            "Error: ENOENT: no such file or directory, open '/tmp/missing-socket.sock'\nprocess exited",
        )
        self._write_log(
            f"20260101T000100_{fid[:8]}_implement.stderr.log",
            "Error: ENOENT: no such file or directory, open '/tmp/missing-socket.sock'\ndifferent suffix",
        )

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            pattern = harvest_novel_pattern(fid, workspace=self.tmpdir)

        self.assertIsNotNone(pattern)
        assert pattern is not None
        self.assertGreater(len(pattern), 0)

    def test_extracted_pattern_is_valid_regex(self):
        """The extracted pattern must be a valid regex."""
        import re
        fid = "feat-lcs-002"
        common = "ENOENT: no such file or directory"
        for i in range(3):
            self._write_log(
                f"20260101T0000{i:02d}_{fid[:8]}_implement.stderr.log",
                f"run{i}: {common} at /path/to/file{i}\nexiting",
            )

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            pattern = harvest_novel_pattern(fid, workspace=self.tmpdir)

        self.assertIsNotNone(pattern)
        # Must compile without error
        compiled = re.compile(pattern)
        self.assertIsNotNone(compiled)

    def test_extracted_pattern_matches_original_stderrs(self):
        """The extracted pattern should match (or be found in) the original stderrs."""
        import re
        fid = "feat-lcs-003"
        common_phrase = "NewInfraError: unexpected socket closure"
        logs = [
            f"prefix_a: {common_phrase} on port 8080\nmore text",
            f"prefix_b: {common_phrase} on port 9090\nother text",
        ]
        for i, content in enumerate(logs):
            self._write_log(
                f"20260101T0000{i:02d}_{fid[:8]}_implement.stderr.log",
                content,
            )

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            pattern = harvest_novel_pattern(fid, workspace=self.tmpdir)

        self.assertIsNotNone(pattern)
        assert pattern is not None
        # Pattern should match at least one of the original strings
        matched_any = any(re.search(pattern, log) for log in logs)
        self.assertTrue(matched_any, f"Pattern {pattern!r} didn't match any original log")

    def test_three_stderrs_with_shared_error_code(self):
        """Three stderrs all containing same novel error code → pattern includes it."""
        import re
        fid = "feat-lcs-004"
        for i in range(3):
            self._write_log(
                f"20260101T0000{i:02d}_{fid[:8]}_implement.stderr.log",
                f"SystemError: NOVEL_ERR_XYZ99 — internal buffer overflow at step {i}\n"
                f"stack trace line {i}",
            )

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            pattern = harvest_novel_pattern(fid, workspace=self.tmpdir)

        self.assertIsNotNone(pattern)
        assert pattern is not None
        # The common part "NOVEL_ERR_XYZ99" or similar should appear in pattern
        # (may be re.escaped, so check decoded)
        import re as re2
        decoded = re2.sub(r"\\(.)", r"\1", pattern)
        self.assertIn("NOVEL_ERR_XYZ99", decoded)
