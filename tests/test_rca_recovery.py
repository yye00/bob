"""Tests for bob3.rca_recovery — second-line defense against false NH escalation.

Covers:
- is_infra_only: returns True/False based on RCA verdict, raises on bad input
- learn_signature: appends novel patterns to spawn_retry.yaml, raises on bad input
- Integration with orchestrator auto_reset_if_infra
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest


class TestIsInfraOnly:
    """bob3.rca_recovery.is_infra_only: classification predicate."""

    def test_returns_true_when_verdict_infra_only(self) -> None:
        from bob3.rca_recovery import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ):
            result = is_infra_only("feat-rca-001")
        assert result is True

    def test_returns_false_when_verdict_feature_defect(self) -> None:
        from bob3.rca_recovery import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            result = is_infra_only("feat-rca-002")
        assert result is False

    def test_returns_false_when_verdict_mixed(self) -> None:
        from bob3.rca_recovery import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="mixed",
        ):
            result = is_infra_only("feat-rca-003")
        assert result is False

    def test_none_feature_id_raises_value_error(self) -> None:
        from bob3.rca_recovery import is_infra_only

        with pytest.raises(ValueError):
            is_infra_only(None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises_value_error(self) -> None:
        from bob3.rca_recovery import is_infra_only

        with pytest.raises(ValueError):
            is_infra_only("")

    def test_whitespace_feature_id_raises_value_error(self) -> None:
        from bob3.rca_recovery import is_infra_only

        with pytest.raises(ValueError):
            is_infra_only("   ")

    def test_non_string_feature_id_raises_type_error(self) -> None:
        from bob3.rca_recovery import is_infra_only

        with pytest.raises(TypeError):
            is_infra_only(42)  # type: ignore[arg-type]

    def test_returns_bool(self) -> None:
        from bob3.rca_recovery import is_infra_only

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            result = is_infra_only("feat-rca-004")
        assert isinstance(result, bool)

    def test_passes_workspace_to_classify_attempts(self, tmp_path: pathlib.Path) -> None:
        import bob3.orchestrator.rca_infra_recovery as _rca_mod
        from bob3.rca_recovery import is_infra_only

        with patch.object(
            _rca_mod, "classify_attempts", return_value="feature_defect"
        ) as mock_classify:
            is_infra_only("feat-rca-005", workspace=tmp_path)
        mock_classify.assert_called_once_with("feat-rca-005", workspace=tmp_path)

    def test_no_logs_does_not_raise(self, tmp_path: pathlib.Path) -> None:
        from bob3.rca_recovery import is_infra_only

        # With empty workspace, should return a bool without raising
        result = is_infra_only("feat-rca-boundary-001", workspace=tmp_path)
        assert isinstance(result, bool)


class TestLearnSignature:
    """bob3.rca_recovery.learn_signature: persist novel infra signatures."""

    def test_appends_pattern_to_spawn_retry_yaml(self, tmp_path: pathlib.Path) -> None:
        import yaml

        from bob3.rca_recovery import learn_signature

        config_path = tmp_path / "config" / "spawn_retry.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("{}\n")

        with patch(
            "bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG",
            config_path,
        ):
            learn_signature("ECONNABORTED", "feat-learn-001")

        data = yaml.safe_load(config_path.read_text())
        patterns = [p["pattern"] for p in data.get("discovered_patterns", [])]
        assert "ECONNABORTED" in patterns

    def test_duplicate_pattern_is_idempotent(self, tmp_path: pathlib.Path) -> None:
        import yaml

        from bob3.rca_recovery import learn_signature

        config_path = tmp_path / "config" / "spawn_retry.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("{}\n")

        with patch(
            "bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG",
            config_path,
        ):
            learn_signature("ECONNABORTED", "feat-learn-002")
            learn_signature("ECONNABORTED", "feat-learn-002")

        data = yaml.safe_load(config_path.read_text())
        patterns = [p["pattern"] for p in data.get("discovered_patterns", [])]
        assert patterns.count("ECONNABORTED") == 1

    def test_creates_config_dir_if_missing(self, tmp_path: pathlib.Path) -> None:
        from bob3.rca_recovery import learn_signature

        config_path = tmp_path / "config" / "spawn_retry.yaml"

        with patch(
            "bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG",
            config_path,
        ):
            learn_signature("socket hang up", "feat-learn-003")

        assert config_path.exists()

    def test_none_pattern_raises_value_error(self) -> None:
        from bob3.rca_recovery import learn_signature

        with pytest.raises(ValueError):
            learn_signature(None, "feat-learn-004")  # type: ignore[arg-type]

    def test_empty_pattern_raises_value_error(self) -> None:
        from bob3.rca_recovery import learn_signature

        with pytest.raises(ValueError):
            learn_signature("", "feat-learn-005")

    def test_whitespace_pattern_raises_value_error(self) -> None:
        from bob3.rca_recovery import learn_signature

        with pytest.raises(ValueError):
            learn_signature("   ", "feat-learn-006")

    def test_non_string_pattern_raises_type_error(self) -> None:
        from bob3.rca_recovery import learn_signature

        with pytest.raises(TypeError):
            learn_signature(123, "feat-learn-007")  # type: ignore[arg-type]

    def test_none_feature_id_raises_value_error(self) -> None:
        from bob3.rca_recovery import learn_signature

        with pytest.raises(ValueError):
            learn_signature("ECONNABORTED", None)  # type: ignore[arg-type]

    def test_empty_feature_id_raises_value_error(self) -> None:
        from bob3.rca_recovery import learn_signature

        with pytest.raises(ValueError):
            learn_signature("ECONNABORTED", "")

    def test_non_string_feature_id_raises_type_error(self) -> None:
        from bob3.rca_recovery import learn_signature

        with pytest.raises(TypeError):
            learn_signature("ECONNABORTED", 99)  # type: ignore[arg-type]

    def test_stored_entry_includes_confidence_field(self, tmp_path: pathlib.Path) -> None:
        import yaml

        from bob3.rca_recovery import learn_signature

        config_path = tmp_path / "config" / "spawn_retry.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("{}\n")

        with patch(
            "bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG",
            config_path,
        ):
            learn_signature("novel_error_code_42", "feat-learn-008")

        data = yaml.safe_load(config_path.read_text())
        entries = data.get("discovered_patterns", [])
        assert len(entries) == 1
        assert "confidence" in entries[0]
        assert "discovered_at" in entries[0]


class TestOrchestratorIntegration:
    """Integration: auto_reset_if_infra uses is_infra_only and learn_signature path."""

    def test_auto_reset_resets_to_ready_on_infra_only(self) -> None:
        from bob3.orchestrator.rca_infra_recovery import auto_reset_if_infra

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
                feature_id="feat-integ-001",
                project_id="proj-001",
                db_update_fn=db_update,
            )

        assert result is True
        db_update.assert_called_once()
        call_kwargs = db_update.call_args
        assert call_kwargs[1].get("status") == "ready"
        assert call_kwargs[1].get("refinement_attempts") == 0

    def test_auto_reset_returns_false_on_feature_defect(self) -> None:
        from bob3.orchestrator.rca_infra_recovery import auto_reset_if_infra

        db_update = MagicMock()

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            result = auto_reset_if_infra(
                feature_id="feat-integ-002",
                project_id="proj-001",
                db_update_fn=db_update,
            )

        assert result is False
        db_update.assert_not_called()

    def test_novel_pattern_is_appended_on_infra_only(self, tmp_path: pathlib.Path) -> None:
        import yaml

        from bob3.orchestrator.rca_infra_recovery import auto_reset_if_infra

        config_path = tmp_path / "config" / "spawn_retry.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.write_text("{}\n")

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
                return_value="novel_infra_signature",
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG",
                config_path,
            ),
            patch("bob3.orchestrator.rca_infra_recovery._emit_rca_reset_event"),
        ):
            result = auto_reset_if_infra(
                feature_id="feat-integ-003",
                project_id="proj-001",
                db_update_fn=db_update,
            )

        assert result is True
        data = yaml.safe_load(config_path.read_text())
        patterns = [p["pattern"] for p in data.get("discovered_patterns", [])]
        assert "novel_infra_signature" in patterns

    def test_rca_recovery_is_infra_only_consistent_with_orchestrator(
        self, tmp_path: pathlib.Path
    ) -> None:
        """is_infra_only() and auto_reset_if_infra() use the same classify_attempts logic."""
        import bob3.orchestrator.rca_infra_recovery as _rca_mod
        from bob3.rca_recovery import is_infra_only

        # Patch at the module level where classify_attempts lives
        with patch.object(_rca_mod, "classify_attempts", return_value="infra_only"):
            result = is_infra_only("feat-integ-004", workspace=tmp_path)

        assert result is True
