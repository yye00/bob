"""Tests: auto_reset cap — after 3 RCA-driven resets, NH stands regardless of verdict."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from bob.orchestrator.rca_infra_recovery import auto_reset_if_infra


class TestAutoResetCap3ThenNHStands(unittest.TestCase):
    """After 3 RCA-driven resets per feature, 4th attempt must NOT reset (NH stands)."""

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
        for i in range(2):
            p = self.agent_logs_dir / f"20260101T0000{i:02d}_{fid[:8]}_implement.stderr.log"
            p.write_text("self signed certificate in certificate chain")

    def _seed_prior_resets(self, fid: str, count: int) -> None:
        """Write N prior reset events to rca_resets.jsonl."""
        events = [
            json.dumps({
                "timestamp": f"2026-01-01T0{i:02d}:00:00+00:00",
                "feature_id": fid,
                "verdict": "infra_only",
                "novel_pattern": None,
                "evidence": {"reset_number": i + 1},
            })
            for i in range(count)
        ]
        self.rca_resets_path.write_text("\n".join(events) + "\n")

    def test_first_reset_succeeds(self):
        """First auto-reset (no prior resets) returns True."""
        fid = "feat-cap-001"
        self._make_infra_logs(fid)
        db_update = MagicMock()

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
            patch("bob.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", self.rca_resets_path),
            patch("bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            result = auto_reset_if_infra(fid, "proj-001", db_update, workspace=self.tmpdir)

        self.assertTrue(result)

    def test_third_reset_still_succeeds(self):
        """3rd auto-reset (2 prior resets) still returns True."""
        fid = "feat-cap-002"
        self._make_infra_logs(fid)
        self._seed_prior_resets(fid, 2)
        db_update = MagicMock()

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
            patch("bob.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", self.rca_resets_path),
            patch("bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            result = auto_reset_if_infra(fid, "proj-001", db_update, workspace=self.tmpdir)

        self.assertTrue(result)

    def test_fourth_attempt_nh_stands_despite_infra_verdict(self):
        """4th attempt (3 prior resets) → auto_reset_cap_reached → NH stands."""
        fid = "feat-cap-003"
        self._make_infra_logs(fid)
        self._seed_prior_resets(fid, 3)
        db_update = MagicMock()

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
            patch("bob.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", self.rca_resets_path),
            patch("bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            result = auto_reset_if_infra(fid, "proj-001", db_update, workspace=self.tmpdir)

        self.assertFalse(result)
        db_update.assert_not_called()

    def test_cap_is_per_feature_not_global(self):
        """Cap counts resets per feature; different feature is unaffected."""
        fid_a = "feat-cap-004a"
        fid_b = "feat-cap-004b"
        self._make_infra_logs(fid_b)

        # fid_a has 3 resets, fid_b has 0
        self._seed_prior_resets(fid_a, 3)

        db_update = MagicMock()

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
            patch("bob.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", self.rca_resets_path),
            patch("bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            result = auto_reset_if_infra(fid_b, "proj-001", db_update, workspace=self.tmpdir)

        # fid_b has 0 prior resets — should succeed
        self.assertTrue(result)

    def test_cap_reached_event_logged_with_auto_reset_cap_reached(self):
        """When cap is reached, an event with auto_reset_cap_reached=True is emitted."""
        fid = "feat-cap-005"
        self._make_infra_logs(fid)
        self._seed_prior_resets(fid, 3)
        db_update = MagicMock()

        with (
            patch("bob.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", self.agent_logs_dir),
            patch("bob.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", self.rca_resets_path),
            patch("bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            auto_reset_if_infra(fid, "proj-001", db_update, workspace=self.tmpdir)

        # Read all events — the 4th should have cap_reached marker
        all_events = [
            json.loads(line)
            for line in self.rca_resets_path.read_text().splitlines()
            if line.strip()
        ]
        # The last event (newly appended) should have cap_reached
        cap_event = all_events[-1]
        self.assertTrue(cap_event.get("evidence", {}).get("auto_reset_cap_reached"))
