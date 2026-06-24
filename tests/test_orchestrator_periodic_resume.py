"""Tests for bob.orchestrator.resume_scan (feature e072706e).

Verifies that the periodic resume scan promotes 'interrupted' features
to 'ready' mid-run without requiring an orchestrator restart.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


PROJECT_ID = "proj-e072706e-0000-0000-0000-000000000001"


def _make_feature(*, feature_id: str, name: str = "Feature", status: str = "interrupted") -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = status
    return f


# ---------------------------------------------------------------------------
# Module-level import
# ---------------------------------------------------------------------------


def test_resume_scan_importable_from_orchestrator():
    """bob.orchestrator.resume_scan must be importable."""
    from bob.orchestrator import resume_scan  # noqa: F401
    assert callable(resume_scan)


def test_resume_scan_importable_from_periodic_resume():
    """bob.orchestrator.periodic_resume.resume_scan must be importable."""
    from bob.orchestrator.periodic_resume import resume_scan  # noqa: F401
    assert callable(resume_scan)


# ---------------------------------------------------------------------------
# Happy path: interrupted features are promoted
# ---------------------------------------------------------------------------


def test_promotes_interrupted_features():
    """resume_scan must promote 'interrupted' features to 'ready'."""
    from bob.orchestrator import resume_scan
    feat = _make_feature(feature_id="feat-aaa-001")
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        result = resume_scan(PROJECT_ID)
    assert result == ["feat-aaa-001"]
    mock_db.update_feature.assert_called_once_with("feat-aaa-001", status="ready")


def test_promotes_multiple_interrupted_features():
    """resume_scan must return all promoted feature IDs."""
    from bob.orchestrator import resume_scan
    feats = [
        _make_feature(feature_id="feat-001"),
        _make_feature(feature_id="feat-002"),
        _make_feature(feature_id="feat-003"),
    ]
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = feats
        mock_db.update_feature.return_value = None
        result = resume_scan(PROJECT_ID)
    assert set(result) == {"feat-001", "feat-002", "feat-003"}
    assert mock_db.update_feature.call_count == 3


def test_returns_empty_when_no_interrupted():
    """resume_scan must return [] when there are no interrupted features."""
    from bob.orchestrator import resume_scan
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_scan(PROJECT_ID)
    assert result == []


# ---------------------------------------------------------------------------
# DB error resilience
# ---------------------------------------------------------------------------


def test_list_features_db_error_returns_empty():
    """resume_scan must return [] (not raise) when list_features fails."""
    from bob.orchestrator import resume_scan
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.side_effect = RuntimeError("db locked")
        result = resume_scan(PROJECT_ID)
    assert result == []


def test_update_feature_db_error_skips_failing_row():
    """When update_feature fails for one row, the rest must still be promoted."""
    from bob.orchestrator import resume_scan
    feats = [
        _make_feature(feature_id="feat-good"),
        _make_feature(feature_id="feat-bad"),
    ]

    def selective_update(fid, **kwargs):
        if fid == "feat-bad":
            raise RuntimeError("lock timeout")

    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = feats
        mock_db.update_feature.side_effect = selective_update
        result = resume_scan(PROJECT_ID)

    assert "feat-good" in result
    assert "feat-bad" not in result


# ---------------------------------------------------------------------------
# Input validation (delegates to underlying function)
# ---------------------------------------------------------------------------


def test_none_project_id_raises_value_error():
    """None project_id must raise ValueError."""
    from bob.orchestrator import resume_scan
    with pytest.raises(ValueError):
        resume_scan(None)  # type: ignore[arg-type]


def test_empty_string_project_id_raises_value_error():
    """Empty string project_id must raise ValueError."""
    from bob.orchestrator import resume_scan
    with pytest.raises(ValueError):
        resume_scan("")


def test_whitespace_only_project_id_raises_value_error():
    """Whitespace-only project_id must raise ValueError."""
    from bob.orchestrator import resume_scan
    with pytest.raises(ValueError):
        resume_scan("   ")


# ---------------------------------------------------------------------------
# Integration: run_loop integration
# ---------------------------------------------------------------------------


def test_run_loop_imports_periodic_resume_scan():
    """run_loop must import periodic_resume_scan (integration AC)."""
    import importlib
    import sys
    # Verify the module is importable
    mod = importlib.import_module("bob.orchestrator.run_loop")
    # Check the integration is wired: either via attribute or confirmed import
    assert hasattr(mod, "periodic_resume_scan") or "periodic_resume_scan" in dir(mod) or \
        "periodic_resume_scan" in str(getattr(mod, "__file__", ""))


def test_resume_scan_is_callable_from_orchestrator_namespace():
    """bob.orchestrator.resume_scan must be callable."""
    import bob.orchestrator as orch
    assert callable(orch.resume_scan)


def test_resume_scan_returns_list():
    """resume_scan must always return a list."""
    from bob.orchestrator import resume_scan
    with patch("bob.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_scan(PROJECT_ID)
    assert isinstance(result, list)
