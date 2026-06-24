"""Boundary tests for _final_exit_sweep (F-R7-598).

AC: pytest: tests/test_final_exit_sweep_boundary.py — empty, zero, or minimum
input returns a well-defined result rather than raising (boundary case).
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


class TestFinalExitSweepBoundary:
    """Boundary: empty, zero, or minimum inputs must not raise."""

    def test_empty_executing_features_list(self) -> None:
        """When there are no executing features, sweep completes without raising."""
        with (
            patch("bob.orchestrator.run_loop.db") as mock_db,
            patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature", return_value=[]),
        ):
            mock_db.list_features.return_value = []

            # Must not raise
            result = _final_exit_sweep("project-boundary-empty")
            assert result is None  # _final_exit_sweep returns None

    def test_single_feature_already_promoted(self) -> None:
        """Minimum input (one feature whose ACs are satisfied) returns without raising."""
        feature = _make_feature(
            "eeee5555-0000-0000-0000-000000000005",
            "minimum feature",
            ["File exists: src/bob/verification/ac_artifact_check.py"],
        )

        with (
            patch("bob.orchestrator.run_loop.db") as mock_db,
            patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature", return_value=[]),
            patch("bob.orchestrator.run_loop._check_executing_feature_acs", return_value=True),
        ):
            mock_db.list_features.return_value = [feature]

            # Must not raise
            _final_exit_sweep("project-boundary-single")

    def test_none_project_id_raises_value_error(self) -> None:
        """None project_id raises ValueError — defined error, not a silent pass."""
        with pytest.raises(ValueError):
            _final_exit_sweep(None)  # type: ignore[arg-type]

    def test_feature_with_empty_acs_list(self) -> None:
        """Feature with an empty AC list still goes through the sweep without raising."""
        feature = _make_feature(
            "ffff6666-0000-0000-0000-000000000006",
            "empty acs feature",
            [],
        )

        with (
            patch("bob.orchestrator.run_loop.db") as mock_db,
            patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature", return_value=[]),
            patch("bob.orchestrator.run_loop._check_executing_feature_acs", return_value=False),
        ):
            mock_db.list_features.return_value = [feature]

            # Must not raise
            _final_exit_sweep("project-boundary-empty-acs")
            mock_db.update_feature.assert_called_once_with(
                feature.id,
                status="failed",
                last_improvement_type="orchestrator_exit_during_execution",
            )

    def test_feature_with_live_pid_not_touched(self) -> None:
        """Feature with a live PID is skipped — sweep returns without raising."""
        feature = _make_feature(
            "gggg7777-0000-0000-0000-000000000007",
            "live feature boundary",
            ["File exists: src/bob/verification/ac_artifact_check.py"],
        )

        with (
            patch("bob.orchestrator.run_loop.db") as mock_db,
            patch("bob.orchestrator.run_loop.find_subagent_pid_for_feature", return_value=[99999]),
            patch("bob.orchestrator.run_loop._check_executing_feature_acs") as mock_check,
        ):
            mock_db.list_features.return_value = [feature]

            _final_exit_sweep("project-boundary-live-pid")

            mock_check.assert_not_called()
            mock_db.update_feature.assert_not_called()
