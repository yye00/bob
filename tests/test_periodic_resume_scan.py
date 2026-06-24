"""Tests for bob3.orchestrator.periodic_resume_scan (AC: f9f35288).

Verifies:
- periodic_resume_scan is importable from bob3.orchestrator.periodic_resume_scan
- It promotes 'interrupted' features to 'ready'
- It returns the list of promoted feature IDs
- It skips features that fail to update (DB errors)
- It handles empty result gracefully
- It logs structured INFO messages for each promotion
- It is integrated into run_loop (imported as _periodic_resume_scan)
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, call, patch

import pytest

from bob3.orchestrator.periodic_resume_scan import periodic_resume_scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Import / signature
# ---------------------------------------------------------------------------


class TestPeriodicResumeScanImport:
    def test_function_is_importable(self):
        from bob3.orchestrator.periodic_resume_scan import periodic_resume_scan as fn  # noqa: F401

        assert callable(fn)

    def test_accepts_project_id_returns_list(self):
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = periodic_resume_scan("proj-1")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Happy-path promotion
# ---------------------------------------------------------------------------


class TestPeriodicResumeScanPromotion:
    def test_promotes_single_interrupted_feature(self):
        feat = _make_feature()
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            result = periodic_resume_scan("proj-abc")
        mock_db.update_feature.assert_called_once_with(feat.id, status="ready")
        assert result == [feat.id]

    def test_promotes_multiple_interrupted_features(self):
        feats = [
            _make_feature(feature_id=f"feat000{i}-0000-0000-0000-000000000001", name=f"F{i}")
            for i in range(3)
        ]
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = feats
            mock_db.update_feature.return_value = None
            result = periodic_resume_scan("proj-multi")
        assert len(result) == 3
        assert set(result) == {f.id for f in feats}

    def test_returns_empty_list_when_no_interrupted_features(self):
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = periodic_resume_scan("proj-empty")
        assert result == []

    def test_queries_by_interrupted_status(self):
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            periodic_resume_scan("proj-xyz")
        mock_db.list_features.assert_called_once_with(
            project_id="proj-xyz", status="interrupted"
        )

    def test_sets_status_to_ready(self):
        feat = _make_feature(feature_id="aaaa0001-0000-0000-0000-000000000001")
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            periodic_resume_scan("proj-z")
        args, kwargs = mock_db.update_feature.call_args
        assert args[0] == feat.id
        assert kwargs.get("status") == "ready"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestPeriodicResumeScanErrorHandling:
    def test_list_features_db_error_returns_empty(self):
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = Exception("DB locked")
            result = periodic_resume_scan("proj-err")
        assert result == []

    def test_update_feature_db_error_skips_feature(self):
        feat1 = _make_feature(
            feature_id="feat0001-0000-0000-0000-000000000001", name="F1"
        )
        feat2 = _make_feature(
            feature_id="feat0002-0000-0000-0000-000000000001", name="F2"
        )
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat1, feat2]
            # feat1 fails to update, feat2 succeeds
            mock_db.update_feature.side_effect = [Exception("constraint"), None]
            result = periodic_resume_scan("proj-partial")
        # Only feat2 should be in the returned list
        assert result == [feat2.id]

    def test_all_updates_fail_returns_empty(self):
        feats = [_make_feature(feature_id=f"feat000{i}-0000-0000-0000-000000000001") for i in range(2)]
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = feats
            mock_db.update_feature.side_effect = Exception("busy")
            result = periodic_resume_scan("proj-all-fail")
        assert result == []

    def test_list_features_exception_does_not_propagate(self):
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = RuntimeError("unexpected")
            # Should not raise
            result = periodic_resume_scan("proj-safe")
        assert result == []

    def test_update_exception_does_not_propagate(self):
        feat = _make_feature()
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.side_effect = RuntimeError("disk full")
            result = periodic_resume_scan("proj-safe2")
        assert result == []


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestPeriodicResumeScanLogging:
    def test_logs_info_for_each_promoted_feature(self, caplog):
        feat = _make_feature(
            feature_id="feat0001-0000-0000-0000-000000000001", name="Sticky-completed gate"
        )
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            with caplog.at_level(
                logging.INFO, logger="bob3.orchestrator.periodic_resume_scan"
            ):
                periodic_resume_scan("proj-log")
        assert any("periodic_resume_scan" in r.message for r in caplog.records)
        assert any(feat.id in r.message for r in caplog.records)

    def test_logs_debug_on_list_features_failure(self, caplog):
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = Exception("DB error")
            with caplog.at_level(
                logging.DEBUG, logger="bob3.orchestrator.periodic_resume_scan"
            ):
                periodic_resume_scan("proj-dbg")
        assert any("periodic_resume_scan" in r.message for r in caplog.records)

    def test_logs_debug_on_update_feature_failure(self, caplog):
        feat = _make_feature()
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.side_effect = Exception("write failed")
            with caplog.at_level(
                logging.DEBUG, logger="bob3.orchestrator.periodic_resume_scan"
            ):
                periodic_resume_scan("proj-dbg2")
        assert any("periodic_resume_scan" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestPeriodicResumeScanIdempotency:
    def test_multiple_calls_are_safe(self):
        feat = _make_feature()
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            r1 = periodic_resume_scan("proj-idem")
            r2 = periodic_resume_scan("proj-idem")
        assert r1 == [feat.id]
        assert r2 == [feat.id]

    def test_empty_project_never_crashes(self):
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            for _ in range(5):
                result = periodic_resume_scan("proj-empty")
            assert result == []


# ---------------------------------------------------------------------------
# Orchestrator integration: imported in run_loop
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    def test_periodic_resume_scan_imported_in_run_loop(self):
        import importlib

        run_loop = importlib.import_module("bob3.orchestrator.run_loop")
        assert hasattr(run_loop, "_periodic_resume_scan"), (
            "run_loop must import periodic_resume_scan as _periodic_resume_scan "
            "for periodic resume to be wired into the orchestrator tick"
        )

    def test_periodic_resume_scan_module_importable(self):
        from bob3.orchestrator import periodic_resume_scan as mod  # noqa: F401

        assert hasattr(mod, "periodic_resume_scan")

    def test_periodic_resume_scan_is_callable_from_orchestrator_package(self):
        from bob3.orchestrator.periodic_resume_scan import periodic_resume_scan as fn

        assert callable(fn)

    def test_promote_interrupted_rows_imported_in_run_loop(self):
        import importlib

        run_loop = importlib.import_module("bob3.orchestrator.run_loop")
        assert hasattr(run_loop, "_promote_interrupted_rows"), (
            "run_loop must import promote_interrupted_rows as _promote_interrupted_rows "
            "for periodic resume (6abe05be) to be wired into the orchestrator tick"
        )


# ---------------------------------------------------------------------------
# Tests for bob3.periodic_resume_scan.promote_interrupted_rows (6abe05be)
# ---------------------------------------------------------------------------


from bob3.periodic_resume_scan import promote_interrupted_rows  # noqa: E402


class TestPromoteInterruptedRowsImport:
    def test_function_is_importable(self):
        from bob3.periodic_resume_scan import promote_interrupted_rows as fn  # noqa: F401

        assert callable(fn)

    def test_accepts_project_id_returns_list(self):
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = promote_interrupted_rows("proj-1")
        assert isinstance(result, list)


class TestPromoteInterruptedRowsPromotion:
    def test_promotes_single_interrupted_feature(self):
        feat = _make_feature()
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            result = promote_interrupted_rows("proj-abc")
        mock_db.update_feature.assert_called_once_with(feat.id, status="ready")
        assert result == [feat.id]

    def test_promotes_multiple_interrupted_features(self):
        feats = [
            _make_feature(feature_id=f"feat000{i}-0000-0000-0000-000000000001", name=f"F{i}")
            for i in range(3)
        ]
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = feats
            mock_db.update_feature.return_value = None
            result = promote_interrupted_rows("proj-multi")
        assert len(result) == 3
        assert set(result) == {f.id for f in feats}

    def test_returns_empty_list_when_no_interrupted_features(self):
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = promote_interrupted_rows("proj-empty")
        assert result == []

    def test_queries_by_interrupted_status(self):
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            promote_interrupted_rows("proj-xyz")
        mock_db.list_features.assert_called_once_with(
            project_id="proj-xyz", status="interrupted"
        )

    def test_sets_status_to_ready(self):
        feat = _make_feature(feature_id="aaaa0001-0000-0000-0000-000000000001")
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            promote_interrupted_rows("proj-z")
        args, kwargs = mock_db.update_feature.call_args
        assert args[0] == feat.id
        assert kwargs.get("status") == "ready"


class TestPromoteInterruptedRowsErrorHandling:
    def test_list_features_db_error_returns_empty(self):
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = Exception("DB locked")
            result = promote_interrupted_rows("proj-err")
        assert result == []

    def test_update_feature_db_error_skips_feature(self):
        feat1 = _make_feature(
            feature_id="feat0001-0000-0000-0000-000000000001", name="F1"
        )
        feat2 = _make_feature(
            feature_id="feat0002-0000-0000-0000-000000000001", name="F2"
        )
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat1, feat2]
            mock_db.update_feature.side_effect = [Exception("constraint"), None]
            result = promote_interrupted_rows("proj-partial")
        assert result == [feat2.id]

    def test_list_features_exception_does_not_propagate(self):
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = RuntimeError("unexpected")
            result = promote_interrupted_rows("proj-safe")
        assert result == []

    def test_update_exception_does_not_propagate(self):
        feat = _make_feature()
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.side_effect = RuntimeError("disk full")
            result = promote_interrupted_rows("proj-safe2")
        assert result == []


class TestPromoteInterruptedRowsLogging:
    def test_logs_info_for_each_promoted_feature(self, caplog):
        feat = _make_feature(
            feature_id="feat0001-0000-0000-0000-000000000001", name="Sticky-completed gate"
        )
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            with caplog.at_level(logging.INFO, logger="bob3.periodic_resume_scan"):
                promote_interrupted_rows("proj-log")
        assert any("promote_interrupted_rows" in r.message for r in caplog.records)
        assert any(feat.id in r.message for r in caplog.records)

    def test_logs_debug_on_list_features_failure(self, caplog):
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = Exception("DB error")
            with caplog.at_level(logging.DEBUG, logger="bob3.periodic_resume_scan"):
                promote_interrupted_rows("proj-dbg")
        assert any("promote_interrupted_rows" in r.message for r in caplog.records)


class TestPromoteInterruptedRowsIdempotency:
    def test_multiple_calls_are_safe(self):
        feat = _make_feature()
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            r1 = promote_interrupted_rows("proj-idem")
            r2 = promote_interrupted_rows("proj-idem")
        assert r1 == [feat.id]
        assert r2 == [feat.id]

    def test_empty_project_never_crashes(self):
        with patch("bob3.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            for _ in range(5):
                result = promote_interrupted_rows("proj-empty")
            assert result == []
