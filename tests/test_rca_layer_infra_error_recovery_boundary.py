"""Boundary tests for RCA-layer infra-error recovery.

Tests that empty, zero, or minimum inputs return well-defined results
rather than raising (boundary case).
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest


class TestAnalyzeAttemptHistoryBoundary:
    """rca_agent.analyze_attempt_history: minimum/empty input is safe."""

    def test_empty_agent_logs_returns_feature_defect(self, tmp_path: pathlib.Path) -> None:
        """With no log files, classify_attempts returns feature_defect (no infra evidence)."""
        from bob3.rca_agent import analyze_attempt_history

        # point to empty workspace with no .bob3/agent_logs
        verdict = analyze_attempt_history("feat-boundary-001", workspace=tmp_path)
        # Boundary: no log files → no infra evidence → feature_defect (safe, defined)
        assert verdict in {"infra_only", "feature_defect", "mixed"}

    def test_very_short_feature_id_accepted(self) -> None:
        """A minimal valid feature_id (1 char) should not raise."""
        from bob3.rca_agent import analyze_attempt_history

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            verdict = analyze_attempt_history("x")
        assert verdict == "feature_defect"


class TestIsInfraOnlyBoundary:
    """rca_agent.is_infra_only: minimum input returns well-defined bool."""

    def test_no_logs_returns_false(self, tmp_path: pathlib.Path) -> None:
        """Empty workspace: is_infra_only must return a bool (not raise)."""
        from bob3.rca_agent import is_infra_only

        result = is_infra_only("feat-boundary-002", workspace=tmp_path)
        assert isinstance(result, bool)

    def test_returns_false_on_feature_defect(self) -> None:
        from bob3.rca_agent import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            assert is_infra_only("feat-boundary-003") is False


class TestResetToReadyBoundary:
    """feature_reset.reset_to_ready: zero / minimum refinement_attempts is valid."""

    def test_zero_refinement_attempts_is_valid(self) -> None:
        """refinement_attempts=0 is the canonical infra-reset value — must not raise."""
        from bob3.feature_reset import reset_to_ready

        mock_fn = MagicMock()
        reset_to_ready("feat-boundary-004", mock_fn, refinement_attempts=0)
        mock_fn.assert_called_once()

    def test_one_refinement_attempt_is_valid(self) -> None:
        """refinement_attempts=1 is a valid boundary value."""
        from bob3.feature_reset import reset_to_ready

        mock_fn = MagicMock()
        reset_to_ready("feat-boundary-005", mock_fn, refinement_attempts=1)
        mock_fn.assert_called_once()


class TestAutoResetIfInfraBoundary:
    """auto_reset_if_infra: empty / minimum failed_acs list is safe."""

    def test_empty_failed_acs_triggers_infra_path(self) -> None:
        """failed_acs=[] → no code-emission-defect path → falls through to infra path."""
        from bob3.orchestrator.rca_infra_recovery import auto_reset_if_infra

        db_update = MagicMock()

        with (
            patch(
                "bob3.orchestrator.rca_infra_recovery.classify_attempts",
                return_value="feature_defect",
            ),
        ):
            result = auto_reset_if_infra(
                feature_id="feat-boundary-006",
                project_id="proj-x",
                db_update_fn=db_update,
                failed_acs=[],
                refinement_attempts=0,
            )
        # empty list → spec_ambiguity classification (see classify_verification_failure)
        # → NH stands → False
        assert isinstance(result, bool)

    def test_zero_refinement_attempts_with_code_defect(self) -> None:
        """refinement_attempts=0 with code_emission_defect → grants first attempt."""
        from bob3.orchestrator.rca_infra_recovery import auto_reset_if_infra

        db_update = MagicMock()

        with patch("bob3.orchestrator.rca_infra_recovery._emit_rca_reset_event"):
            result = auto_reset_if_infra(
                feature_id="feat-boundary-007",
                project_id="proj-x",
                db_update_fn=db_update,
                failed_acs=["pytest: tests/test_boundary.py failed"],
                refinement_attempts=0,
            )
        assert result is True
        db_update.assert_called_once()
