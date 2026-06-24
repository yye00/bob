"""Error-path tests for RCA-layer infra-error recovery.

Tests that invalid input raises ValueError (or TypeError) and the function
does not silently succeed.
"""

from __future__ import annotations

import pytest


class TestAnalyzeAttemptHistoryError:
    """rca_agent.analyze_attempt_history: invalid inputs raise."""

    def test_none_feature_id_raises_value_error(self) -> None:
        from bob3.rca_agent import analyze_attempt_history

        with pytest.raises(ValueError):
            analyze_attempt_history(None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises_value_error(self) -> None:
        from bob3.rca_agent import analyze_attempt_history

        with pytest.raises(ValueError):
            analyze_attempt_history("")

    def test_whitespace_feature_id_raises_value_error(self) -> None:
        from bob3.rca_agent import analyze_attempt_history

        with pytest.raises(ValueError):
            analyze_attempt_history("   ")

    def test_non_string_feature_id_raises_type_error(self) -> None:
        from bob3.rca_agent import analyze_attempt_history

        with pytest.raises(TypeError):
            analyze_attempt_history(123)  # type: ignore[arg-type]

    def test_list_feature_id_raises_type_error(self) -> None:
        from bob3.rca_agent import analyze_attempt_history

        with pytest.raises(TypeError):
            analyze_attempt_history(["feat-001"])  # type: ignore[arg-type]


class TestIsInfraOnlyError:
    """rca_agent.is_infra_only: invalid inputs raise and do not silently succeed."""

    def test_none_feature_id_raises(self) -> None:
        from bob3.rca_agent import is_infra_only

        with pytest.raises(ValueError):
            is_infra_only(None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises(self) -> None:
        from bob3.rca_agent import is_infra_only

        with pytest.raises(ValueError):
            is_infra_only("")

    def test_non_string_feature_id_raises(self) -> None:
        from bob3.rca_agent import is_infra_only

        with pytest.raises(TypeError):
            is_infra_only(42)  # type: ignore[arg-type]


class TestResetToReadyError:
    """feature_reset.reset_to_ready: invalid inputs raise and do not silently succeed."""

    def test_none_feature_id_raises(self) -> None:
        from bob3.feature_reset import reset_to_ready
        from unittest.mock import MagicMock

        with pytest.raises(ValueError):
            reset_to_ready(None, MagicMock())  # type: ignore[arg-type]

    def test_empty_feature_id_raises(self) -> None:
        from bob3.feature_reset import reset_to_ready
        from unittest.mock import MagicMock

        with pytest.raises(ValueError):
            reset_to_ready("", MagicMock())

    def test_non_callable_db_fn_raises_type_error(self) -> None:
        from bob3.feature_reset import reset_to_ready

        with pytest.raises(TypeError):
            reset_to_ready("feat-001", "not-callable")  # type: ignore[arg-type]

    def test_negative_refinement_attempts_raises(self) -> None:
        from bob3.feature_reset import reset_to_ready
        from unittest.mock import MagicMock

        with pytest.raises(ValueError):
            reset_to_ready("feat-001", MagicMock(), refinement_attempts=-1)

    def test_float_refinement_attempts_raises_type_error(self) -> None:
        from bob3.feature_reset import reset_to_ready
        from unittest.mock import MagicMock

        with pytest.raises(TypeError):
            reset_to_ready("feat-001", MagicMock(), refinement_attempts=0.5)  # type: ignore[arg-type]
