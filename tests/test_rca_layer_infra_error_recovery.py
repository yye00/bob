"""Tests for rca_layer.infra_error_recovery.

Covers:
- Module is importable at src/rca_layer/infra_error_recovery.py.
- verdict_infra_only returns True when classify_attempts → infra_only.
- verdict_infra_only returns False when classify_attempts → feature_defect.
- verdict_infra_only returns False when classify_attempts → mixed.
- verdict_infra_only raises ValueError for empty/None feature_id.
- verdict_infra_only raises TypeError for non-string feature_id.
- append_novel_signature delegates to _append_discovered_pattern.
- append_novel_signature raises ValueError for empty/None inputs.
- append_novel_signature raises TypeError for non-string inputs.
- append_novel_signature writes entry to config/spawn_retry.yaml.
- Integration: auto_reset_if_infra is re-exported.
- Integration: classify_attempts is re-exported.
- Integration: harvest_novel_pattern is re-exported.
"""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml


class TestModuleImports:
    """The module exists at the correct path and exports the required symbols."""

    def test_module_is_importable(self) -> None:
        import rca_layer.infra_error_recovery  # noqa: F401

    def test_verdict_infra_only_is_callable(self) -> None:
        from rca_layer.infra_error_recovery import verdict_infra_only

        assert callable(verdict_infra_only)

    def test_append_novel_signature_is_callable(self) -> None:
        from rca_layer.infra_error_recovery import append_novel_signature

        assert callable(append_novel_signature)

    def test_auto_reset_if_infra_reexported(self) -> None:
        from rca_layer.infra_error_recovery import auto_reset_if_infra

        assert callable(auto_reset_if_infra)

    def test_classify_attempts_reexported(self) -> None:
        from rca_layer.infra_error_recovery import classify_attempts

        assert callable(classify_attempts)

    def test_harvest_novel_pattern_reexported(self) -> None:
        from rca_layer.infra_error_recovery import harvest_novel_pattern

        assert callable(harvest_novel_pattern)


class TestVerdictInfraOnly:
    """verdict_infra_only wraps classify_attempts and returns a bool."""

    def test_returns_true_on_infra_only(self) -> None:
        from rca_layer.infra_error_recovery import verdict_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ):
            assert verdict_infra_only("feat-001") is True

    def test_returns_false_on_feature_defect(self) -> None:
        from rca_layer.infra_error_recovery import verdict_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            assert verdict_infra_only("feat-002") is False

    def test_returns_false_on_mixed(self) -> None:
        from rca_layer.infra_error_recovery import verdict_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="mixed",
        ):
            assert verdict_infra_only("feat-003") is False

    def test_passes_workspace_to_classify(self, tmp_path: pathlib.Path) -> None:
        from rca_layer.infra_error_recovery import verdict_infra_only

        captured: list[Any] = []

        def fake_classify(fid: str, workspace=None):
            captured.append(workspace)
            return "feature_defect"

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            side_effect=fake_classify,
        ):
            verdict_infra_only("feat-004", workspace=tmp_path)

        assert captured[0] == tmp_path

    def test_none_feature_id_raises_value_error(self) -> None:
        from rca_layer.infra_error_recovery import verdict_infra_only

        with pytest.raises(ValueError):
            verdict_infra_only(None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises_value_error(self) -> None:
        from rca_layer.infra_error_recovery import verdict_infra_only

        with pytest.raises(ValueError):
            verdict_infra_only("")

    def test_whitespace_only_feature_id_raises_value_error(self) -> None:
        from rca_layer.infra_error_recovery import verdict_infra_only

        with pytest.raises(ValueError):
            verdict_infra_only("   ")

    def test_non_string_feature_id_raises_type_error(self) -> None:
        from rca_layer.infra_error_recovery import verdict_infra_only

        with pytest.raises(TypeError):
            verdict_infra_only(42)  # type: ignore[arg-type]

    def test_list_feature_id_raises_type_error(self) -> None:
        from rca_layer.infra_error_recovery import verdict_infra_only

        with pytest.raises(TypeError):
            verdict_infra_only(["feat-001"])  # type: ignore[arg-type]


class TestAppendNovelSignature:
    """append_novel_signature writes a discovered pattern to spawn_retry.yaml."""

    def test_delegates_to_append_discovered_pattern(self) -> None:
        from rca_layer.infra_error_recovery import append_novel_signature

        with patch(
            "bob3.orchestrator.rca_infra_recovery._append_discovered_pattern"
        ) as mock_append:
            append_novel_signature("ENOENT.*socket", "feat-010")

        mock_append.assert_called_once_with(
            pattern="ENOENT.*socket",
            feature_id="feat-010",
        )

    def test_writes_to_spawn_retry_yaml(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        """End-to-end: pattern appears in config/spawn_retry.yaml after call."""
        from rca_layer.infra_error_recovery import append_novel_signature

        cfg = tmp_path / "config" / "spawn_retry.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("TRANSIENT_PATTERNS:\n- '429'\n")

        import bob3.orchestrator.rca_infra_recovery as mod
        monkeypatch.setattr(mod, "_SPAWN_RETRY_CONFIG", cfg)

        append_novel_signature("novel.*signature", "feat-011")

        data = yaml.safe_load(cfg.read_text())
        patterns = [e["pattern"] for e in data.get("discovered_patterns", [])]
        assert "novel.*signature" in patterns

    def test_duplicate_pattern_not_written_twice(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        from rca_layer.infra_error_recovery import append_novel_signature

        cfg = tmp_path / "config" / "spawn_retry.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("TRANSIENT_PATTERNS: []\n")

        import bob3.orchestrator.rca_infra_recovery as mod
        monkeypatch.setattr(mod, "_SPAWN_RETRY_CONFIG", cfg)

        append_novel_signature("dup.*pattern", "feat-012")
        append_novel_signature("dup.*pattern", "feat-012")

        data = yaml.safe_load(cfg.read_text())
        patterns = [e["pattern"] for e in data.get("discovered_patterns", [])]
        assert patterns.count("dup.*pattern") == 1

    def test_none_pattern_raises_value_error(self) -> None:
        from rca_layer.infra_error_recovery import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature(None, "feat-020")  # type: ignore[arg-type]

    def test_empty_pattern_raises_value_error(self) -> None:
        from rca_layer.infra_error_recovery import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature("", "feat-021")

    def test_whitespace_pattern_raises_value_error(self) -> None:
        from rca_layer.infra_error_recovery import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature("   ", "feat-022")

    def test_non_string_pattern_raises_type_error(self) -> None:
        from rca_layer.infra_error_recovery import append_novel_signature

        with pytest.raises(TypeError):
            append_novel_signature(123, "feat-023")  # type: ignore[arg-type]

    def test_none_feature_id_raises_value_error(self) -> None:
        from rca_layer.infra_error_recovery import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature("some-pattern", None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises_value_error(self) -> None:
        from rca_layer.infra_error_recovery import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature("some-pattern", "")

    def test_non_string_feature_id_raises_type_error(self) -> None:
        from rca_layer.infra_error_recovery import append_novel_signature

        with pytest.raises(TypeError):
            append_novel_signature("some-pattern", 42)  # type: ignore[arg-type]


class TestIntegrationWithOrchestrator:
    """Integration: auto_reset_if_infra orchestrates verdict + DB reset + pattern append."""

    def test_auto_reset_if_infra_returns_true_on_infra_only(self) -> None:
        from rca_layer.infra_error_recovery import auto_reset_if_infra

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
                return_value=None,
            ),
            patch("bob3.orchestrator.rca_infra_recovery._emit_rca_reset_event"),
        ):
            result = auto_reset_if_infra(
                feature_id="feat-int-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is True
        db_update.assert_called_once()
        call_kwargs = db_update.call_args
        assert call_kwargs[1].get("status") == "ready"
        assert call_kwargs[1].get("refinement_attempts") == 0

    def test_auto_reset_if_infra_returns_false_on_feature_defect(self) -> None:
        from rca_layer.infra_error_recovery import auto_reset_if_infra

        db_update = MagicMock()

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            result = auto_reset_if_infra(
                feature_id="feat-int-002",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is False
        db_update.assert_not_called()

    def test_novel_pattern_appended_when_infra_only(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        from rca_layer.infra_error_recovery import auto_reset_if_infra

        cfg = tmp_path / "config" / "spawn_retry.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("TRANSIENT_PATTERNS: []\n")

        import bob3.orchestrator.rca_infra_recovery as mod
        monkeypatch.setattr(mod, "_SPAWN_RETRY_CONFIG", cfg)
        monkeypatch.setattr(mod, "_RCA_RESETS_JSONL", tmp_path / "reviews" / "rca_resets.jsonl")
        monkeypatch.setattr(mod, "_AGENT_LOGS_DIR", tmp_path / ".bob3" / "agent_logs")

        db_update = MagicMock()

        with (
            patch.object(mod, "classify_attempts", return_value="infra_only"),
            patch.object(mod, "_count_rca_resets", return_value=0),
            patch.object(mod, "harvest_novel_pattern", return_value="novel.*infra\\x20sig"),
            patch.object(mod, "_emit_rca_reset_event"),
        ):
            result = auto_reset_if_infra(
                feature_id="feat-int-003",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is True
        data = yaml.safe_load(cfg.read_text())
        patterns = [e["pattern"] for e in data.get("discovered_patterns", [])]
        assert "novel.*infra\\x20sig" in patterns
