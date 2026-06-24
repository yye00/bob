"""Tests for periodic_resume_scan_promote_interrupted_rows_mid_run_not (191a16e2).

Verifies that `periodic_resume_scan_promote_interrupted_rows_mid_run_not` in
`bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not` promotes
'interrupted' features to 'ready' mid-run, not only at startup.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest


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


def test_periodic_resume_scan_promote_interrupted_rows_mid_run_not():
    """Primary AC test: function is importable, callable, and promotes interrupted rows."""
    from bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not import (
        periodic_resume_scan_promote_interrupted_rows_mid_run_not as fn,
    )

    assert callable(fn)

    feat = _make_feature()
    with patch(
        "bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not.db"
    ) as mock_db:
        mock_db.list_features.return_value = [feat]
        mock_db.update_feature.return_value = None
        result = fn("proj-test")

    mock_db.list_features.assert_called_once_with(
        project_id="proj-test", status="interrupted"
    )
    mock_db.update_feature.assert_called_once_with(feat.id, status="ready")
    assert result == [feat.id]


class TestPeriodicResumeScanPromoteInterruptedRowsMidRunNot:
    def test_returns_empty_when_no_interrupted(self):
        from bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not import (
            periodic_resume_scan_promote_interrupted_rows_mid_run_not as fn,
        )

        with patch(
            "bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not.db"
        ) as mock_db:
            mock_db.list_features.return_value = []
            result = fn("proj-empty")
        assert result == []

    def test_promotes_multiple_interrupted_features(self):
        from bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not import (
            periodic_resume_scan_promote_interrupted_rows_mid_run_not as fn,
        )

        feats = [
            _make_feature(
                feature_id=f"feat000{i}-0000-0000-0000-000000000001", name=f"F{i}"
            )
            for i in range(3)
        ]
        with patch(
            "bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not.db"
        ) as mock_db:
            mock_db.list_features.return_value = feats
            mock_db.update_feature.return_value = None
            result = fn("proj-multi")

        assert len(result) == 3
        assert set(result) == {f.id for f in feats}

    def test_list_features_error_returns_empty(self):
        from bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not import (
            periodic_resume_scan_promote_interrupted_rows_mid_run_not as fn,
        )

        with patch(
            "bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not.db"
        ) as mock_db:
            mock_db.list_features.side_effect = Exception("DB locked")
            result = fn("proj-err")
        assert result == []

    def test_update_error_skips_feature_continues(self):
        from bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not import (
            periodic_resume_scan_promote_interrupted_rows_mid_run_not as fn,
        )

        feat1 = _make_feature(
            feature_id="feat0001-0000-0000-0000-000000000001", name="F1"
        )
        feat2 = _make_feature(
            feature_id="feat0002-0000-0000-0000-000000000001", name="F2"
        )
        with patch(
            "bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not.db"
        ) as mock_db:
            mock_db.list_features.return_value = [feat1, feat2]
            mock_db.update_feature.side_effect = [Exception("constraint"), None]
            result = fn("proj-partial")

        assert result == [feat2.id]

    def test_does_not_propagate_exceptions(self):
        from bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not import (
            periodic_resume_scan_promote_interrupted_rows_mid_run_not as fn,
        )

        with patch(
            "bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not.db"
        ) as mock_db:
            mock_db.list_features.side_effect = RuntimeError("unexpected")
            result = fn("proj-safe")
        assert result == []

    def test_logs_info_on_promotion(self, caplog):
        from bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not import (
            periodic_resume_scan_promote_interrupted_rows_mid_run_not as fn,
        )

        feat = _make_feature(
            feature_id="feat0001-0000-0000-0000-000000000001",
            name="Interrupted Feature",
        )
        module = "bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not"
        with patch(f"{module}.db") as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            with caplog.at_level(logging.INFO, logger=module):
                fn("proj-log")

        assert any(feat.id in r.message for r in caplog.records)

    def test_idempotent_multiple_calls(self):
        from bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not import (
            periodic_resume_scan_promote_interrupted_rows_mid_run_not as fn,
        )

        feat = _make_feature()
        with patch(
            "bob3.periodic_resume_scan_promote_interrupted_rows_mid_run_not.db"
        ) as mock_db:
            mock_db.list_features.return_value = [feat]
            mock_db.update_feature.return_value = None
            r1 = fn("proj-idem")
            r2 = fn("proj-idem")
        assert r1 == [feat.id]
        assert r2 == [feat.id]
