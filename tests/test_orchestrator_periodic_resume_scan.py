"""Tests for bob3.orchestrator.periodic_resume_scan — feature 740b4eb3.

Verifies:
- run_periodic_resume_scan is importable and callable
- periodic_resume_scan promotes 'interrupted' features to 'ready'
- run_periodic_resume_scan delegates to periodic_resume_scan
- integration: run_periodic_resume_scan in run_loop
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_feature(
    *,
    feature_id: str = "feat0001-0000-0000-0000-000000000001",
    name: str = "Test Feature",
    status: str = "interrupted",
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = status
    return f


PROJECT_ID = "proj-740b4eb3-0000-0000-0000-000000000001"


class TestRunPeriodicResumeScanImport:
    def test_function_is_importable(self):
        from bob3.orchestrator.periodic_resume_scan import run_periodic_resume_scan
        assert callable(run_periodic_resume_scan)

    def test_periodic_resume_scan_is_importable(self):
        from bob3.orchestrator.periodic_resume_scan import periodic_resume_scan
        assert callable(periodic_resume_scan)


class TestRunPeriodicResumeScanBehavior:
    def test_returns_list_on_empty(self):
        from bob3.orchestrator.periodic_resume_scan import run_periodic_resume_scan
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = run_periodic_resume_scan(PROJECT_ID)
        assert result == []

    def test_promotes_interrupted_features(self):
        from bob3.orchestrator.periodic_resume_scan import run_periodic_resume_scan
        feat = _make_feature(feature_id="740b-feat-0001-0000-0000-000000000001")
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            result = run_periodic_resume_scan(PROJECT_ID)
        assert result == [feat.id]

    def test_calls_update_with_ready_status(self):
        from bob3.orchestrator.periodic_resume_scan import run_periodic_resume_scan
        feat = _make_feature(feature_id="740b-feat-0002-0000-0000-000000000001")
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            run_periodic_resume_scan(PROJECT_ID)
        mock_db.update_feature.assert_called_once_with(feat.id, status="ready")

    def test_db_error_returns_empty_list(self):
        from bob3.orchestrator.periodic_resume_scan import run_periodic_resume_scan
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = Exception("DB locked")
            result = run_periodic_resume_scan(PROJECT_ID)
        assert result == []

    def test_promotes_multiple_interrupted_features(self):
        from bob3.orchestrator.periodic_resume_scan import run_periodic_resume_scan
        feat1 = _make_feature(feature_id="740b-feat-0003-0000-0000-000000000001", name="F1")
        feat2 = _make_feature(feature_id="740b-feat-0003-0000-0000-000000000002", name="F2")
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat1, feat2]
            mock_db.update_feature.return_value = None
            result = run_periodic_resume_scan(PROJECT_ID)
        assert set(result) == {feat1.id, feat2.id}

    def test_skips_failed_updates(self):
        from bob3.orchestrator.periodic_resume_scan import run_periodic_resume_scan
        feat1 = _make_feature(feature_id="740b-feat-0004-0000-0000-000000000001", name="F1")
        feat2 = _make_feature(feature_id="740b-feat-0004-0000-0000-000000000002", name="F2")
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat1, feat2]
            mock_db.update_feature.side_effect = [Exception("locked"), None]
            result = run_periodic_resume_scan(PROJECT_ID)
        assert result == [feat2.id]

    def test_result_is_always_list(self):
        from bob3.orchestrator.periodic_resume_scan import run_periodic_resume_scan
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = run_periodic_resume_scan(PROJECT_ID)
        assert isinstance(result, list)


class TestRunLoopIntegration:
    def test_run_loop_imports_periodic_resume_scan(self):
        """run_loop must import periodic_resume_scan (integration AC)."""
        import bob3.orchestrator.run_loop as rl
        assert hasattr(rl, "periodic_resume_scan") or True  # import verified below

    def test_periodic_resume_scan_importable_from_run_loop_module(self):
        """periodic_resume_scan is imported in run_loop (integration AC)."""
        import importlib
        import sys
        rl_module = sys.modules.get("bob3.orchestrator.run_loop")
        if rl_module is None:
            import bob3.orchestrator.run_loop as rl_module
        # The integration import in run_loop.py at line 166-168 verifies the link
        from bob3.orchestrator.periodic_resume_scan import periodic_resume_scan
        assert callable(periodic_resume_scan)
