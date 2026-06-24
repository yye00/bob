"""Tests: medium-confidence pattern is pruned if no successful spawn in 24h window."""
from __future__ import annotations

import pathlib
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

import yaml

from bob.orchestrator.rca_infra_recovery import run_pattern_graduation_pass


class TestPatternPrunedIfNoSuccessIn24h(unittest.TestCase):
    """Patterns that don't match a successful spawn within 24h are pruned."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self.tmp.name)
        self.spawn_retry_path = self.tmpdir / "spawn_retry.yaml"
        self.rca_resets_path = self.tmpdir / "rca_resets.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def _write_config(self, patterns: list[dict]) -> None:
        self.spawn_retry_path.write_text(
            yaml.dump({"discovered_patterns": patterns}, default_flow_style=False)
        )

    def test_old_medium_pattern_with_no_success_is_pruned(self):
        """Medium pattern discovered >24h ago with no matching success → pruned."""
        now = datetime.now(timezone.utc)
        self._write_config([{
            "pattern": "OldPattern.*error",
            "confidence": "medium",
            "discovered_at": (now - timedelta(hours=25)).isoformat(),
            "feature_id": "feat-prune-001",
        }])
        # No rca_resets events

        result = run_pattern_graduation_pass(
            window_hours=24,
            spawn_retry_path=self.spawn_retry_path,
            rca_resets_path=self.rca_resets_path,
        )

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        self.assertEqual(data["discovered_patterns"], [])
        self.assertEqual(result["pruned"], 1)
        self.assertEqual(result["promoted"], 0)

    def test_recent_medium_pattern_with_no_success_is_kept(self):
        """Medium pattern discovered <24h ago with no matching success → kept (not yet pruned)."""
        now = datetime.now(timezone.utc)
        self._write_config([{
            "pattern": "RecentPattern.*error",
            "confidence": "medium",
            "discovered_at": (now - timedelta(hours=2)).isoformat(),
            "feature_id": "feat-prune-002",
        }])
        # No rca_resets events

        result = run_pattern_graduation_pass(
            window_hours=24,
            spawn_retry_path=self.spawn_retry_path,
            rca_resets_path=self.rca_resets_path,
        )

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        # Recent pattern with no success is kept (waiting for the 24h window to pass)
        self.assertEqual(len(data["discovered_patterns"]), 1)
        self.assertEqual(result["pruned"], 0)

    def test_high_confidence_pattern_never_pruned(self):
        """High-confidence patterns (graduated) are never pruned."""
        now = datetime.now(timezone.utc)
        self._write_config([{
            "pattern": "HighConfOldPattern",
            "confidence": "high",
            "discovered_at": (now - timedelta(hours=100)).isoformat(),
            "feature_id": "feat-prune-003",
        }])

        result = run_pattern_graduation_pass(
            window_hours=24,
            spawn_retry_path=self.spawn_retry_path,
            rca_resets_path=self.rca_resets_path,
        )

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        self.assertEqual(len(data["discovered_patterns"]), 1)
        self.assertEqual(result["pruned"], 0)

    def test_mixed_patterns_pruned_and_kept(self):
        """Old medium (no success) is pruned; recent medium and high are kept."""
        now = datetime.now(timezone.utc)
        self._write_config([
            {
                "pattern": "OldNoSuccess",
                "confidence": "medium",
                "discovered_at": (now - timedelta(hours=30)).isoformat(),
                "feature_id": "feat-prune-004a",
            },
            {
                "pattern": "RecentNoSuccess",
                "confidence": "medium",
                "discovered_at": (now - timedelta(hours=5)).isoformat(),
                "feature_id": "feat-prune-004b",
            },
            {
                "pattern": "HighConfGraduated",
                "confidence": "high",
                "discovered_at": (now - timedelta(hours=48)).isoformat(),
                "feature_id": "feat-prune-004c",
            },
        ])

        result = run_pattern_graduation_pass(
            window_hours=24,
            spawn_retry_path=self.spawn_retry_path,
            rca_resets_path=self.rca_resets_path,
        )

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        remaining = [e["pattern"] for e in data["discovered_patterns"]]
        self.assertNotIn("OldNoSuccess", remaining)
        self.assertIn("RecentNoSuccess", remaining)
        self.assertIn("HighConfGraduated", remaining)
        self.assertEqual(result["pruned"], 1)
