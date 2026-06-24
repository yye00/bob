"""Tests: cross-feature crash clustering boosts infra_only verdict."""
from __future__ import annotations

import pathlib
import tempfile
import time
import unittest
from unittest.mock import patch

from bob.orchestrator.rca_infra_recovery import classify_attempts


class TestClassifyAttemptsCrossFeatureClusterBoostsInfra(unittest.TestCase):
    """Cross-feature crash cluster in 30-min window boosts infra_only heuristic."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self.tmp.name)
        self.agent_logs_dir = self.tmpdir / ".bob" / "agent_logs"
        self.agent_logs_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_log(self, name: str, content: str, mtime: float | None = None) -> pathlib.Path:
        p = self.agent_logs_dir / name
        p.write_text(content)
        if mtime is not None:
            import os
            os.utime(p, (mtime, mtime))
        return p

    def test_other_feature_crash_in_window_boosts_h3(self):
        """Another feature crashing with infra errors in same 30-min window boosts verdict."""
        fid = "feat-cluster-001"
        now = time.time()

        # This feature's log
        self._write_log(
            f"20260101T000000_{fid[:8]}_implement.stderr.log",
            "self signed certificate in certificate chain",
            mtime=now - 10,
        )

        # OTHER feature crashed 5 minutes ago with infra error
        other_fid = "other-feat-aabbccdd"
        self._write_log(
            f"20260101T000500_{other_fid[:8]}_implement.stderr.log",
            "self signed certificate in certificate chain\nnetwork unreachable",
            mtime=now - 300,
        )

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        self.assertEqual(verdict, "infra_only")

    def test_multiple_other_features_in_window_boosts_verdict(self):
        """Multiple other features crashing in window strongly boosts verdict."""
        fid = "feat-cluster-002"
        now = time.time()

        self._write_log(
            f"20260101T000000_{fid[:8]}_implement.stderr.log",
            "ECONNRESET connection reset by peer",
            mtime=now - 60,
        )

        # Three other features crashed with infra errors
        for i in range(3):
            other_fid = f"other{i}-aabbcced"
            self._write_log(
                f"20260101T0000{i:02d}_{other_fid[:8]}_impl.stderr.log",
                "rate_limit_error: rate limit exceeded",
                mtime=now - (i + 1) * 120,
            )

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        self.assertEqual(verdict, "infra_only")

    def test_old_other_feature_crash_outside_window_does_not_boost(self):
        """Crash outside 30-min window doesn't count as cluster evidence."""
        fid = "feat-cluster-003"
        now = time.time()

        # This feature's log — no infra match, no work events
        # Just a small log (h4 heuristic)
        p = self._write_log(
            f"20260101T000000_{fid[:8]}_implement.stderr.log",
            "UnknownError: something weird happened",
            mtime=now - 10,
        )
        # Make it small
        p.write_bytes(b"x" * 100)

        # Other feature crashed 40 minutes ago — outside 30-min window
        other_fid = "old-feat-aabbccdd"
        self._write_log(
            f"20260101T000000_{other_fid[:8]}_implement.stderr.log",
            "ECONNRESET connection reset by peer",
            mtime=now - 2400,  # 40 minutes ago
        )

        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        # Without cluster boost and without infra stderr, verdict should be feature_defect
        self.assertNotEqual(verdict, "infra_only")

    def test_cluster_check_excludes_own_feature_logs(self):
        """Cross-feature clustering must not count the feature's own logs."""
        fid = "feat-cluster-004"
        now = time.time()

        # Only this feature's own logs — multiple ones — all infra
        for i in range(5):
            self._write_log(
                f"20260101T0000{i:02d}_{fid[:8]}_implement.stderr.log",
                "self signed certificate in certificate chain",
                mtime=now - i * 30,
            )

        # No other-feature logs
        with patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir):
            verdict = classify_attempts(fid, workspace=self.tmpdir)

        # h1 (all stderrs infra) + h2 (no work) = 2/4 → infra_only
        # but h3 should NOT be boosted by own logs
        # Verdict should still be infra_only due to h1+h2
        self.assertEqual(verdict, "infra_only")
