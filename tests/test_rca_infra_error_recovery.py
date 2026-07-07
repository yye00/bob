"""Tests for RCA-layer infra-error recovery (F-R7-479).

Second-line defense against false needs_human: before the orchestrator
transitions a feature to ``needs_human``, the RCA layer inspects the history
of failed attempts and answers — were ALL N attempts infra-caused? If so, the
feature is reset to ``ready`` with refinement_attempts=0 and the novel signature
is auto-learned into config/spawn_retry.yaml.
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest


class TestClassifyAttemptsInfraOnly:
    """classify_attempts_infra_only returns a well-defined bool verdict."""

    def test_returns_true_when_all_attempts_infra(self) -> None:
        from bob.rca_infra_error_recovery import classify_attempts_infra_only

        with patch(
            "bob.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ):
            assert classify_attempts_infra_only("feat-001") is True

    def test_returns_false_on_feature_defect(self) -> None:
        from bob.rca_infra_error_recovery import classify_attempts_infra_only

        with patch(
            "bob.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            assert classify_attempts_infra_only("feat-002") is False

    def test_returns_false_on_mixed(self) -> None:
        from bob.rca_infra_error_recovery import classify_attempts_infra_only

        with patch(
            "bob.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="mixed",
        ):
            assert classify_attempts_infra_only("feat-003") is False

    def test_empty_workspace_returns_bool(self, tmp_path: pathlib.Path) -> None:
        from bob.rca_infra_error_recovery import classify_attempts_infra_only

        result = classify_attempts_infra_only("feat-004", workspace=tmp_path)
        assert isinstance(result, bool)


class TestRecoverInfraOnlyFeature:
    """recover_infra_only_feature resets to ready only on infra_only verdict."""

    def test_resets_feature_on_infra_only(self) -> None:
        from bob.rca_infra_error_recovery import recover_infra_only_feature

        db_update = MagicMock()
        with (
            patch(
                "bob.orchestrator.rca_infra_recovery.classify_attempts",
                return_value="infra_only",
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery.harvest_novel_pattern",
                return_value=None,
            ),
            patch("bob.orchestrator.rca_infra_recovery._count_rca_resets", return_value=0),
            patch("bob.orchestrator.rca_infra_recovery._emit_rca_reset_event"),
        ):
            result = recover_infra_only_feature("feat-005", db_update)

        assert result is True
        db_update.assert_called_once()
        _, kwargs = db_update.call_args
        assert kwargs.get("status") == "ready"
        assert kwargs.get("refinement_attempts") == 0

    def test_does_not_reset_on_feature_defect(self) -> None:
        from bob.rca_infra_error_recovery import recover_infra_only_feature

        db_update = MagicMock()
        with patch(
            "bob.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            result = recover_infra_only_feature("feat-006", db_update)

        assert result is False
        db_update.assert_not_called()

    def test_appends_novel_pattern_on_infra_only(self) -> None:
        from bob.rca_infra_error_recovery import recover_infra_only_feature

        db_update = MagicMock()
        with (
            patch(
                "bob.orchestrator.rca_infra_recovery.classify_attempts",
                return_value="infra_only",
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery.harvest_novel_pattern",
                return_value="brand.*new.*signature",
            ),
            patch("bob.orchestrator.rca_infra_recovery._count_rca_resets", return_value=0),
            patch("bob.orchestrator.rca_infra_recovery._emit_rca_reset_event"),
            patch(
                "bob.orchestrator.rca_infra_recovery._append_discovered_pattern"
            ) as mock_append,
        ):
            result = recover_infra_only_feature("feat-007", db_update)

        assert result is True
        mock_append.assert_called_once()
        args, _ = mock_append.call_args
        assert args[0] == "brand.*new.*signature"


class TestModuleSurface:
    """The module exposes the AC-required entry points."""

    def test_functions_are_defined(self) -> None:
        import bob.rca_infra_error_recovery as mod

        assert callable(mod.classify_attempts_infra_only)
        assert callable(mod.recover_infra_only_feature)

    def test_orchestrator_integration_import(self) -> None:
        import bob.orchestrator  # noqa: F401
        import bob.rca_infra_error_recovery  # noqa: F401
