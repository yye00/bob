"""Tests for bob3.orchestrator.resume_scan (87f0d6aa).

Verifies:
- resume_scan is importable from bob3.orchestrator.resume_scan
- It promotes 'interrupted' features to 'ready'
- It returns the list of promoted feature IDs
- It skips features that fail to update (DB errors)
- It handles empty/zero input gracefully (boundary case)
- It raises ValueError for invalid input (not silently succeed)
- It is integrated into bob3.orchestrator.run_loop
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.orchestrator.resume_scan import resume_scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature(
    *,
    feature_id: str = "87f0d6aa-0000-0000-0000-000000000001",
    name: str = "Sticky-completed gate",
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


class TestResumeScanImport:
    def test_function_is_importable(self):
        from bob3.orchestrator.resume_scan import resume_scan as fn  # noqa: F401

        assert callable(fn)

    def test_accepts_project_id_returns_list(self):
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = resume_scan("proj-87f0d6aa")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Happy-path promotion
# ---------------------------------------------------------------------------


class TestResumeScanPromotion:
    def test_promotes_single_interrupted_feature(self):
        feat = _make_feature()
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            result = resume_scan("proj-abc")
        mock_db.update_feature.assert_called_once_with(feat.id, status="ready")
        assert result == [feat.id]

    def test_promotes_multiple_interrupted_features(self):
        feats = [
            _make_feature(
                feature_id=f"87f0d6aa-0000-0000-0000-{i:012d}", name=f"F{i}"
            )
            for i in range(3)
        ]
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = feats
            mock_db.update_feature.return_value = None
            result = resume_scan("proj-multi")
        assert len(result) == 3
        assert set(result) == {f.id for f in feats}

    def test_queries_by_interrupted_status(self):
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            resume_scan("proj-xyz")
        mock_db.list_features.assert_called_once_with(
            project_id="proj-xyz", status="interrupted"
        )

    def test_sets_status_to_ready(self):
        feat = _make_feature(feature_id="87f0d6aa-0000-0000-0000-000000000002")
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            resume_scan("proj-z")
        args, kwargs = mock_db.update_feature.call_args
        assert args[0] == feat.id
        assert kwargs.get("status") == "ready"


# ---------------------------------------------------------------------------
# Boundary case: empty / zero input
# AC: "Periodic resume scan handles the boundary case of empty or zero input
#      by returning a well-defined result rather than crashing"
# ---------------------------------------------------------------------------


class TestResumeScanBoundary:
    def test_empty_project_returns_empty_list(self):
        """No features in project — must return [] without crashing."""
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = resume_scan("proj-empty")
        assert result == []

    def test_multiple_calls_on_empty_project_never_crash(self):
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            for _ in range(5):
                result = resume_scan("proj-empty")
            assert result == []

    def test_empty_list_returned_not_none(self):
        """Must return a list object, not None, on empty input."""
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = resume_scan("proj-zero")
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Invalid input — must raise ValueError, not silently succeed
# AC: "Periodic resume scan raises a ValueError or returns a rejection when
#      given invalid input, and does not silently succeed"
# ---------------------------------------------------------------------------


class TestResumeScanInvalidInput:
    def test_empty_string_project_id_raises_value_error(self):
        with pytest.raises(ValueError):
            resume_scan("")

    def test_whitespace_only_project_id_raises_value_error(self):
        with pytest.raises(ValueError):
            resume_scan("   ")

    def test_none_project_id_raises_value_error(self):
        with pytest.raises(ValueError):
            resume_scan(None)  # type: ignore[arg-type]

    def test_integer_project_id_raises_value_error(self):
        with pytest.raises(ValueError):
            resume_scan(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestResumeScanErrorHandling:
    def test_list_features_db_error_returns_empty(self):
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = Exception("DB locked")
            result = resume_scan("proj-err")
        assert result == []

    def test_update_feature_db_error_skips_feature(self):
        feat1 = _make_feature(
            feature_id="87f0d6aa-0000-0000-0000-000000000010", name="F1"
        )
        feat2 = _make_feature(
            feature_id="87f0d6aa-0000-0000-0000-000000000020", name="F2"
        )
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat1, feat2]
            mock_db.update_feature.side_effect = [Exception("constraint"), None]
            result = resume_scan("proj-partial")
        assert result == [feat2.id]

    def test_all_updates_fail_returns_empty(self):
        feats = [
            _make_feature(feature_id=f"87f0d6aa-0000-0000-0000-{i:012d}")
            for i in range(1, 3)
        ]
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = feats
            mock_db.update_feature.side_effect = Exception("busy")
            result = resume_scan("proj-all-fail")
        assert result == []

    def test_list_features_exception_does_not_propagate(self):
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = RuntimeError("unexpected")
            result = resume_scan("proj-safe")
        assert result == []

    def test_update_exception_does_not_propagate(self):
        feat = _make_feature()
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.side_effect = RuntimeError("disk full")
            result = resume_scan("proj-safe2")
        assert result == []


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestResumeScanLogging:
    def test_logs_info_for_each_promoted_feature(self, caplog):
        feat = _make_feature()
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            with caplog.at_level(
                logging.INFO, logger="bob3.orchestrator.resume_scan"
            ):
                resume_scan("proj-log")
        assert any("resume_scan" in r.message for r in caplog.records)
        assert any(feat.id in r.message for r in caplog.records)

    def test_logs_debug_on_list_features_failure(self, caplog):
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = Exception("DB error")
            with caplog.at_level(
                logging.DEBUG, logger="bob3.orchestrator.resume_scan"
            ):
                resume_scan("proj-dbg")
        assert any("resume_scan" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestResumeScanIdempotency:
    def test_multiple_calls_are_safe(self):
        feat = _make_feature()
        with patch("bob3.orchestrator.resume_scan.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            r1 = resume_scan("proj-idem")
            r2 = resume_scan("proj-idem")
        assert r1 == [feat.id]
        assert r2 == [feat.id]


# ---------------------------------------------------------------------------
# Fixture file: tests/fixtures/interrupted_feature.json
# AC: "File exists: tests/fixtures/interrupted_feature.json"
# ---------------------------------------------------------------------------


class TestFixtureFile:
    def test_interrupted_feature_json_fixture_exists(self):
        fixture_path = (
            Path(__file__).parent / "fixtures" / "interrupted_feature.json"
        )
        assert fixture_path.exists(), (
            f"Missing fixture: {fixture_path}. "
            "Create tests/fixtures/interrupted_feature.json."
        )

    def test_interrupted_feature_json_is_valid_json(self):
        fixture_path = (
            Path(__file__).parent / "fixtures" / "interrupted_feature.json"
        )
        data = json.loads(fixture_path.read_text())
        assert isinstance(data, dict)

    def test_interrupted_feature_json_has_required_keys(self):
        fixture_path = (
            Path(__file__).parent / "fixtures" / "interrupted_feature.json"
        )
        data = json.loads(fixture_path.read_text())
        assert "id" in data
        assert "status" in data
        assert data["status"] == "interrupted"


# ---------------------------------------------------------------------------
# Integration: bob3.orchestrator.run_loop
# AC: "integration: bob3.orchestrator.run_loop"
# ---------------------------------------------------------------------------


class TestRunLoopIntegration:
    def test_run_loop_exposes_periodic_resume_scan(self):
        import bob3.orchestrator.run_loop as rl

        assert hasattr(rl, "periodic_resume_scan") or hasattr(
            rl, "_periodic_resume_scan"
        ), (
            "run_loop must expose periodic_resume_scan (or _periodic_resume_scan) "
            "so it can be called on each orchestrator tick"
        )

    def test_run_loop_periodic_resume_scan_is_callable(self):
        import bob3.orchestrator.run_loop as rl

        fn = getattr(rl, "periodic_resume_scan", None) or getattr(
            rl, "_periodic_resume_scan", None
        )
        assert callable(fn)

    def test_resume_scan_module_accessible_from_orchestrator(self):
        from bob3.orchestrator import resume_scan as mod  # noqa: F401

        assert hasattr(mod, "resume_scan")
        assert callable(mod.resume_scan)
