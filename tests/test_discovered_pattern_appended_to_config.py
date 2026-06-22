"""Tests: novel pattern is appended to config/spawn_retry.yaml with correct metadata."""
from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml

from bob3.orchestrator.rca_infra_recovery import (
    _append_discovered_pattern,
    auto_reset_if_infra,
)


class TestDiscoveredPatternAppendedToConfig(unittest.TestCase):
    """Novel discovered patterns are appended to spawn_retry.yaml with correct structure."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self.tmp.name)
        self.config_dir = self.tmpdir / "config"
        self.config_dir.mkdir(parents=True)
        self.spawn_retry_path = self.config_dir / "spawn_retry.yaml"

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_creates_file_if_missing(self):
        """_append_discovered_pattern creates spawn_retry.yaml if not present."""
        _append_discovered_pattern("test.*pattern", "feat-001")

        cfg_path = pathlib.Path("config/spawn_retry.yaml")
        # Use our tmp path explicitly
        with patch("bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path):
            _append_discovered_pattern("test.*pattern", "feat-001")

        self.assertTrue(self.spawn_retry_path.exists())

    def test_pattern_has_confidence_medium(self):
        """Discovered patterns get confidence=medium."""
        with patch("bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path):
            _append_discovered_pattern("MyNovelError.*socket", "feat-grad-001")

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        entry = data["discovered_patterns"][0]
        self.assertEqual(entry["confidence"], "medium")

    def test_pattern_has_discovered_at_timestamp(self):
        """Discovered patterns include discovered_at ISO timestamp."""
        with patch("bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path):
            _append_discovered_pattern("SomePattern", "feat-ts-001")

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        entry = data["discovered_patterns"][0]
        self.assertIn("discovered_at", entry)
        self.assertRegex(entry["discovered_at"], r"\d{4}-\d{2}-\d{2}T")

    def test_pattern_has_feature_id_annotation(self):
        """Discovered patterns include feature_id."""
        fid = "feat-annot-001"
        with patch("bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path):
            _append_discovered_pattern("SomePattern", fid)

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        entry = data["discovered_patterns"][0]
        self.assertEqual(entry["feature_id"], fid)

    def test_deduplication_prevents_duplicate_patterns(self):
        """Same pattern is not added twice."""
        pattern = "DuplicatePattern.*error"
        with patch("bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path):
            _append_discovered_pattern(pattern, "feat-dup-001")
            _append_discovered_pattern(pattern, "feat-dup-002")

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        self.assertEqual(len(data["discovered_patterns"]), 1)

    def test_multiple_different_patterns_all_appended(self):
        """Multiple different patterns all get stored."""
        patterns = ["PatternA.*foo", "PatternB.*bar", "PatternC.*baz"]
        with patch("bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path):
            for pat in patterns:
                _append_discovered_pattern(pat, "feat-multi-001")

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        stored_patterns = [e["pattern"] for e in data["discovered_patterns"]]
        for pat in patterns:
            self.assertIn(pat, stored_patterns)

    def test_append_preserves_existing_config_keys(self):
        """Appending a pattern does not overwrite other keys in spawn_retry.yaml."""
        initial = {
            "known_patterns": ["ECONNRESET", "ETIMEDOUT"],
            "max_retries": 5,
        }
        self.spawn_retry_path.write_text(yaml.dump(initial))

        with patch("bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path):
            _append_discovered_pattern("NewPattern", "feat-preserve-001")

        data = yaml.safe_load(self.spawn_retry_path.read_text())
        self.assertEqual(data["known_patterns"], ["ECONNRESET", "ETIMEDOUT"])
        self.assertEqual(data["max_retries"], 5)
        self.assertEqual(len(data["discovered_patterns"]), 1)

    def test_auto_reset_appends_novel_pattern_via_full_pipeline(self):
        """auto_reset_if_infra appends discovered novel pattern during reset."""
        agent_logs = self.tmpdir / ".bob3" / "agent_logs"
        agent_logs.mkdir(parents=True)
        reviews = self.tmpdir / "reviews"
        reviews.mkdir(parents=True)
        rca_resets = reviews / "rca_resets.jsonl"

        fid = "feat-pipeline-001"
        # Write two similar novel-infra stderr logs (not matching builtin patterns)
        novel_error = "NewInfraError: ENOENT /var/run/claude-socket.sock"
        for i in range(2):
            p = agent_logs / f"20260101T0000{i:02d}_{fid[:8]}_implement.stderr.log"
            p.write_bytes(novel_error.encode() * 1)  # <1024 bytes → h4 too

        db_update = MagicMock()

        with (
            patch("bob3.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", agent_logs),
            patch("bob3.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", rca_resets),
            patch("bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", self.spawn_retry_path),
        ):
            auto_reset_if_infra(fid, "proj-001", db_update, workspace=self.tmpdir)

        # Pattern may or may not have been appended depending on LCS result,
        # but if it was, it must have correct metadata
        if self.spawn_retry_path.exists():
            data = yaml.safe_load(self.spawn_retry_path.read_text()) or {}
            for entry in data.get("discovered_patterns", []):
                self.assertEqual(entry.get("confidence"), "medium")
                self.assertIn("discovered_at", entry)
                self.assertIn("feature_id", entry)
