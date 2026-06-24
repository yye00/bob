"""Tests: auto_reset_if_infra resets feature to ready when verdict is infra_only."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from bob.orchestrator.rca_infra_recovery import auto_reset_if_infra


class TestAutoResetIfInfraWritesBackToReady(unittest.TestCase):
    """Auto_reset_if_infra sets status=ready, refinement_attempts=0 on infra_only verdict."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self.tmp.name)
        self.agent_logs_dir = self.tmpdir / ".bob" / "agent_logs"
        self.agent_logs_dir.mkdir(parents=True)
        self.reviews_dir = self.tmpdir / "reviews"
        self.reviews_dir.mkdir(parents=True)
        self.rca_resets_path = self.reviews_dir / "rca_resets.jsonl"
        self.config_dir = self.tmpdir / "config"
        self.config_dir.mkdir(parents=True)
        self.spawn_retry_path = self.config_dir / "spawn_retry.yaml"

    def tearDown(self):
        self.tmp.cleanup()

    def _make_infra_logs(self, fid: str) -> None:
        """Create infra-pattern stderr logs for a feature."""
        for i in range(2):
            p = self.agent_logs_dir / f"20260101T0000{i:02d}_{fid[:8]}_implement.stderr.log"
            p.write_text("self signed certificate in certificate chain\nnetwork failed")

    def test_infra_only_verdict_calls_db_update_with_ready(self):
        """When verdict=infra_only, db_update_fn called with status=ready."""
        fid = "feat-reset-001"
        self._make_infra_logs(fid)
        db_update = MagicMock()

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
            patch("bob.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", self.rca_resets_path),
            patch("bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            result = auto_reset_if_infra(fid, "proj-001", db_update, workspace=self.tmpdir)

        self.assertTrue(result)
        db_update.assert_called_once_with(fid, status="ready", refinement_attempts=0)

    def test_infra_only_verdict_returns_true(self):
        """auto_reset_if_infra returns True when reset happens."""
        fid = "feat-reset-002"
        self._make_infra_logs(fid)
        db_update = MagicMock()

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
            patch("bob.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", self.rca_resets_path),
            patch("bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            result = auto_reset_if_infra(fid, "proj-001", db_update, workspace=self.tmpdir)

        self.assertTrue(result)

    def test_feature_defect_verdict_returns_false(self):
        """When verdict=feature_defect, auto_reset returns False (NH proceeds)."""
        import json as _json

        fid = "feat-reset-003"
        # Write progress with real work
        progress_dir = self.tmpdir / ".bob"
        progress_dir.mkdir(parents=True, exist_ok=True)
        (progress_dir / "progress.jsonl").write_text(
            _json.dumps({"type": "tool_use", "tool": "Write"}) + "\n" +
            _json.dumps({"type": "tool_result", "content": "done"})
        )
        # Non-infra stderr
        p = self.agent_logs_dir / f"20260101T000000_{fid[:8]}_implement.stderr.log"
        p.write_text("AssertionError: expected 42 got 0\n" * 20)

        db_update = MagicMock()

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
            patch("bob.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", self.rca_resets_path),
            patch("bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            result = auto_reset_if_infra(fid, "proj-001", db_update, workspace=self.tmpdir)

        self.assertFalse(result)
        db_update.assert_not_called()

    def test_infra_only_emits_rca_reset_event(self):
        """Reset emits structured event to rca_resets.jsonl."""
        fid = "feat-reset-004"
        self._make_infra_logs(fid)
        db_update = MagicMock()

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
            patch("bob.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", self.rca_resets_path),
            patch("bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            auto_reset_if_infra(fid, "proj-001", db_update, workspace=self.tmpdir)

        self.assertTrue(self.rca_resets_path.exists())
        events = [
            json.loads(line) for line in self.rca_resets_path.read_text().splitlines() if line.strip()
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["feature_id"], fid)
        self.assertEqual(events[0]["verdict"], "infra_only")

    def test_refinement_attempts_reset_to_zero(self):
        """DB update must pass refinement_attempts=0."""
        fid = "feat-reset-005"
        self._make_infra_logs(fid)
        db_update = MagicMock()

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
            patch("bob.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", self.rca_resets_path),
            patch("bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            auto_reset_if_infra(fid, "proj-001", db_update, workspace=self.tmpdir)

        call_kwargs = db_update.call_args[1]
        self.assertEqual(call_kwargs.get("refinement_attempts"), 0)
        self.assertEqual(call_kwargs.get("status"), "ready")
