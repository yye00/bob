"""Tests: medium-confidence pattern is promoted to high after matching a successful spawn."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import yaml

from bob3.orchestrator.rca_infra_recovery import run_pattern_graduation_pass


class TestPatternGraduationMediumToHighOnSuccess(unittest.TestCase):
    """Patterns matched by a successful spawn within 24h are promoted to high confidence."""

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

    def _write_rca_event(self, pattern: str, ts: str) -> None:
        event = {
            "timestamp": ts,
            "feature_id": "feat-grad-001",
            "verdict": "infra_only",
            "novel_pattern": pattern,
            "evidence": {},
        }
        with self.rca_resets_path.open("a") as fh:
            fh.write(json.dumps(event) + "\n")

    def test_medium_pattern_promoted_to_high_when_matched(self):
        """Medium pattern that matches recent successful spawn is promoted to high."""
        pattern = "NewInfraError.*socket"
        now = datetime.now(timezone.utc)
        self._write_config([{
            "pattern": pattern,
            "confidence": "medium",
            "discovered_at": (now - timedelta(hours=2)).isoformat(),
            "feature_id": "feat-001",
        }])
        # Record a successful reset using this pattern in the last 24h
        self._write_rca_event(pattern, (now - timedelta(hours=1)).isoformat())

        result = run_pattern_graduation_pass(
            window_hours=24,
            spawn_retry_path=self.spawn_retry_path,
            rca_resets_path=self.rca_resets_path,
        )

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        entry = data["discovered_patterns"][0]
        self.assertEqual(entry["confidence"], "high")
        self.assertEqual(result["promoted"], 1)
        self.assertEqual(result["pruned"], 0)

    def test_graduated_pattern_has_graduated_at_timestamp(self):
        """Promoted pattern gets a graduated_at field."""
        pattern = "SocketGradPattern"
        now = datetime.now(timezone.utc)
        self._write_config([{
            "pattern": pattern,
            "confidence": "medium",
            "discovered_at": (now - timedelta(hours=1)).isoformat(),
            "feature_id": "feat-002",
        }])
        self._write_rca_event(pattern, (now - timedelta(minutes=30)).isoformat())

        run_pattern_graduation_pass(
            spawn_retry_path=self.spawn_retry_path,
            rca_resets_path=self.rca_resets_path,
        )

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        entry = data["discovered_patterns"][0]
        self.assertIn("graduated_at", entry)

    def test_high_confidence_pattern_not_changed(self):
        """Already high-confidence patterns are left unchanged."""
        pattern = "HighConfPattern"
        now = datetime.now(timezone.utc)
        self._write_config([{
            "pattern": pattern,
            "confidence": "high",
            "discovered_at": (now - timedelta(hours=1)).isoformat(),
            "feature_id": "feat-003",
        }])
        self._write_rca_event(pattern, (now - timedelta(minutes=10)).isoformat())

        result = run_pattern_graduation_pass(
            spawn_retry_path=self.spawn_retry_path,
            rca_resets_path=self.rca_resets_path,
        )

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        entry = data["discovered_patterns"][0]
        self.assertEqual(entry["confidence"], "high")
        self.assertEqual(result["promoted"], 0)

    def test_empty_config_returns_zero_promoted_pruned(self):
        """No patterns in config → promoted=0, pruned=0."""
        self._write_config([])

        result = run_pattern_graduation_pass(
            spawn_retry_path=self.spawn_retry_path,
            rca_resets_path=self.rca_resets_path,
        )

        self.assertEqual(result["promoted"], 0)
        self.assertEqual(result["pruned"], 0)

    def test_missing_config_returns_zero(self):
        """Config file doesn't exist → promoted=0, pruned=0 (no error)."""
        result = run_pattern_graduation_pass(
            spawn_retry_path=self.spawn_retry_path,
            rca_resets_path=self.rca_resets_path,
        )

        self.assertEqual(result["promoted"], 0)
        self.assertEqual(result["pruned"], 0)
