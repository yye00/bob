"""Tests for bob.resume_scanner.scan_and_promote_interrupted (feature 89c6e29f).

Covers the canonical public entry point for the periodic resume scan:
- Normal promotion of interrupted features to 'ready'
- ValueError for invalid project_id inputs
- Graceful handling of DB errors
- Idempotency and partial-failure resilience
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


MODULE = "bob.resume_scanner"


def _make_feature(*, feature_id: str, name: str = "Feature", status: str = "interrupted") -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = name
    f.status = status
    return f


PROJECT_ID = "proj-89c6e29f-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Import and basic existence
# ---------------------------------------------------------------------------


def test_module_importable():
    import bob.resume_scanner  # noqa: F401


def test_function_defined():
    from bob.resume_scanner import scan_and_promote_interrupted
    assert callable(scan_and_promote_interrupted)


# ---------------------------------------------------------------------------
# Normal promotion cases
# ---------------------------------------------------------------------------


def test_promotes_single_interrupted_feature():
    from bob.resume_scanner import scan_and_promote_interrupted
    feat = _make_feature(feature_id="feat-0001-0000-0000-000000000001")
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == [feat.id]


def test_promotes_multiple_interrupted_features():
    from bob.resume_scanner import scan_and_promote_interrupted
    feats = [_make_feature(feature_id=f"feat-{i:04d}-0000-0000-0000-000000000001") for i in range(3)]
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.return_value = feats
        mock_db.update_feature.return_value = None
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == [f.id for f in feats]


def test_update_called_with_ready_status():
    from bob.resume_scanner import scan_and_promote_interrupted
    feat = _make_feature(feature_id="feat-update-0000-0000-0000-000000000001")
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        scan_and_promote_interrupted(PROJECT_ID)
    mock_db.update_feature.assert_called_once_with(feat.id, status="ready")


def test_queries_interrupted_status():
    from bob.resume_scanner import scan_and_promote_interrupted
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.return_value = []
        scan_and_promote_interrupted(PROJECT_ID)
    mock_db.list_features.assert_called_once_with(project_id=PROJECT_ID, status="interrupted")


def test_empty_project_returns_empty_list():
    from bob.resume_scanner import scan_and_promote_interrupted
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.return_value = []
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == []


def test_return_type_is_always_list():
    from bob.resume_scanner import scan_and_promote_interrupted
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.return_value = []
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# ValueError for invalid project_id
# ---------------------------------------------------------------------------


def test_none_project_id_raises_value_error():
    from bob.resume_scanner import scan_and_promote_interrupted
    with pytest.raises(ValueError):
        scan_and_promote_interrupted(None)  # type: ignore[arg-type]


def test_empty_string_raises_value_error():
    from bob.resume_scanner import scan_and_promote_interrupted
    with pytest.raises(ValueError):
        scan_and_promote_interrupted("")


def test_whitespace_only_raises_value_error():
    from bob.resume_scanner import scan_and_promote_interrupted
    with pytest.raises(ValueError):
        scan_and_promote_interrupted("   ")


def test_integer_project_id_raises_value_error():
    from bob.resume_scanner import scan_and_promote_interrupted
    with pytest.raises(ValueError):
        scan_and_promote_interrupted(42)  # type: ignore[arg-type]


def test_list_project_id_raises_value_error():
    from bob.resume_scanner import scan_and_promote_interrupted
    with pytest.raises(ValueError):
        scan_and_promote_interrupted(["proj-id"])  # type: ignore[arg-type]


def test_value_error_message_mentions_project_id():
    from bob.resume_scanner import scan_and_promote_interrupted
    with pytest.raises(ValueError, match="project_id"):
        scan_and_promote_interrupted("")


def test_value_error_raised_before_db_access():
    from bob.resume_scanner import scan_and_promote_interrupted
    with patch(f"{MODULE}.db") as mock_db:
        with pytest.raises(ValueError):
            scan_and_promote_interrupted("")
        mock_db.list_features.assert_not_called()


# ---------------------------------------------------------------------------
# DB error resilience
# ---------------------------------------------------------------------------


def test_db_error_on_list_features_returns_empty():
    from bob.resume_scanner import scan_and_promote_interrupted
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.side_effect = Exception("DB locked")
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == []


def test_runtime_error_on_list_features_returns_empty():
    from bob.resume_scanner import scan_and_promote_interrupted
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.side_effect = RuntimeError("unexpected")
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == []


def test_db_error_on_list_features_returns_list_type():
    from bob.resume_scanner import scan_and_promote_interrupted
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.side_effect = Exception("io error")
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Partial failure resilience
# ---------------------------------------------------------------------------


def test_partial_update_failure_promotes_remaining():
    from bob.resume_scanner import scan_and_promote_interrupted
    feat1 = _make_feature(feature_id="feat-partial-0001-0000-0000-000000000001", name="F1")
    feat2 = _make_feature(feature_id="feat-partial-0002-0000-0000-000000000001", name="F2")
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.return_value = [feat1, feat2]
        mock_db.update_feature.side_effect = [Exception("constraint"), None]
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == [feat2.id]


def test_all_updates_fail_returns_empty():
    from bob.resume_scanner import scan_and_promote_interrupted
    feats = [_make_feature(feature_id=f"feat-fail-{i:04d}-0000-0000-0000-000000000001") for i in range(3)]
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.return_value = feats
        mock_db.update_feature.side_effect = Exception("all fail")
        result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_repeated_calls_on_empty_project_stable():
    from bob.resume_scanner import scan_and_promote_interrupted
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.return_value = []
        for _ in range(5):
            result = scan_and_promote_interrupted(PROJECT_ID)
    assert result == []


def test_uuid_project_id_accepted():
    from bob.resume_scanner import scan_and_promote_interrupted
    with patch(f"{MODULE}.db") as mock_db:
        mock_db.list_features.return_value = []
        result = scan_and_promote_interrupted("89c6e29f-7d60-4e41-bc67-ee7177d3898f")
    assert isinstance(result, list)
