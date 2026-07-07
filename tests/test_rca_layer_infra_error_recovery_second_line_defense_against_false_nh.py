"""Tests for rca_layer_infra_error_recovery_second_line_defense_against_false_nh.

Covers the public function and the module-level AC requirements:
- Module is importable.
- Named function is callable.
- infra_only verdict → reset to ready + refinement_attempts=0 + novel pattern appended.
- feature_defect verdict → NH stands (returns False).
- mixed verdict → NH stands (returns False).
- auto-reset cap at 3 resets.
- novel pattern auto-appended to spawn_retry.yaml.
- failed_acs code-emission-defect path → grants fresh attempt.
- failed_acs spec-ambiguity path → NH stands.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Module-level import AC
# ---------------------------------------------------------------------------


def test_rca_layer_infra_error_recovery_second_line_defense_against_false_nh() -> None:
    """AC: function is importable and callable; basic smoke test."""
    from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
        rca_layer_infra_error_recovery_second_line_defense_against_false_nh,
    )

    calls: list[dict] = []

    def fake_db_update(feature_id: str, **kwargs: Any) -> None:
        calls.append({"feature_id": feature_id, **kwargs})

    # With infra_only verdict the feature should be reset to ready
    with (
        patch(
            "bob.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="infra_only",
        ),
        patch(
            "bob.orchestrator.rca_infra_recovery._count_rca_resets",
            return_value=0,
        ),
        patch(
            "bob.orchestrator.rca_infra_recovery.harvest_novel_pattern",
            return_value=None,
        ),
        patch(
            "bob.orchestrator.rca_infra_recovery._emit_rca_reset_event",
        ),
    ):
        result = rca_layer_infra_error_recovery_second_line_defense_against_false_nh(
            feature_id="feat-smoke-test-0001",
            project_id="proj-test",
            db_update_fn=fake_db_update,
        )

    assert result is True, "infra_only verdict should return True (reset happened)"
    assert any(c.get("status") == "ready" for c in calls), "db_update_fn should set status=ready"


# ---------------------------------------------------------------------------
# Functional tests
# ---------------------------------------------------------------------------


class TestInfraOnlyVerdictResetsFeature:
    """infra_only verdict → reset to ready with refinement_attempts=0."""

    def test_returns_true_on_infra_only(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_layer_infra_error_recovery_second_line_defense_against_false_nh,
        )

        calls: list[dict] = []

        def db_update(fid: str, **kw: Any) -> None:
            calls.append({"feature_id": fid, **kw})

        with (
            patch(
                "bob.orchestrator.rca_infra_recovery.classify_attempts",
                return_value="infra_only",
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery._count_rca_resets",
                return_value=0,
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery.harvest_novel_pattern",
                return_value=None,
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery._emit_rca_reset_event",
            ),
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against_false_nh(
                feature_id="feat-infra-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is True
        assert calls[0]["status"] == "ready"
        assert calls[0]["refinement_attempts"] == 0

    def test_novel_pattern_appended_when_found(self, tmp_path: pathlib.Path) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_layer_infra_error_recovery_second_line_defense_against_false_nh,
        )

        cfg_file = tmp_path / "config" / "spawn_retry.yaml"
        cfg_file.parent.mkdir(parents=True)
        cfg_file.write_text(
            yaml.dump({"TRANSIENT_PATTERNS": [], "discovered_patterns": []}),
        )

        db_update = MagicMock()

        with (
            patch(
                "bob.orchestrator.rca_infra_recovery.classify_attempts",
                return_value="infra_only",
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery._count_rca_resets",
                return_value=0,
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery.harvest_novel_pattern",
                return_value="novel\\.error\\.pattern",
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery._SPAWN_RETRY_CONFIG",
                cfg_file,
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery._emit_rca_reset_event",
            ),
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against_false_nh(
                feature_id="feat-pattern-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is True
        with cfg_file.open() as fh:
            data = yaml.safe_load(fh)
        patterns = [p["pattern"] for p in data.get("discovered_patterns", [])]
        assert "novel\\.error\\.pattern" in patterns


class TestFeatureDefectVerdictNHStands:
    """feature_defect verdict → returns False (NH transition proceeds)."""

    def test_returns_false_on_feature_defect(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_layer_infra_error_recovery_second_line_defense_against_false_nh,
        )

        db_update = MagicMock()

        with patch(
            "bob.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="feature_defect",
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against_false_nh(
                feature_id="feat-defect-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is False
        db_update.assert_not_called()


class TestMixedVerdictNHStands:
    """mixed verdict → returns False (NH transition proceeds)."""

    def test_returns_false_on_mixed(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_layer_infra_error_recovery_second_line_defense_against_false_nh,
        )

        db_update = MagicMock()

        with patch(
            "bob.orchestrator.rca_infra_recovery.classify_attempts",
            return_value="mixed",
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against_false_nh(
                feature_id="feat-mixed-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is False
        db_update.assert_not_called()


class TestAutoResetCap:
    """After 3 resets, NH stands regardless of infra_only verdict."""

    def test_cap_at_3_resets(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_layer_infra_error_recovery_second_line_defense_against_false_nh,
        )

        db_update = MagicMock()

        with (
            patch(
                "bob.orchestrator.rca_infra_recovery.classify_attempts",
                return_value="infra_only",
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery._count_rca_resets",
                return_value=3,
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery._emit_rca_reset_event",
            ),
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against_false_nh(
                feature_id="feat-cap-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is False
        db_update.assert_not_called()


class TestCodeEmissionDefectPath:
    """failed_acs with pytest: prefix → code_emission_defect → grants fresh attempt."""

    def test_code_defect_grants_fresh_attempt(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_layer_infra_error_recovery_second_line_defense_against_false_nh,
        )

        calls: list[dict] = []

        def db_update(fid: str, **kw: Any) -> None:
            calls.append({"feature_id": fid, **kw})

        with patch(
            "bob.orchestrator.rca_infra_recovery._emit_rca_reset_event",
        ):
            result = rca_layer_infra_error_recovery_second_line_defense_against_false_nh(
                feature_id="feat-codedefect-001",
                project_id="proj-x",
                db_update_fn=db_update,
                failed_acs=["pytest: tests/test_something.py::test_foo failed"],
                refinement_attempts=2,
            )

        assert result is True
        assert any(c.get("status") == "ready" for c in calls)

    def test_code_defect_at_cap_returns_false(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_layer_infra_error_recovery_second_line_defense_against_false_nh,
        )

        db_update = MagicMock()

        result = rca_layer_infra_error_recovery_second_line_defense_against_false_nh(
            feature_id="feat-codedefect-cap",
            project_id="proj-x",
            db_update_fn=db_update,
            failed_acs=["pytest: tests/test_something.py::test_foo failed"],
            refinement_attempts=5,  # at cap
        )

        assert result is False
        db_update.assert_not_called()


class TestSpecAmbiguityPath:
    """failed_acs with no recognized prefix → spec_ambiguity → NH stands."""

    def test_spec_ambiguity_nh_stands(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_layer_infra_error_recovery_second_line_defense_against_false_nh,
        )

        db_update = MagicMock()

        result = rca_layer_infra_error_recovery_second_line_defense_against_false_nh(
            feature_id="feat-spec-ambig",
            project_id="proj-x",
            db_update_fn=db_update,
            failed_acs=["some vague requirement that no code could satisfy"],
            refinement_attempts=1,
        )

        assert result is False
        db_update.assert_not_called()


class TestRcaInfraOnlyRecovery:
    """AC-named canonical entry point rca_infra_only_recovery."""

    def test_function_is_defined(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_infra_only_recovery,
        )

        assert callable(rca_infra_only_recovery)

    def test_infra_only_verdict_resets(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_infra_only_recovery,
        )

        calls: list[dict] = []

        def db_update(fid: str, **kw: Any) -> None:
            calls.append({"feature_id": fid, **kw})

        with (
            patch(
                "bob.orchestrator.rca_infra_recovery.classify_attempts",
                return_value="infra_only",
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery._count_rca_resets",
                return_value=0,
            ),
            patch(
                "bob.orchestrator.rca_infra_recovery.harvest_novel_pattern",
                return_value=None,
            ),
            patch("bob.orchestrator.rca_infra_recovery._emit_rca_reset_event"),
        ):
            result = rca_infra_only_recovery(
                feature_id="feat-canonical-001",
                project_id="proj-x",
                db_update_fn=db_update,
            )

        assert result is True
        assert calls[0]["status"] == "ready"
        assert calls[0]["refinement_attempts"] == 0

    def test_none_feature_id_raises_type_error(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_infra_only_recovery,
        )

        with pytest.raises(TypeError):
            rca_infra_only_recovery(
                feature_id=None,  # type: ignore[arg-type]
                project_id="proj-x",
                db_update_fn=MagicMock(),
            )

    def test_empty_feature_id_raises_value_error(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_infra_only_recovery,
        )

        with pytest.raises(ValueError):
            rca_infra_only_recovery(
                feature_id="   ",
                project_id="proj-x",
                db_update_fn=MagicMock(),
            )

    def test_non_callable_db_fn_raises_type_error(self) -> None:
        from bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh import (
            rca_infra_only_recovery,
        )

        with pytest.raises(TypeError):
            rca_infra_only_recovery(
                feature_id="feat-canonical-002",
                project_id="proj-x",
                db_update_fn="not-callable",  # type: ignore[arg-type]
            )


class TestPublicAPIExports:
    """Module exports expected symbols."""

    def test_module_exports_classify_attempts(self) -> None:
        import bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh as m

        assert hasattr(m, "classify_attempts")

    def test_module_exports_auto_reset_if_infra(self) -> None:
        import bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh as m

        assert hasattr(m, "auto_reset_if_infra")

    def test_module_exports_harvest_novel_pattern(self) -> None:
        import bob.rca_layer_infra_error_recovery_second_line_defense_against_false_nh as m

        assert hasattr(m, "harvest_novel_pattern")
