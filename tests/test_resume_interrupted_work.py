"""Tests for bob3.orchestrator.run_loop.resume_interrupted_work.

Verifies the module-level periodic resume scan function that promotes
'interrupted' rows mid-run (not only at startup), as required by the
feature AC: "Function defined: orchestrator.run_loop.resume_interrupted_work".
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


PROJECT_ID = "test-proj-9d3609cc-a48a-4058-ad7a-5c59a1b3fb0f"


def _make_feature(*, feature_id: str, name: str = "Feature", status: str = "interrupted") -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = status
    return f


# ---------------------------------------------------------------------------
# Smoke: function is importable from the correct location
# ---------------------------------------------------------------------------


def test_resume_interrupted_work_is_importable():
    """resume_interrupted_work must be importable from bob3.orchestrator.run_loop."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    assert callable(resume_interrupted_work)


# ---------------------------------------------------------------------------
# Happy path: interrupted features are promoted to 'ready'
# ---------------------------------------------------------------------------


def test_returns_empty_list_when_no_interrupted():
    """No interrupted features → returns [] without raising."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_interrupted_work(PROJECT_ID)
    assert result == []


def test_promotes_interrupted_feature_to_ready():
    """Single interrupted feature → promoted and returned."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    feat = _make_feature(feature_id="feat-0001-9d3609cc")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        result = resume_interrupted_work(PROJECT_ID)
    assert result == [feat.id]


def test_calls_update_feature_with_ready_status():
    """Promotion must call update_feature(id, status='ready')."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    feat = _make_feature(feature_id="feat-0002-9d3609cc")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        resume_interrupted_work(PROJECT_ID)
    mock_db.update_feature.assert_called_once_with(feat.id, status="ready")


def test_promotes_multiple_interrupted_features():
    """Multiple interrupted features are all promoted."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    feats = [_make_feature(feature_id=f"feat-000{i}-9d3609cc") for i in range(3)]
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = feats
        mock_db.update_feature.return_value = None
        result = resume_interrupted_work(PROJECT_ID)
    assert sorted(result) == sorted([f.id for f in feats])


# ---------------------------------------------------------------------------
# Error handling: DB transient errors are swallowed
# ---------------------------------------------------------------------------


def test_db_error_on_list_features_returns_empty():
    """DB error during list_features → returns [] not raises."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.side_effect = Exception("DB locked")
        result = resume_interrupted_work(PROJECT_ID)
    assert result == []


def test_partial_update_failure_promotes_remaining():
    """If one feature's update fails, the others are still promoted."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    feat1 = _make_feature(feature_id="feat-partial-1-9d3609cc", name="F1")
    feat2 = _make_feature(feature_id="feat-partial-2-9d3609cc", name="F2")
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat1, feat2]
        mock_db.update_feature.side_effect = [Exception("conflict"), None]
        result = resume_interrupted_work(PROJECT_ID)
    assert result == [feat2.id]


# ---------------------------------------------------------------------------
# Idempotency: successive calls on same project are safe
# ---------------------------------------------------------------------------


def test_successive_calls_are_safe():
    """Repeated calls on the same project must not raise."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        for _ in range(3):
            result = resume_interrupted_work(PROJECT_ID)
        assert result == []


# ---------------------------------------------------------------------------
# Validation: invalid project_id raises ValueError
# ---------------------------------------------------------------------------


def test_none_project_id_raises_value_error():
    """None project_id must raise ValueError."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work(None)  # type: ignore[arg-type]


def test_empty_string_project_id_raises_value_error():
    """Empty string project_id must raise ValueError."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work("")


def test_whitespace_project_id_raises_value_error():
    """Whitespace-only project_id must raise ValueError."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work("   ")


def test_non_string_project_id_raises_value_error():
    """Non-string project_id (int) must raise ValueError."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work(42)  # type: ignore[arg-type]


def test_value_error_raised_before_db_access():
    """ValueError must be raised before any DB call (fast-fail path)."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        with pytest.raises(ValueError):
            resume_interrupted_work("")
        mock_db.list_features.assert_not_called()


# ---------------------------------------------------------------------------
# Return type: always a list
# ---------------------------------------------------------------------------


def test_return_type_is_always_list():
    """Return value must always be a list."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_interrupted_work(PROJECT_ID)
    assert isinstance(result, list)


def test_return_type_is_list_on_db_error():
    """Return value must be a list even when DB raises."""
    from bob3.orchestrator.run_loop import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.side_effect = RuntimeError("io error")
        result = resume_interrupted_work(PROJECT_ID)
    assert isinstance(result, list)
