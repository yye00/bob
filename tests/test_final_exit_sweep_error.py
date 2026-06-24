"""Error-path tests for _final_exit_sweep (F-R7-598).

AC: pytest: tests/test_final_exit_sweep_error.py — invalid input raises ValueError
and the function does not silently succeed (error path).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bob.run_loop import _final_exit_sweep


def _make_feature(feature_id: str, name: str, acs: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        id=feature_id,
        name=name,
        acceptance_criteria=json.dumps(acs),
    )


class TestFinalExitSweepErrorPath:
    """Error paths: invalid inputs must raise ValueError, not silently succeed."""

    def test_none_project_id_raises_value_error(self) -> None:
        """None project_id is invalid — must raise ValueError, not silently return."""
        with pytest.raises(ValueError):
            _final_exit_sweep(None)  # type: ignore[arg-type]

    def test_disk_ac_check_exception_falls_through_to_flip_failed(self) -> None:
        """When _check_executing_feature_acs raises, feature is flipped to failed (no silent success)."""
        feature = _make_feature(
            "hhhh8888-0000-0000-0000-000000000008",
            "error path feature",
            ["File exists: src/bob/verification/ac_artifact_check.py"],
        )

        with (
            patch("bob.orchestrator.run_loop.db") as mock_db,
            patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature", return_value=[]),
            patch(
                "bob.orchestrator.run_loop._check_executing_feature_acs",
                side_effect=RuntimeError("disk check exploded"),
            ),
        ):
            mock_db.list_features.return_value = [feature]

            # Must not re-raise the RuntimeError — sweep handles it internally
            _final_exit_sweep("project-error-disk-exploded")

            # Feature must be flipped to failed, not silently dropped
            mock_db.update_feature.assert_called_once_with(
                feature.id,
                status="failed",
                last_improvement_type="orchestrator_exit_during_execution",
            )

    def test_pid_lookup_exception_skips_feature(self) -> None:
        """When find_subagent_pid_for_feature raises, the feature is skipped (no silent success)."""
        feature = _make_feature(
            "iiii9999-0000-0000-0000-000000000009",
            "pid lookup error feature",
            ["File exists: src/bob/verification/ac_artifact_check.py"],
        )

        with (
            patch("bob.orchestrator.run_loop.db") as mock_db,
            patch(
                "bob.orchestrator.run_loop.find_subagent_pid_for_feature",
                side_effect=OSError("PID table gone"),
            ),
            patch("bob.orchestrator.run_loop._check_executing_feature_acs") as mock_check,
        ):
            mock_db.list_features.return_value = [feature]

            # Must not re-raise the OSError — sweep logs and skips this feature
            _final_exit_sweep("project-error-pid-lookup")

            # Neither AC check nor DB update should have run
            mock_check.assert_not_called()
            mock_db.update_feature.assert_not_called()

    def test_db_list_features_exception_returns_without_raising(self) -> None:
        """When the DB query for executing features fails, sweep returns without raising."""
        with (
            patch("bob.orchestrator.run_loop.db") as mock_db,
        ):
            mock_db.list_features.side_effect = Exception("DB unavailable")

            # Must not propagate the DB exception
            _final_exit_sweep("project-error-db-query")

    def test_flip_to_failed_db_exception_does_not_abort_sweep(self) -> None:
        """When db.update_feature raises during flip-to-failed, sweep continues (no crash)."""
        feature1 = _make_feature(
            "jjjj1010-0000-0000-0000-000000000010",
            "failing db update feature 1",
            ["File exists: missing1.py"],
        )
        feature2 = _make_feature(
            "kkkk1111-0000-0000-0000-000000000011",
            "failing db update feature 2",
            ["File exists: missing2.py"],
        )

        update_calls = []

        def update_side_effect(fid, **kwargs):
            update_calls.append(fid)
            if fid == feature1.id:
                raise Exception("DB write failed for feature 1")

        with (
            patch("bob.orchestrator.run_loop.db") as mock_db,
            patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature", return_value=[]),
            patch("bob.orchestrator.run_loop._check_executing_feature_acs", return_value=False),
        ):
            mock_db.list_features.return_value = [feature1, feature2]
            mock_db.update_feature.side_effect = update_side_effect

            # Must not raise even though feature1's DB write fails
            _final_exit_sweep("project-error-db-flip")

            # Both features were attempted
            assert feature1.id in update_calls
            assert feature2.id in update_calls
