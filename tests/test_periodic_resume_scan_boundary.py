"""Boundary tests for bob3.orchestrator.resume_interrupted_work (feature 2d9615ff).

Verifies that empty, zero, or minimum input returns a well-defined result
rather than raising (boundary case AC).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


PROJECT_ID = "proj-boundary-2d9615ff-0000-0000-0000-000000000001"


def _make_feature(*, feature_id: str, name: str = "Feature", status: str = "interrupted") -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = status
    return f


# ---------------------------------------------------------------------------
# Boundary: empty project (no interrupted rows) → returns []
# ---------------------------------------------------------------------------


def test_empty_project_returns_empty_list():
    """Empty project (no interrupted rows) must return [] not raise."""
    from bob3.orchestrator import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_interrupted_work(PROJECT_ID)
    assert result == []


def test_empty_project_repeated_calls_stable():
    """Repeated calls on empty project must never raise and must return []."""
    from bob3.orchestrator import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        for _ in range(5):
            result = resume_interrupted_work(PROJECT_ID)
    assert result == []


# ---------------------------------------------------------------------------
# Boundary: minimum input (exactly one interrupted feature) → returns [id]
# ---------------------------------------------------------------------------


def test_single_interrupted_feature_is_promoted():
    """Single interrupted feature (minimum non-empty case) must be promoted."""
    from bob3.orchestrator import resume_interrupted_work
    feat = _make_feature(feature_id="min-feat-0000-0000-0000-000000000001")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        result = resume_interrupted_work(PROJECT_ID)
    assert result == [feat.id]


def test_single_interrupted_feature_update_called_with_ready():
    """The promotion must set status='ready' for the single feature."""
    from bob3.orchestrator import resume_interrupted_work
    feat = _make_feature(feature_id="min-feat-0001-0000-0000-000000000001")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        resume_interrupted_work(PROJECT_ID)
    mock_db.update_feature.assert_called_once_with(feat.id, status="ready")


# ---------------------------------------------------------------------------
# Boundary: DB transient error on list_features → returns [] not raises
# ---------------------------------------------------------------------------


def test_db_lock_on_list_features_returns_empty():
    """Transient DB lock during list_features must return [] not raise."""
    from bob3.orchestrator import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.side_effect = Exception("DB locked")
        result = resume_interrupted_work(PROJECT_ID)
    assert result == []


def test_runtime_error_on_list_features_returns_empty():
    """RuntimeError during list_features must return [] not propagate."""
    from bob3.orchestrator import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.side_effect = RuntimeError("unexpected")
        result = resume_interrupted_work(PROJECT_ID)
    assert result == []


# ---------------------------------------------------------------------------
# Boundary: partial update failure — remaining features still promoted
# ---------------------------------------------------------------------------


def test_partial_update_failure_promotes_remaining():
    """When one feature's update fails, the rest must still be promoted."""
    from bob3.orchestrator import resume_interrupted_work
    feat1 = _make_feature(feature_id="bound-feat-0001-0000-0000-000000000001", name="F1")
    feat2 = _make_feature(feature_id="bound-feat-0002-0000-0000-000000000001", name="F2")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat1, feat2]
        mock_db.update_feature.side_effect = [Exception("constraint"), None]
        result = resume_interrupted_work(PROJECT_ID)
    assert result == [feat2.id]


# ---------------------------------------------------------------------------
# Boundary: result is always a list (never None)
# ---------------------------------------------------------------------------


def test_result_is_always_a_list():
    """Return value must always be a list, even on empty or error."""
    from bob3.orchestrator import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_interrupted_work(PROJECT_ID)
    assert isinstance(result, list)


def test_result_is_list_on_db_error():
    """Return value must be a list even when list_features raises."""
    from bob3.orchestrator import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.side_effect = Exception("io error")
        result = resume_interrupted_work(PROJECT_ID)
    assert isinstance(result, list)
