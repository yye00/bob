"""Tests for bob3.rca_layer — second-line infra-error recovery.

Covers:
- Module is importable at bob3.rca_layer.
- analyze_infra_errors returns correct Verdict.
- analyze_infra_errors raises ValueError/TypeError on invalid inputs.
- is_infra_only returns True only for infra_only verdict.
- is_infra_only raises ValueError/TypeError on invalid inputs.
- append_spawn_retry_signature delegates and persists patterns.
- append_spawn_retry_signature raises ValueError/TypeError on invalid inputs.
- Re-exported symbols (auto_reset_if_infra, classify_attempts, harvest_novel_pattern).
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest
import yaml


class TestModuleImports:
    """Module and all required symbols are importable."""

    def test_module_is_importable(self) -> None:
        import bob3.rca_layer  # noqa: F401

    def test_analyze_infra_errors_callable(self) -> None:
        from bob3.rca_layer import analyze_infra_errors
        assert callable(analyze_infra_errors)

    def test_is_infra_only_callable(self) -> None:
        from bob3.rca_layer import is_infra_only
        assert callable(is_infra_only)

    def test_append_spawn_retry_signature_callable(self) -> None:
        from bob3.rca_layer import append_spawn_retry_signature
        assert callable(append_spawn_retry_signature)

    def test_auto_reset_if_infra_reexported(self) -> None:
        from bob3.rca_layer import auto_reset_if_infra
        assert callable(auto_reset_if_infra)

    def test_classify_attempts_reexported(self) -> None:
        from bob3.rca_layer import classify_attempts
        assert callable(classify_attempts)

    def test_harvest_novel_pattern_reexported(self) -> None:
        from bob3.rca_layer import harvest_novel_pattern
        assert callable(harvest_novel_pattern)


class TestAnalyzeInfraErrors:
    """analyze_infra_errors wraps classify_attempts and returns a Verdict."""

    def test_returns_infra_only_when_classify_returns_infra_only(self) -> None:
        from bob3.rca_layer import analyze_infra_errors

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ):
            result = analyze_infra_errors("feat-001")
        assert result == "infra_only"

    def test_returns_feature_defect_when_classify_returns_feature_defect(self) -> None:
        from bob3.rca_layer import analyze_infra_errors

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            result = analyze_infra_errors("feat-002")
        assert result == "feature_defect"

    def test_returns_mixed_when_classify_returns_mixed(self) -> None:
        from bob3.rca_layer import analyze_infra_errors

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="mixed",
        ):
            result = analyze_infra_errors("feat-003")
        assert result == "mixed"

    def test_passes_workspace_to_classify(self, tmp_path: pathlib.Path) -> None:
        from bob3.rca_layer import analyze_infra_errors

        captured: list = []

        def fake_classify(fid, workspace=None):
            captured.append(workspace)
            return "feature_defect"

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            side_effect=fake_classify,
        ):
            analyze_infra_errors("feat-004", workspace=tmp_path)

        assert captured[0] == tmp_path

    def test_none_feature_id_raises_value_error(self) -> None:
        from bob3.rca_layer import analyze_infra_errors

        with pytest.raises(ValueError):
            analyze_infra_errors(None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises_value_error(self) -> None:
        from bob3.rca_layer import analyze_infra_errors

        with pytest.raises(ValueError):
            analyze_infra_errors("")

    def test_whitespace_feature_id_raises_value_error(self) -> None:
        from bob3.rca_layer import analyze_infra_errors

        with pytest.raises(ValueError):
            analyze_infra_errors("   ")

    def test_non_string_feature_id_raises_type_error(self) -> None:
        from bob3.rca_layer import analyze_infra_errors

        with pytest.raises(TypeError):
            analyze_infra_errors(42)  # type: ignore[arg-type]

    def test_list_feature_id_raises_type_error(self) -> None:
        from bob3.rca_layer import analyze_infra_errors

        with pytest.raises(TypeError):
            analyze_infra_errors(["feat-001"])  # type: ignore[arg-type]


class TestIsInfraOnly:
    """is_infra_only returns True only when analyze_infra_errors → infra_only."""

    def test_true_on_infra_only(self) -> None:
        from bob3.rca_layer import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ):
            assert is_infra_only("feat-010") is True

    def test_false_on_feature_defect(self) -> None:
        from bob3.rca_layer import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            assert is_infra_only("feat-011") is False

    def test_false_on_mixed(self) -> None:
        from bob3.rca_layer import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="mixed",
        ):
            assert is_infra_only("feat-012") is False

    def test_none_feature_id_raises_value_error(self) -> None:
        from bob3.rca_layer import is_infra_only

        with pytest.raises(ValueError):
            is_infra_only(None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises_value_error(self) -> None:
        from bob3.rca_layer import is_infra_only

        with pytest.raises(ValueError):
            is_infra_only("")

    def test_whitespace_feature_id_raises_value_error(self) -> None:
        from bob3.rca_layer import is_infra_only

        with pytest.raises(ValueError):
            is_infra_only("   ")

    def test_non_string_feature_id_raises_type_error(self) -> None:
        from bob3.rca_layer import is_infra_only

        with pytest.raises(TypeError):
            is_infra_only(42)  # type: ignore[arg-type]

    def test_returns_bool(self) -> None:
        from bob3.rca_layer import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ):
            result = is_infra_only("feat-013")
        assert isinstance(result, bool)


class TestAppendSpawnRetrySignature:
    """append_spawn_retry_signature persists novel patterns to spawn_retry.yaml."""

    def test_delegates_to_append_discovered_pattern(self) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        with patch(
            "bob3.rca_layer._append_discovered_pattern"
        ) as mock_append:
            append_spawn_retry_signature("ENOENT.*socket", "feat-020")

        mock_append.assert_called_once_with("ENOENT.*socket", "feat-020")

    def test_pattern_appears_in_yaml(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        cfg = tmp_path / "config" / "spawn_retry.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("TRANSIENT_PATTERNS:\n- '429'\n")

        import bob3.orchestrator.rca_infra_recovery as mod
        monkeypatch.setattr(mod, "_SPAWN_RETRY_CONFIG", cfg)

        append_spawn_retry_signature("novel.*error", "feat-021")

        data = yaml.safe_load(cfg.read_text())
        patterns = [e["pattern"] for e in data.get("discovered_patterns", [])]
        assert "novel.*error" in patterns

    def test_duplicate_pattern_not_written_twice(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        cfg = tmp_path / "config" / "spawn_retry.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("TRANSIENT_PATTERNS: []\n")

        import bob3.orchestrator.rca_infra_recovery as mod
        monkeypatch.setattr(mod, "_SPAWN_RETRY_CONFIG", cfg)

        append_spawn_retry_signature("dup.*pattern", "feat-022")
        append_spawn_retry_signature("dup.*pattern", "feat-022")

        data = yaml.safe_load(cfg.read_text())
        patterns = [e["pattern"] for e in data.get("discovered_patterns", [])]
        assert patterns.count("dup.*pattern") == 1

    def test_none_pattern_raises_value_error(self) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        with pytest.raises(ValueError):
            append_spawn_retry_signature(None, "feat-030")  # type: ignore[arg-type]

    def test_empty_pattern_raises_value_error(self) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        with pytest.raises(ValueError):
            append_spawn_retry_signature("", "feat-031")

    def test_whitespace_pattern_raises_value_error(self) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        with pytest.raises(ValueError):
            append_spawn_retry_signature("   ", "feat-032")

    def test_non_string_pattern_raises_type_error(self) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        with pytest.raises(TypeError):
            append_spawn_retry_signature(123, "feat-033")  # type: ignore[arg-type]

    def test_none_feature_id_raises_value_error(self) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        with pytest.raises(ValueError):
            append_spawn_retry_signature("some-pattern", None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises_value_error(self) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        with pytest.raises(ValueError):
            append_spawn_retry_signature("some-pattern", "")

    def test_whitespace_feature_id_raises_value_error(self) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        with pytest.raises(ValueError):
            append_spawn_retry_signature("some-pattern", "   ")

    def test_non_string_feature_id_raises_type_error(self) -> None:
        from bob3.rca_layer import append_spawn_retry_signature

        with pytest.raises(TypeError):
            append_spawn_retry_signature("some-pattern", 42)  # type: ignore[arg-type]


class TestOrchestratorIntegration:
    """Integration: auto_reset_if_infra is accessible and functional."""

    def test_auto_reset_returns_true_on_infra_only(self) -> None:
        from bob3.rca_layer import auto_reset_if_infra

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
        assert db_update.call_args[1].get("status") == "ready"
        assert db_update.call_args[1].get("refinement_attempts") == 0

    def test_auto_reset_returns_false_on_feature_defect(self) -> None:
        from bob3.rca_layer import auto_reset_if_infra

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
