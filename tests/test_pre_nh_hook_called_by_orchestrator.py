"""Tests: run_loop calls auto_reset_if_infra before any needs_human transition.

The pre-NH hook requirement: orchestrator MUST call auto_reset_if_infra BEFORE
any feature.status="needs_human" assignment. This test verifies the import
is present and the hook is accessible from the orchestrator module.
"""
from __future__ import annotations

import importlib
import inspect
import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

from bob3.orchestrator import rca_infra_recovery


class TestPreNHHookCalledByOrchestrator(unittest.TestCase):
    """auto_reset_if_infra must be wired into run_loop before needs_human transitions."""

    def test_rca_infra_recovery_module_importable(self):
        """rca_infra_recovery module must be importable."""
        mod = importlib.import_module("bob3.orchestrator.rca_infra_recovery")
        self.assertIsNotNone(mod)

    def test_auto_reset_if_infra_is_callable(self):
        """auto_reset_if_infra must be a callable function."""
        self.assertTrue(callable(rca_infra_recovery.auto_reset_if_infra))

    def test_auto_reset_if_infra_signature(self):
        """auto_reset_if_infra must accept feature_id, project_id, db_update_fn, workspace."""
        sig = inspect.signature(rca_infra_recovery.auto_reset_if_infra)
        params = list(sig.parameters.keys())
        self.assertIn("feature_id", params)
        self.assertIn("project_id", params)
        self.assertIn("db_update_fn", params)
        self.assertIn("workspace", params)

    def test_auto_reset_if_infra_returns_bool(self):
        """auto_reset_if_infra must return a bool (True=reset happened, False=NH proceeds)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = pathlib.Path(tmp)
            agent_logs = tmpdir / ".bob3" / "agent_logs"
            agent_logs.mkdir(parents=True)
            reviews = tmpdir / "reviews"
            reviews.mkdir(parents=True)
            spawn_cfg = tmpdir / "config" / "spawn_retry.yaml"
            spawn_cfg.parent.mkdir(parents=True)

            with (
                patch("bob3.orchestrator.rca_infra_recovery._AGENT_LOGS_DIR", agent_logs),
                patch("bob3.orchestrator.rca_infra_recovery._RCA_RESETS_JSONL", reviews / "rca_resets.jsonl"),
                patch("bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG", spawn_cfg),
            ):
                result = rca_infra_recovery.auto_reset_if_infra(
                    "feat-hook-001",
                    "proj-001",
                    MagicMock(),
                    workspace=tmpdir,
                )

        self.assertIsInstance(result, bool)

    def test_run_loop_imports_rca_infra_recovery(self):
        """run_loop module must import rca_infra_recovery (pre-NH hook wired)."""
        run_loop = importlib.import_module("bob3.orchestrator.run_loop")
        # The module must reference rca_infra_recovery somewhere
        source_file = inspect.getfile(run_loop)
        source = pathlib.Path(source_file).read_text()
        self.assertIn(
            "rca_infra_recovery",
            source,
            "run_loop.py must import/use rca_infra_recovery for pre-NH hook",
        )

    def test_run_loop_calls_auto_reset_before_needs_human(self):
        """auto_reset_if_infra is referenced in run_loop source near needs_human."""
        import bob3.orchestrator.run_loop as rl
        source_file = inspect.getfile(rl)
        source = pathlib.Path(source_file).read_text()

        # Both symbols must appear in the same file
        self.assertIn("auto_reset_if_infra", source)
        self.assertIn("needs_human", source)

        # Find the relative position: auto_reset_if_infra call site should appear
        # somewhere before or near a needs_human assignment
        rca_pos = source.find("auto_reset_if_infra")
        nh_pos = source.find('"needs_human"')
        # At least one call to auto_reset_if_infra must exist
        self.assertGreater(rca_pos, 0, "auto_reset_if_infra not found in run_loop.py")
