"""Tests that _resume_interrupted_work_periodic handles DB errors gracefully.

If the DB is locked (sqlite3.OperationalError), raises an exception during
list_features, or update_feature fails, the function must not propagate the
exception — it should log and return a partial (or empty) result list.

This mirrors the behavior of the stuck-executing reaper and zombie-run reaper
in run_loop.py: each periodic sweep is wrapped in try/except so that a
transient DB failure doesn't crash the orchestrator loop.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from bob.orchestrator.run_loop import _resume_interrupted_work_periodic


def _feature(fid: str = "lock0001-0000-0000-0000-000000000001") -> MagicMock:
    f = MagicMock()
    f.id = fid
    f.name = "locked-db-feature"
    f.status = "interrupted"
    return f


class TestPeriodicResumeHandlesLockedDbGracefully:
    def test_list_features_raises_operational_error_returns_empty(self):
        """If list_features raises OperationalError, function returns [] without propagating."""
        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = sqlite3.OperationalError("database is locked")
            result = _resume_interrupted_work_periodic("proj-1")

        assert result == []

    def test_update_feature_raises_operational_error_is_caught(self):
        """If update_feature raises OperationalError, function should not propagate it."""
        feat = _feature()
        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feat] if status == "interrupted" else []
            )
            mock_db.update_feature.side_effect = sqlite3.OperationalError("database is locked")
            try:
                result = _resume_interrupted_work_periodic("proj-1")
            except sqlite3.OperationalError:
                pytest.fail("OperationalError from update_feature was not caught")

    def test_generic_exception_from_list_features_returns_empty(self):
        """If list_features raises a generic exception, function returns [] gracefully."""
        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = RuntimeError("unexpected db failure")
            result = _resume_interrupted_work_periodic("proj-1")

        assert result == []

    def test_partial_failure_in_update_returns_successfully_promoted(self):
        """If update_feature fails for one feature, successfully promoted IDs are returned."""
        feat_ok = _feature("lock0001-0000-0000-0000-000000000001")
        feat_fail = _feature("lock0002-0000-0000-0000-000000000002")
        feats = [feat_ok, feat_fail]

        call_n = {"n": 0}

        def update_side_effect(fid, **kwargs):
            call_n["n"] += 1
            if fid == feat_fail.id:
                raise sqlite3.OperationalError("database is locked")

        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = lambda project_id, status: (
                feats if status == "interrupted" else []
            )
            mock_db.update_feature.side_effect = update_side_effect
            result = _resume_interrupted_work_periodic("proj-1")

        # At least the successfully promoted feature should be in the result
        assert feat_ok.id in result

    def test_function_does_not_raise_on_db_error(self):
        """Ensures the function never raises — errors are swallowed."""
        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = Exception("severe db failure")
            try:
                _resume_interrupted_work_periodic("proj-1")
            except Exception as exc:
                pytest.fail(f"Function raised unexpectedly: {exc}")
