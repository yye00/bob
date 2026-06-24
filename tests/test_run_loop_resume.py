"""Tests for orchestrator.run_loop.resume_interrupted_work (feature 099abfda).

Verifies that resume_interrupted_work is defined in bob.orchestrator.run_loop
and correctly promotes 'interrupted' features back to 'ready'.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


PROJECT_ID = "proj-runloop-099abfda-0000-0000-0000-000000000001"


def _make_feature(*, feature_id: str, name: str = "Feature") -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = "interrupted"
    return f


# ---------------------------------------------------------------------------
# Function is importable from orchestrator.run_loop
# ---------------------------------------------------------------------------


def test_resume_interrupted_work_is_importable():
    """resume_interrupted_work must be importable from bob.orchestrator.run_loop."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    assert callable(resume_interrupted_work)


# ---------------------------------------------------------------------------
# Basic promotion behaviour
# ---------------------------------------------------------------------------


def test_no_interrupted_features_returns_empty():
    """When no features are interrupted, return []."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_interrupted_work(PROJECT_ID)
    assert result == []


def test_single_interrupted_feature_is_promoted():
    """A single interrupted feature must be promoted to 'ready'."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    feat = _make_feature(feature_id="rl-feat-0001-0000-0000-000000000001")
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        result = resume_interrupted_work(PROJECT_ID)
    assert result == [feat.id]


def test_multiple_interrupted_features_all_promoted():
    """All interrupted features must be promoted and returned."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    feats = [
        _make_feature(feature_id=f"rl-feat-{i:04d}-0000-0000-000000000001")
        for i in range(3)
    ]
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = feats
        mock_db.update_feature.return_value = None
        result = resume_interrupted_work(PROJECT_ID)
    assert result == [f.id for f in feats]


def test_update_called_with_ready_status():
    """Each promoted feature must have update_feature called with status='ready'."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    feat = _make_feature(feature_id="rl-feat-0002-0000-0000-000000000001")
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        resume_interrupted_work(PROJECT_ID)
    mock_db.update_feature.assert_called_once_with(feat.id, status="ready")


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------


def test_db_error_on_list_returns_empty():
    """DB error during list_features must return [] and not raise."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.side_effect = Exception("DB locked")
        result = resume_interrupted_work(PROJECT_ID)
    assert result == []


def test_partial_update_failure_still_promotes_rest():
    """When one feature update fails, the others must still be promoted."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    feat1 = _make_feature(feature_id="rl-feat-0003-0000-0000-000000000001", name="F1")
    feat2 = _make_feature(feature_id="rl-feat-0004-0000-0000-000000000001", name="F2")
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat1, feat2]
        mock_db.update_feature.side_effect = [Exception("constraint"), None]
        result = resume_interrupted_work(PROJECT_ID)
    assert result == [feat2.id]


# ---------------------------------------------------------------------------
# Invalid input raises ValueError
# ---------------------------------------------------------------------------


def test_none_project_id_raises():
    """None project_id must raise ValueError."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work(None)  # type: ignore[arg-type]


def test_empty_string_project_id_raises():
    """Empty string project_id must raise ValueError."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work("")


def test_whitespace_project_id_raises():
    """Whitespace-only project_id must raise ValueError."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work("   ")


def test_integer_project_id_raises():
    """Non-string project_id must raise ValueError."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work(42)  # type: ignore[arg-type]


def test_value_error_mentions_project_id():
    """ValueError message must mention 'project_id'."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    with pytest.raises(ValueError, match="project_id"):
        resume_interrupted_work("")


def test_valid_project_id_returns_list():
    """A valid project_id returns a list (not None)."""
    from bob.orchestrator.run_loop import resume_interrupted_work
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_interrupted_work("valid-proj-099abfda")
    assert isinstance(result, list)
