"""Tests for bob3.periodic_resume_scanner.scan_and_promote_interrupted.

Verifies that interrupted features are promoted to 'ready' on each tick,
that DB errors are handled gracefully, and that invalid inputs raise ValueError.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


def _make_feature(*, feature_id: str, name: str = "Feature", status: str = "interrupted") -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = status
    return f


PROJECT_ID = "test-project-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Import and function existence
# ---------------------------------------------------------------------------


def test_module_importable():
    """bob3.periodic_resume_scanner must be importable."""
    import bob3.periodic_resume_scanner  # noqa: F401


def test_scan_and_promote_interrupted_is_callable():
    """scan_and_promote_interrupted must be a callable."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    assert callable(scan_and_promote_interrupted)


# ---------------------------------------------------------------------------
# Core promotion behaviour
# ---------------------------------------------------------------------------


def test_no_interrupted_features_returns_empty_list():
    """When no interrupted features exist, returns empty list."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    with patch("bob3.periodic_resume_scanner.db") as mock_db:
        mock_db.list_features.return_value = []
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == []


def test_single_interrupted_feature_promoted_to_ready():
    """A single interrupted feature is promoted to 'ready'."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    feat = _make_feature(feature_id="feat-0001")
    with patch("bob3.periodic_resume_scanner.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == [feat.id]
    mock_db.update_feature.assert_called_once_with(feat.id, status="ready")


def test_multiple_interrupted_features_all_promoted():
    """Multiple interrupted features are all promoted."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    feats = [
        _make_feature(feature_id=f"feat-{i:04d}", name=f"F{i}")
        for i in range(3)
    ]
    with patch("bob3.periodic_resume_scanner.db") as mock_db:
        mock_db.list_features.return_value = feats
        mock_db.update_feature.return_value = None
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == [f.id for f in feats]
    assert mock_db.update_feature.call_count == 3


def test_list_features_called_with_interrupted_status():
    """list_features must be called with status='interrupted'."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    with patch("bob3.periodic_resume_scanner.db") as mock_db:
        mock_db.list_features.return_value = []
        scan_and_promote_interrupted(PROJECT_ID)
    mock_db.list_features.assert_called_once_with(project_id=PROJECT_ID, status="interrupted")


def test_returns_list_type():
    """Return value is always a list."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    with patch("bob3.periodic_resume_scanner.db") as mock_db:
        mock_db.list_features.return_value = []
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# DB error resilience
# ---------------------------------------------------------------------------


def test_db_list_features_error_returns_empty():
    """When list_features raises, returns [] instead of propagating."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    with patch("bob3.periodic_resume_scanner.db") as mock_db:
        mock_db.list_features.side_effect = Exception("DB locked")
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == []


def test_db_update_error_on_one_feature_continues_others():
    """When update_feature fails for one feature, remaining are still promoted."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    feat1 = _make_feature(feature_id="feat-err-0001", name="F1")
    feat2 = _make_feature(feature_id="feat-ok-0002", name="F2")
    with patch("bob3.periodic_resume_scanner.db") as mock_db:
        mock_db.list_features.return_value = [feat1, feat2]
        mock_db.update_feature.side_effect = [Exception("constraint"), None]
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == [feat2.id]


def test_all_update_errors_returns_empty():
    """When all update_feature calls fail, returns []."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    feats = [_make_feature(feature_id=f"feat-{i:04d}") for i in range(2)]
    with patch("bob3.periodic_resume_scanner.db") as mock_db:
        mock_db.list_features.return_value = feats
        mock_db.update_feature.side_effect = Exception("all fail")
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == []


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_none_project_id_raises_value_error():
    """None project_id raises ValueError."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    with pytest.raises(ValueError):
        scan_and_promote_interrupted(None)  # type: ignore[arg-type]


def test_empty_string_project_id_raises_value_error():
    """Empty string project_id raises ValueError."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    with pytest.raises(ValueError):
        scan_and_promote_interrupted("")


def test_whitespace_project_id_raises_value_error():
    """Whitespace-only project_id raises ValueError."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    with pytest.raises(ValueError):
        scan_and_promote_interrupted("   ")


def test_integer_project_id_raises_value_error():
    """Non-string project_id raises ValueError."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    with pytest.raises(ValueError):
        scan_and_promote_interrupted(42)  # type: ignore[arg-type]


def test_value_error_raised_before_db_access():
    """ValueError is raised before any DB access."""
    from bob3.periodic_resume_scanner import scan_and_promote_interrupted
    with patch("bob3.periodic_resume_scanner.db") as mock_db:
        with pytest.raises(ValueError):
            scan_and_promote_interrupted("")
        mock_db.list_features.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: orchestrator integration check
# ---------------------------------------------------------------------------


def test_orchestrator_exposes_resume_interrupted_work():
    """bob3.orchestrator must expose resume_interrupted_work."""
    from bob3.orchestrator import resume_interrupted_work
    assert callable(resume_interrupted_work)


def test_orchestrator_periodic_resume_scan_exposes_scan_and_promote():
    """bob3.orchestrator.periodic_resume_scan must expose scan_and_promote_interrupted alias."""
    from bob3.orchestrator import periodic_resume_scan
    assert hasattr(periodic_resume_scan, "scan_and_promote_interrupted")
