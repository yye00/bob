"""Tests for RCA-layer infra-error recovery (F-R7-479).

Validates the full second-line defense chain:
- rca_agent.analyze_attempt_history classifies attempt history
- rca_agent.is_infra_only returns correct boolean verdict
- feature_reset.reset_to_ready calls db_update_fn with correct args
- auto_reset_if_infra integrates classification + reset + pattern append
- config/spawn_retry.yaml exists and is writable
"""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# rca_agent.analyze_attempt_history
# ---------------------------------------------------------------------------


class TestAnalyzeAttemptHistory:
    """rca_agent.analyze_attempt_history returns correct verdicts."""

    def test_infra_only_verdict(self) -> None:
        from bob3.rca_agent import analyze_attempt_history

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ):
            verdict = analyze_attempt_history("feat-001")
        assert verdict == "infra_only"

    def test_feature_defect_verdict(self) -> None:
        from bob3.rca_agent import analyze_attempt_history

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            verdict = analyze_attempt_history("feat-002")
        assert verdict == "feature_defect"

    def test_mixed_verdict(self) -> None:
        from bob3.rca_agent import analyze_attempt_history

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="mixed",
        ):
            verdict = analyze_attempt_history("feat-003")
        assert verdict == "mixed"

    def test_accepts_workspace_kwarg(self, tmp_path: pathlib.Path) -> None:
        from bob3.rca_agent import analyze_attempt_history

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ) as mock_classify:
            analyze_attempt_history("feat-004", workspace=tmp_path)
            mock_classify.assert_called_once_with("feat-004", workspace=tmp_path)


# ---------------------------------------------------------------------------
# rca_agent.is_infra_only
# ---------------------------------------------------------------------------


class TestIsInfraOnly:
    """rca_agent.is_infra_only returns True only for infra_only verdict."""

    def test_true_on_infra_only(self) -> None:
        from bob3.rca_agent import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ):
            assert is_infra_only("feat-infra") is True

    def test_false_on_feature_defect(self) -> None:
        from bob3.rca_agent import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            assert is_infra_only("feat-defect") is False

    def test_false_on_mixed(self) -> None:
        from bob3.rca_agent import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="mixed",
        ):
            assert is_infra_only("feat-mixed") is False


# ---------------------------------------------------------------------------
# feature_reset.reset_to_ready
# ---------------------------------------------------------------------------


class TestResetToReady:
    """feature_reset.reset_to_ready calls db_update_fn correctly."""

    def test_calls_db_update_with_ready_status(self) -> None:
        from bob3.feature_reset import reset_to_ready

        calls: list[dict] = []

        def db_update(feature_id: str, **kw: Any) -> None:
            calls.append({"feature_id": feature_id, **kw})

        reset_to_ready("feat-001", db_update)

        assert len(calls) == 1
        assert calls[0]["feature_id"] == "feat-001"
        assert calls[0]["status"] == "ready"
        assert calls[0]["refinement_attempts"] == 0

    def test_default_refinement_attempts_is_zero(self) -> None:
        from bob3.feature_reset import reset_to_ready

        mock_fn = MagicMock()
        reset_to_ready("feat-002", mock_fn)
        mock_fn.assert_called_once_with("feat-002", status="ready", refinement_attempts=0)

    def test_custom_refinement_attempts(self) -> None:
        from bob3.feature_reset import reset_to_ready

        mock_fn = MagicMock()
        reset_to_ready("feat-003", mock_fn, refinement_attempts=3)
        mock_fn.assert_called_once_with("feat-003", status="ready", refinement_attempts=3)


# ---------------------------------------------------------------------------
# config/spawn_retry.yaml
# ---------------------------------------------------------------------------


class TestSpawnRetryYaml:
    """config/spawn_retry.yaml exists and has required structure."""

    def test_file_exists(self) -> None:
        cfg = pathlib.Path("config/spawn_retry.yaml")
        assert cfg.exists(), "config/spawn_retry.yaml must exist"

    def test_has_transient_patterns(self) -> None:
        cfg = pathlib.Path("config/spawn_retry.yaml")
        with cfg.open() as fh:
            data = yaml.safe_load(fh)
        assert "TRANSIENT_PATTERNS" in data, "spawn_retry.yaml must have TRANSIENT_PATTERNS key"
        assert isinstance(data["TRANSIENT_PATTERNS"], list)

    def test_has_discovered_patterns_key(self) -> None:
        cfg = pathlib.Path("config/spawn_retry.yaml")
        with cfg.open() as fh:
            data = yaml.safe_load(fh)
        assert "discovered_patterns" in data, "spawn_retry.yaml must have discovered_patterns key"


# ---------------------------------------------------------------------------
# Integration: auto_reset_if_infra orchestrates everything
# ---------------------------------------------------------------------------


class TestAutoResetIfInfraIntegration:
    """End-to-end: infra_only verdict resets feature and appends novel pattern."""

    def test_infra_only_resets_to_ready(self) -> None:
        from bob3.orchestrator.rca_infra_recovery import auto_reset_if_infra

        calls: list[dict] = []

        def db_update(feature_id: str, **kw: Any) -> None:
            calls.append({"feature_id": feature_id, **kw})

        with (
            patch(
                "bob3.orchestrator.rca_infra_recovery.classify_attempts",
                return_value="infra_only",
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery._count_rca_resets",
                return_value=0,
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery.harvest_novel_pattern",
                return_value=None,
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery._emit_rca_reset_event",
            ),
        ):
            result = auto_reset_if_infra(
                feature_id="feat-integ-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is True
        assert calls[0]["status"] == "ready"
        assert calls[0]["refinement_attempts"] == 0

    def test_feature_defect_does_not_reset(self) -> None:
        from bob3.orchestrator.rca_infra_recovery import auto_reset_if_infra

        db_update = MagicMock()

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            result = auto_reset_if_infra(
                feature_id="feat-integ-002",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is False
        db_update.assert_not_called()

    def test_novel_pattern_appended(self, tmp_path: pathlib.Path) -> None:
        from bob3.orchestrator.rca_infra_recovery import auto_reset_if_infra

        cfg_file = tmp_path / "config" / "spawn_retry.yaml"
        cfg_file.parent.mkdir(parents=True)
        cfg_file.write_text(
            yaml.dump({"TRANSIENT_PATTERNS": [], "discovered_patterns": []})
        )

        db_update = MagicMock()

        with (
            patch(
                "bob3.orchestrator.rca_infra_recovery.classify_attempts",
                return_value="infra_only",
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery._count_rca_resets",
                return_value=0,
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery.harvest_novel_pattern",
                return_value="novel\\.pattern\\.123",
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG",
                cfg_file,
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery._emit_rca_reset_event",
            ),
        ):
            result = auto_reset_if_infra(
                feature_id="feat-integ-003",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is True
        with cfg_file.open() as fh:
            data = yaml.safe_load(fh)
        patterns = [p["pattern"] for p in data.get("discovered_patterns", [])]
        assert "novel\\.pattern\\.123" in patterns
