"""Tests for bob.orchestrator.run_loop.periodic_resume_scan (92c96882).

Verifies the AC set for feature 92c96882:
- Function defined: bob.orchestrator.run_loop.periodic_resume_scan
- Integration: bob.orchestrator.run_loop
- periodic_resume_scan promotes 'interrupted' rows mid-run without restart
- Uses fixture: tests/fixtures/interrupted_feature_state.py
"""

from __future__ import annotations

import importlib
import logging
from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures.interrupted_feature_state import (
    PROJECT_ID,
    make_interrupted_feature,
    make_interrupted_feature_batch,
)


# ---------------------------------------------------------------------------
# AC: Function defined: bob.orchestrator.run_loop.periodic_resume_scan
# ---------------------------------------------------------------------------


class TestPeriodicResumeScanDefinedInRunLoop:
    def test_function_exists_in_run_loop_module(self):
        run_loop = importlib.import_module("bob.orchestrator.run_loop")
        assert hasattr(run_loop, "periodic_resume_scan"), (
            "bob.orchestrator.run_loop must expose 'periodic_resume_scan' as a "
            "public module-level function"
        )

    def test_function_is_callable(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        assert callable(periodic_resume_scan)

    def test_function_accepts_project_id(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = periodic_resume_scan(PROJECT_ID)
        assert isinstance(result, list)

    def test_importable_from_run_loop_directly(self):
        from bob.orchestrator.run_loop import periodic_resume_scan as fn  # noqa: F401
        assert fn is not None


# ---------------------------------------------------------------------------
# AC: integration: bob.orchestrator.run_loop
# ---------------------------------------------------------------------------


class TestRunLoopIntegration:
    def test_private_alias_present(self):
        run_loop = importlib.import_module("bob.orchestrator.run_loop")
        assert hasattr(run_loop, "_periodic_resume_scan"), (
            "run_loop must import periodic_resume_scan as _periodic_resume_scan "
            "for the orchestrator tick to wire it in"
        )

    def test_public_and_private_are_consistent(self):
        """periodic_resume_scan and _periodic_resume_scan must agree on empty input."""
        from bob.orchestrator.run_loop import periodic_resume_scan
        from bob.orchestrator.run_loop import _periodic_resume_scan
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            r1 = periodic_resume_scan(PROJECT_ID)
            r2 = _periodic_resume_scan(PROJECT_ID)
        assert r1 == r2 == []

    def test_run_loop_module_imports_orchestrator_periodic_resume_scan(self):
        run_loop = importlib.import_module("bob.orchestrator.run_loop")
        prs_mod = importlib.import_module("bob.orchestrator.periodic_resume_scan")
        assert hasattr(prs_mod, "periodic_resume_scan"), (
            "bob.orchestrator.periodic_resume_scan must define periodic_resume_scan"
        )


# ---------------------------------------------------------------------------
# Promotion behaviour via run_loop.periodic_resume_scan
# ---------------------------------------------------------------------------


class TestPeriodicResumeScanBehaviour:
    def test_returns_empty_when_no_interrupted_features(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = periodic_resume_scan(PROJECT_ID)
        assert result == []

    def test_promotes_single_interrupted_feature(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        feat = make_interrupted_feature()
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            result = periodic_resume_scan(PROJECT_ID)
        mock_db.update_feature.assert_called_once_with(feat.id, status="ready")
        assert result == [feat.id]

    def test_promotes_multiple_interrupted_features(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        feats = make_interrupted_feature_batch(3)
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = feats
            mock_db.update_feature.return_value = None
            result = periodic_resume_scan(PROJECT_ID)
        assert len(result) == 3
        assert set(result) == {f.id for f in feats}

    def test_queries_by_interrupted_status(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            periodic_resume_scan(PROJECT_ID)
        mock_db.list_features.assert_called_once_with(
            project_id=PROJECT_ID, status="interrupted"
        )

    def test_sets_promoted_status_to_ready(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        feat = make_interrupted_feature()
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            periodic_resume_scan(PROJECT_ID)
        _, kwargs = mock_db.update_feature.call_args
        assert kwargs.get("status") == "ready"


# ---------------------------------------------------------------------------
# Error resilience (DB errors must not crash the loop)
# ---------------------------------------------------------------------------


class TestPeriodicResumeScanErrorResilience:
    def test_list_features_db_error_returns_empty(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = Exception("DB locked")
            result = periodic_resume_scan(PROJECT_ID)
        assert result == []

    def test_update_feature_db_error_skips_that_feature(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        feats = make_interrupted_feature_batch(2)
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = feats
            mock_db.update_feature.side_effect = [Exception("constraint"), None]
            result = periodic_resume_scan(PROJECT_ID)
        assert result == [feats[1].id]

    def test_list_features_exception_does_not_propagate(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = RuntimeError("unexpected")
            result = periodic_resume_scan(PROJECT_ID)
        assert result == []

    def test_update_exception_does_not_propagate(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        feat = make_interrupted_feature()
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.side_effect = RuntimeError("disk full")
            result = periodic_resume_scan(PROJECT_ID)
        assert result == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestPeriodicResumeScanIdempotency:
    def test_safe_to_call_repeatedly(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        feat = make_interrupted_feature()
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            r1 = periodic_resume_scan(PROJECT_ID)
            r2 = periodic_resume_scan(PROJECT_ID)
        assert r1 == [feat.id]
        assert r2 == [feat.id]

    def test_empty_project_never_crashes(self):
        from bob.orchestrator.run_loop import periodic_resume_scan
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            for _ in range(5):
                result = periodic_resume_scan(PROJECT_ID)
        assert result == []


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestPeriodicResumeScanLogging:
    def test_logs_info_for_promoted_feature(self, caplog):
        from bob.orchestrator.run_loop import periodic_resume_scan
        feat = make_interrupted_feature()
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            with caplog.at_level(
                logging.INFO, logger="bob.orchestrator.periodic_resume_scan"
            ):
                periodic_resume_scan(PROJECT_ID)
        assert any(feat.id in r.message for r in caplog.records)

    def test_logs_debug_on_list_features_failure(self, caplog):
        from bob.orchestrator.run_loop import periodic_resume_scan
        with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = Exception("DB error")
            with caplog.at_level(
                logging.DEBUG, logger="bob.orchestrator.periodic_resume_scan"
            ):
                periodic_resume_scan(PROJECT_ID)
        assert any("periodic_resume_scan" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Fixture file: tests/fixtures/interrupted_feature_state.py
# ---------------------------------------------------------------------------


class TestInterruptedFeatureStateFixture:
    def test_fixture_module_importable(self):
        from tests.fixtures import interrupted_feature_state  # noqa: F401

    def test_make_interrupted_feature_returns_mock_with_correct_status(self):
        feat = make_interrupted_feature()
        assert feat.status == "interrupted"

    def test_make_interrupted_feature_has_id_and_name(self):
        feat = make_interrupted_feature(feature_id="aaa", name="MyFeat")
        assert feat.id == "aaa"
        assert feat.name == "MyFeat"

    def test_make_interrupted_feature_batch_returns_correct_count(self):
        batch = make_interrupted_feature_batch(5)
        assert len(batch) == 5

    def test_make_interrupted_feature_batch_unique_ids(self):
        batch = make_interrupted_feature_batch(4)
        ids = [f.id for f in batch]
        assert len(set(ids)) == 4

    def test_project_id_constant_is_non_empty_string(self):
        assert isinstance(PROJECT_ID, str)
        assert len(PROJECT_ID) > 0
