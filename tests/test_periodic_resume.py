"""Tests for bob3.orchestrator.periodic_resume (feature 5b9da564).

Verifies that resume_interrupted_rows is importable from the module and
behaves correctly — promoting 'interrupted' feature rows to 'ready' mid-run
without requiring an orchestrator restart.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


PROJECT_ID = "proj-5b9da564-e155-4d1b-b06c-cf2eb58efb58"


def _make_feature(*, feature_id: str, name: str = "Feature") -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = "interrupted"
    return f


# ---------------------------------------------------------------------------
# Import checks
# ---------------------------------------------------------------------------


def test_resume_interrupted_rows_importable():
    """resume_interrupted_rows must be importable from the module."""
    from bob3.orchestrator.periodic_resume import resume_interrupted_rows
    assert callable(resume_interrupted_rows)


def test_resume_scan_importable():
    """resume_scan must still be importable (existing API)."""
    from bob3.orchestrator.periodic_resume import resume_scan
    assert callable(resume_scan)


# ---------------------------------------------------------------------------
# resume_interrupted_rows — happy path
# ---------------------------------------------------------------------------


def test_resume_interrupted_rows_promotes_interrupted_features():
    """resume_interrupted_rows must promote interrupted features to 'ready'."""
    from bob3.orchestrator.periodic_resume import resume_interrupted_rows
    feat = _make_feature(feature_id="feat-5b9da564-0001")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        result = resume_interrupted_rows(PROJECT_ID)
    assert result == [feat.id]


def test_resume_interrupted_rows_calls_update_with_ready():
    """resume_interrupted_rows must call update_feature with status='ready'."""
    from bob3.orchestrator.periodic_resume import resume_interrupted_rows
    feat = _make_feature(feature_id="feat-5b9da564-0002")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        resume_interrupted_rows(PROJECT_ID)
    mock_db.update_feature.assert_called_once_with(feat.id, status="ready")


def test_resume_interrupted_rows_returns_list_when_empty():
    """resume_interrupted_rows must return [] when no interrupted features."""
    from bob3.orchestrator.periodic_resume import resume_interrupted_rows
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_interrupted_rows(PROJECT_ID)
    assert result == []


def test_resume_interrupted_rows_promotes_multiple_features():
    """resume_interrupted_rows must promote all interrupted features."""
    from bob3.orchestrator.periodic_resume import resume_interrupted_rows
    feat1 = _make_feature(feature_id="feat-5b9da564-0003", name="F1")
    feat2 = _make_feature(feature_id="feat-5b9da564-0004", name="F2")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat1, feat2]
        mock_db.update_feature.return_value = None
        result = resume_interrupted_rows(PROJECT_ID)
    assert set(result) == {feat1.id, feat2.id}


# ---------------------------------------------------------------------------
# resume_interrupted_rows — error / validation
# ---------------------------------------------------------------------------


def test_resume_interrupted_rows_raises_on_empty_project_id():
    """resume_interrupted_rows must raise ValueError for empty project_id."""
    from bob3.orchestrator.periodic_resume import resume_interrupted_rows
    with pytest.raises(ValueError):
        resume_interrupted_rows("")


def test_resume_interrupted_rows_raises_on_none_project_id():
    """resume_interrupted_rows must raise ValueError for None project_id."""
    from bob3.orchestrator.periodic_resume import resume_interrupted_rows
    with pytest.raises(ValueError):
        resume_interrupted_rows(None)  # type: ignore[arg-type]


def test_resume_interrupted_rows_raises_on_whitespace_project_id():
    """resume_interrupted_rows must raise ValueError for whitespace-only project_id."""
    from bob3.orchestrator.periodic_resume import resume_interrupted_rows
    with pytest.raises(ValueError):
        resume_interrupted_rows("   ")


def test_resume_interrupted_rows_swallows_db_error():
    """resume_interrupted_rows must return [] when list_features raises, not propagate."""
    from bob3.orchestrator.periodic_resume import resume_interrupted_rows
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.side_effect = Exception("DB locked")
        result = resume_interrupted_rows(PROJECT_ID)
    assert result == []


# ---------------------------------------------------------------------------
# resume_interrupted_rows — consistency with resume_scan
# ---------------------------------------------------------------------------


def test_resume_interrupted_rows_same_result_as_resume_scan():
    """resume_interrupted_rows and resume_scan must return the same result."""
    from bob3.orchestrator.periodic_resume import resume_interrupted_rows, resume_scan
    feat = _make_feature(feature_id="feat-5b9da564-0005")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        r1 = resume_interrupted_rows(PROJECT_ID)
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        r2 = resume_scan(PROJECT_ID)
    assert r1 == r2


# ---------------------------------------------------------------------------
# run_loop integration: periodic_resume_scan call is wired into the loop
# ---------------------------------------------------------------------------


def test_run_loop_imports_periodic_resume_scan():
    """run_loop must import periodic_resume_scan (integration AC)."""
    import bob3.orchestrator.run_loop as rl
    assert hasattr(rl, "periodic_resume_scan") or hasattr(rl, "_periodic_resume_scan")


def test_resume_interrupted_rows_in_module_all():
    """resume_interrupted_rows must be in __all__ of periodic_resume."""
    import bob3.orchestrator.periodic_resume as m
    assert "resume_interrupted_rows" in m.__all__
