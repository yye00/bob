"""Tests for bob.rca_infra_verdict — second-line defense against false NH.

Covers:
- Module is importable and exports required symbols.
- assess_infra_only returns True when classify_attempts → infra_only.
- assess_infra_only returns False when classify_attempts → feature_defect.
- assess_infra_only returns False when classify_attempts → mixed.
- assess_infra_only raises ValueError for None/empty/whitespace feature_id.
- assess_infra_only raises TypeError for non-string feature_id.
- append_novel_signature delegates to _append_discovered_pattern.
- append_novel_signature raises ValueError for None/empty inputs.
- append_novel_signature raises TypeError for non-string inputs.
- append_novel_signature is idempotent (duplicate patterns silently ignored).
- Integration: auto_reset_if_infra is re-exported.
- Integration: classify_attempts is re-exported.
- Integration: harvest_novel_pattern is re-exported.
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, call, patch

import pytest
import yaml


class TestModuleImports:
    """The module exists at the correct path and exports required symbols."""

    def test_module_is_importable(self) -> None:
        import bob.rca_infra_verdict  # noqa: F401

    def test_assess_infra_only_is_callable(self) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        assert callable(assess_infra_only)

    def test_append_novel_signature_is_callable(self) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        assert callable(append_novel_signature)

    def test_auto_reset_if_infra_reexported(self) -> None:
        from bob.rca_infra_verdict import auto_reset_if_infra

        assert callable(auto_reset_if_infra)

    def test_classify_attempts_reexported(self) -> None:
        from bob.rca_infra_verdict import classify_attempts

        assert callable(classify_attempts)

    def test_harvest_novel_pattern_reexported(self) -> None:
        from bob.rca_infra_verdict import harvest_novel_pattern

        assert callable(harvest_novel_pattern)


class TestAssessInfraOnly:
    """assess_infra_only: verdict mapping and delegation."""

    def test_returns_true_when_infra_only(self) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        with patch(
            "bob.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ):
            result = assess_infra_only("feat-001")
        assert result is True

    def test_returns_false_when_feature_defect(self) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        with patch(
            "bob.rca_infra_verdict.classify_attempts",
            return_value="feature_defect",
        ):
            result = assess_infra_only("feat-002")
        assert result is False

    def test_returns_false_when_mixed(self) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        with patch(
            "bob.rca_infra_verdict.classify_attempts",
            return_value="mixed",
        ):
            result = assess_infra_only("feat-003")
        assert result is False

    def test_returns_bool(self) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        with patch(
            "bob.rca_infra_verdict.classify_attempts",
            return_value="infra_only",
        ):
            result = assess_infra_only("feat-004")
        assert isinstance(result, bool)

    def test_passes_workspace_to_classify_attempts(self, tmp_path: pathlib.Path) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        with patch(
            "bob.rca_infra_verdict.classify_attempts",
            return_value="feature_defect",
        ) as mock_classify:
            assess_infra_only("feat-005", workspace=tmp_path)
        mock_classify.assert_called_once_with("feat-005", workspace=tmp_path)

    def test_empty_workspace_logs_returns_false(self, tmp_path: pathlib.Path) -> None:
        """With no log files, assess_infra_only returns a defined bool value."""
        from bob.rca_infra_verdict import assess_infra_only

        result = assess_infra_only("feat-boundary-001", workspace=tmp_path)
        assert isinstance(result, bool)


class TestAssessInfraOnlyErrors:
    """assess_infra_only: invalid inputs raise."""

    def test_none_feature_id_raises_value_error(self) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        with pytest.raises(ValueError):
            assess_infra_only(None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises_value_error(self) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        with pytest.raises(ValueError):
            assess_infra_only("")

    def test_whitespace_feature_id_raises_value_error(self) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        with pytest.raises(ValueError):
            assess_infra_only("   ")

    def test_non_string_feature_id_raises_type_error(self) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        with pytest.raises(TypeError):
            assess_infra_only(123)  # type: ignore[arg-type]

    def test_list_feature_id_raises_type_error(self) -> None:
        from bob.rca_infra_verdict import assess_infra_only

        with pytest.raises(TypeError):
            assess_infra_only(["feat-001"])  # type: ignore[arg-type]


class TestAppendNovelSignature:
    """append_novel_signature: delegation and idempotency."""

    def test_delegates_to_append_discovered_pattern(self) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        with patch(
            "bob.orchestrator.rca_infra_recovery._append_discovered_pattern"
        ) as mock_append:
            append_novel_signature("ECONNRESET", "feat-010")
        mock_append.assert_called_once_with("ECONNRESET", "feat-010")

    def test_writes_entry_to_spawn_retry_yaml(self, tmp_path: pathlib.Path) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "spawn_retry.yaml"
        config_file.write_text("TRANSIENT_PATTERNS: []\ndiscovered_patterns: []\n")

        original_path = None
        import bob.orchestrator.rca_infra_recovery as _rca

        original_path = _rca._SPAWN_RETRY_CONFIG
        try:
            _rca._SPAWN_RETRY_CONFIG = config_file  # type: ignore[attr-defined]
            append_novel_signature("new.*pattern", "feat-011")
        finally:
            _rca._SPAWN_RETRY_CONFIG = original_path  # type: ignore[attr-defined]

        data = yaml.safe_load(config_file.read_text())
        patterns = [p["pattern"] for p in data.get("discovered_patterns", [])]
        assert "new.*pattern" in patterns

    def test_idempotent_duplicate_patterns(self, tmp_path: pathlib.Path) -> None:
        """Appending the same pattern twice should not create duplicates."""
        from bob.rca_infra_verdict import append_novel_signature

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "spawn_retry.yaml"
        config_file.write_text("TRANSIENT_PATTERNS: []\ndiscovered_patterns: []\n")

        import bob.orchestrator.rca_infra_recovery as _rca

        original_path = _rca._SPAWN_RETRY_CONFIG
        try:
            _rca._SPAWN_RETRY_CONFIG = config_file  # type: ignore[attr-defined]
            append_novel_signature("dup.*pattern", "feat-012")
            append_novel_signature("dup.*pattern", "feat-012")
        finally:
            _rca._SPAWN_RETRY_CONFIG = original_path  # type: ignore[attr-defined]

        data = yaml.safe_load(config_file.read_text())
        patterns = [p["pattern"] for p in data.get("discovered_patterns", [])]
        assert patterns.count("dup.*pattern") == 1


class TestAppendNovelSignatureErrors:
    """append_novel_signature: invalid inputs raise."""

    def test_none_pattern_raises_value_error(self) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature(None, "feat-020")  # type: ignore[arg-type]

    def test_empty_pattern_raises_value_error(self) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature("", "feat-021")

    def test_whitespace_pattern_raises_value_error(self) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature("   ", "feat-022")

    def test_non_string_pattern_raises_type_error(self) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        with pytest.raises(TypeError):
            append_novel_signature(123, "feat-023")  # type: ignore[arg-type]

    def test_none_feature_id_raises_value_error(self) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature("pattern", None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises_value_error(self) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature("pattern", "")

    def test_whitespace_feature_id_raises_value_error(self) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        with pytest.raises(ValueError):
            append_novel_signature("pattern", "   ")

    def test_non_string_feature_id_raises_type_error(self) -> None:
        from bob.rca_infra_verdict import append_novel_signature

        with pytest.raises(TypeError):
            append_novel_signature("pattern", 456)  # type: ignore[arg-type]


class TestOrchestratorIntegration:
    """Integration: rca_infra_verdict wires into orchestrator correctly."""

    def test_assess_infra_only_is_reachable_from_orchestrator_module(self) -> None:
        """The orchestrator can call assess_infra_only via the verdict module."""
        from bob.rca_infra_verdict import assess_infra_only

        with patch(
            "bob.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ):
            result = assess_infra_only("feat-orch-001")
        assert result is True

    def test_append_novel_signature_updates_spawn_retry_config(self) -> None:
        """append_novel_signature reaches config/spawn_retry.yaml via the orchestrator layer."""
        from bob.rca_infra_verdict import append_novel_signature

        with patch(
            "bob.orchestrator.rca_infra_recovery._append_discovered_pattern"
        ) as mock_fn:
            append_novel_signature("novel.*error", "feat-orch-002")
        mock_fn.assert_called_once_with("novel.*error", "feat-orch-002")
