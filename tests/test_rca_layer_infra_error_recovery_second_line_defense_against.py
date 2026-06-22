"""Tests for rca_layer_infra_error_recovery_second_line_defense_against.

Covers:
- Module is importable.
- Named function is callable and returns bool.
- infra_only verdict → reset to ready + refinement_attempts=0.
- feature_defect verdict → NH stands (returns False).
- mixed verdict → NH stands (returns False).
- auto-reset cap at 3 resets.
- novel pattern auto-appended to spawn_retry.yaml.
- failed_acs code-emission-defect path → grants fresh attempt.
- failed_acs spec-ambiguity path → NH stands.
- Module exports classify_attempts, auto_reset_if_infra, harvest_novel_pattern.
"""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml


def test_rca_layer_infra_error_recovery_second_line_defense_against() -> None:
    """AC: function is importable, callable; smoke test with infra_only verdict."""
    from bob3.rca_layer_infra_error_recovery_second_line_defense_against import (
        rca_layer_infra_error_recovery_second_line_defense_against,
    )

    calls: list[dict] = []

    def fake_db_update(feature_id: str, **kwargs: Any) -> None:
        calls.append({"feature_id": feature_id, **kwargs})

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
        result = rca_layer_infra_error_recovery_second_line_defense_against(
            feature_id="feat-smoke-0001",
            project_id="proj-test",
            db_update_fn=fake_db_update,
        )

    assert result is True, "infra_only verdict should return True (reset happened)"
    assert any(c.get("status") == "ready" for c in calls), "db_update_fn should set status=ready"


class TestInfraOnlyResets:
    """infra_only verdict resets the feature to ready."""

    def test_returns_true_and_sets_ready(self) -> None:
        from bob3.rca_layer_infra_error_recovery_second_line_defense_against import (
            rca_layer_infra_error_recovery_second_line_defense_against,
        )

        calls: list[dict] = []

        def db_update(fid: str, **kw: Any) -> None:
            calls.append({"feature_id": fid, **kw})

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
            result = rca_layer_infra_error_recovery_second_line_defense_against(
                feature_id="feat-infra-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is True
        assert calls[0]["status"] == "ready"
        assert calls[0]["refinement_attempts"] == 0

    def test_novel_pattern_appended(self, tmp_path: pathlib.Path) -> None:
        from bob3.rca_layer_infra_error_recovery_second_line_defense_against import (
            rca_layer_infra_error_recovery_second_line_defense_against,
        )

        cfg_file = tmp_path / "config" / "spawn_retry.yaml"
        cfg_file.parent.mkdir(parents=True)
        cfg_file.write_text(
            yaml.dump({"TRANSIENT_PATTERNS": [], "discovered_patterns": []}),
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
                return_value="novel\\.error\\.sig",
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG",
                cfg_file,
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery._emit_rca_reset_event",
            ),
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against(
                feature_id="feat-pattern-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is True
        with cfg_file.open() as fh:
            data = yaml.safe_load(fh)
        patterns = [p["pattern"] for p in data.get("discovered_patterns", [])]
        assert "novel\\.error\\.sig" in patterns


class TestFeatureDefectNH:
    """feature_defect verdict → NH stands."""

    def test_returns_false(self) -> None:
        from bob3.rca_layer_infra_error_recovery_second_line_defense_against import (
            rca_layer_infra_error_recovery_second_line_defense_against,
        )

        db_update = MagicMock()

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against(
                feature_id="feat-defect-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is False
        db_update.assert_not_called()


class TestMixedVerdictNH:
    """mixed verdict → NH stands."""

    def test_returns_false(self) -> None:
        from bob3.rca_layer_infra_error_recovery_second_line_defense_against import (
            rca_layer_infra_error_recovery_second_line_defense_against,
        )

        db_update = MagicMock()

        with patch(
            "bob3.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="mixed",
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against(
                feature_id="feat-mixed-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is False
        db_update.assert_not_called()


class TestAutoResetCap:
    """After 3 resets, NH stands even on infra_only verdict."""

    def test_cap_at_3(self) -> None:
        from bob3.rca_layer_infra_error_recovery_second_line_defense_against import (
            rca_layer_infra_error_recovery_second_line_defense_against,
        )

        db_update = MagicMock()

        with (
            patch(
                "bob3.orchestrator.rca_infra_recovery.classify_attempts",
                return_value="infra_only",
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery._count_rca_resets",
                return_value=3,
            ),
            patch(
                "bob3.orchestrator.rca_infra_recovery._emit_rca_reset_event",
            ),
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against(
                feature_id="feat-cap-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is False
        db_update.assert_not_called()


class TestCodeEmissionDefectPath:
    """failed_acs with pytest: prefix → code_emission_defect → fresh attempt."""

    def test_grants_fresh_attempt(self) -> None:
        from bob3.rca_layer_infra_error_recovery_second_line_defense_against import (
            rca_layer_infra_error_recovery_second_line_defense_against,
        )

        calls: list[dict] = []

        def db_update(fid: str, **kw: Any) -> None:
            calls.append({"feature_id": fid, **kw})

        with patch(
            "bob3.orchestrator.rca_infra_recovery._emit_rca_reset_event",
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against(
                feature_id="feat-codedefect-001",
                project_id="proj-x",
                db_update_fn=db_update,
                failed_acs=["pytest: tests/test_something.py::test_foo failed"],
                refinement_attempts=2,
            )

        assert result is True
        assert any(c.get("status") == "ready" for c in calls)

    def test_at_cap_returns_false(self) -> None:
        from bob3.rca_layer_infra_error_recovery_second_line_defense_against import (
            rca_layer_infra_error_recovery_second_line_defense_against,
        )

        db_update = MagicMock()

        result = rca_layer_infra_error_recovery_second_line_defense_against(
            feature_id="feat-codedefect-cap",
            project_id="proj-x",
            db_update_fn=db_update,
            failed_acs=["pytest: tests/test_something.py::test_foo failed"],
            refinement_attempts=5,
        )

        assert result is False
        db_update.assert_not_called()


class TestSpecAmbiguityPath:
    """Unrecognized failed_acs → spec_ambiguity → NH stands."""

    def test_returns_false(self) -> None:
        from bob3.rca_layer_infra_error_recovery_second_line_defense_against import (
            rca_layer_infra_error_recovery_second_line_defense_against,
        )

        db_update = MagicMock()

        result = rca_layer_infra_error_recovery_second_line_defense_against(
            feature_id="feat-spec-ambig",
            project_id="proj-x",
            db_update_fn=db_update,
            failed_acs=["some vague requirement that no code could satisfy"],
            refinement_attempts=1,
        )

        assert result is False
        db_update.assert_not_called()


class TestPublicAPIExports:
    """Module exports expected symbols."""

    def test_exports_classify_attempts(self) -> None:
        import bob3.rca_layer_infra_error_recovery_second_line_defense_against as m

        assert hasattr(m, "classify_attempts")

    def test_exports_auto_reset_if_infra(self) -> None:
        import bob3.rca_layer_infra_error_recovery_second_line_defense_against as m

        assert hasattr(m, "auto_reset_if_infra")

    def test_exports_harvest_novel_pattern(self) -> None:
        import bob3.rca_layer_infra_error_recovery_second_line_defense_against as m

        assert hasattr(m, "harvest_novel_pattern")

    def test_exports_main_function(self) -> None:
        import bob3.rca_layer_infra_error_recovery_second_line_defense_against as m

        assert hasattr(m, "rca_layer_infra_error_recovery_second_line_defense_against")
        assert callable(m.rca_layer_infra_error_recovery_second_line_defense_against)
