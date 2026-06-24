"""Tests for bob3.orchestrator.resume_interrupted_work (feature 2d9615ff).

Verifies:
- resume_interrupted_work is defined in bob3.orchestrator
- It promotes 'interrupted' features to 'ready' on every loop tick
- Integration with bob3.orchestrator.run_loop
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


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


PROJECT_ID = "proj-test-2d9615ff-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# AC: Function defined: bob3.orchestrator.resume_interrupted_work
# ---------------------------------------------------------------------------


class TestResumeInterruptedWorkDefined:
    def test_function_exists_in_orchestrator(self):
        orchestrator = importlib.import_module("bob3.orchestrator")
        assert hasattr(orchestrator, "resume_interrupted_work"), (
            "bob3.orchestrator must expose 'resume_interrupted_work' as a "
            "public module-level function"
        )

    def test_function_is_callable(self):
        from bob3.orchestrator import resume_interrupted_work
        assert callable(resume_interrupted_work)

    def test_function_accepts_project_id(self):
        from bob3.orchestrator import resume_interrupted_work
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = resume_interrupted_work(PROJECT_ID)
        assert isinstance(result, list)

    def test_importable_directly(self):
        from bob3.orchestrator import resume_interrupted_work as fn  # noqa: F401
        assert fn is not None


# ---------------------------------------------------------------------------
# AC: pytest: tests/test_orchestrator_resume.py::test_interrupted_rows_promoted_on_loop_tick
# ---------------------------------------------------------------------------


def test_interrupted_rows_promoted_on_loop_tick():
    """Interrupted rows must be promoted to 'ready' on each orchestrator tick."""
    from bob3.orchestrator import resume_interrupted_work

    feat = _make_feature(feature_id="tick-feat-0001", name="Sticky-completed gate")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        result = resume_interrupted_work(PROJECT_ID)

    mock_db.update_feature.assert_called_once_with(feat.id, status="ready")
    assert result == [feat.id], (
        "resume_interrupted_work must return the list of promoted feature IDs"
    )


# ---------------------------------------------------------------------------
# AC: integration: bob3.orchestrator.run_loop
# ---------------------------------------------------------------------------


class TestRunLoopIntegration:
    def test_periodic_resume_scan_imported_in_run_loop(self):
        run_loop = importlib.import_module("bob3.orchestrator.run_loop")
        assert hasattr(run_loop, "_periodic_resume_scan"), (
            "run_loop must import periodic_resume_scan as _periodic_resume_scan "
            "for periodic resume to be wired into the orchestrator tick"
        )

    def test_run_loop_has_periodic_resume_scan_function(self):
        run_loop = importlib.import_module("bob3.orchestrator.run_loop")
        assert hasattr(run_loop, "periodic_resume_scan"), (
            "run_loop must expose periodic_resume_scan as a public function"
        )

    def test_orchestrator_package_exposes_resume_interrupted_work(self):
        orchestrator = importlib.import_module("bob3.orchestrator")
        assert callable(orchestrator.resume_interrupted_work)


# ---------------------------------------------------------------------------
# Promotion behaviour
# ---------------------------------------------------------------------------


class TestResumeInterruptedWorkBehaviour:
    def test_returns_empty_when_no_interrupted_features(self):
        from bob3.orchestrator import resume_interrupted_work
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            result = resume_interrupted_work(PROJECT_ID)
        assert result == []

    def test_promotes_multiple_interrupted_features(self):
        from bob3.orchestrator import resume_interrupted_work
        feats = [
            _make_feature(feature_id=f"feat000{i}-0000-0000-0000-000000000001", name=f"F{i}")
            for i in range(3)
        ]
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = feats
            mock_db.update_feature.return_value = None
            result = resume_interrupted_work(PROJECT_ID)
        assert len(result) == 3
        assert set(result) == {f.id for f in feats}

    def test_queries_interrupted_status(self):
        from bob3.orchestrator import resume_interrupted_work
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.return_value = []
            resume_interrupted_work(PROJECT_ID)
        mock_db.list_features.assert_called_once_with(
            project_id=PROJECT_ID, status="interrupted"
        )

    def test_db_error_returns_empty_not_raises(self):
        from bob3.orchestrator import resume_interrupted_work
        with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
            mock_db.list_features.side_effect = Exception("DB locked")
            result = resume_interrupted_work(PROJECT_ID)
        assert result == []
