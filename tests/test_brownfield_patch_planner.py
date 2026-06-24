"""BF-7 — tests for bob.brownfield.patch_planner.

AC: File exists: tests/test_brownfield_patch_planner.py
AC: pytest: tests/test_brownfield_patch_planner.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bob.brownfield.patch_planner import (
    PatchPlanner,
    apply_diff_plan,
    check_scope_guard,
    emit_diff_plan,
    generate_diff_plan,
    plan_diff,
    rollback_changes,
)


# ---------------------------------------------------------------------------
# plan_diff (required by AC: Function defined: bob.brownfield.patch_planner.plan_diff)
# ---------------------------------------------------------------------------


class TestPlanDiff:
    def test_plan_diff_returns_path(self, tmp_path):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [1, 2],
                        "op": "replace",
                        "intent": "add OAuth check",
                        "surrounding_symbol": "handle_request",
                        "new_lines": ["# OAuth\n"],
                    }
                ],
            }
        ]
        result = plan_diff("feat-pd-001", touches, workspace=tmp_path)
        assert isinstance(result, Path)
        assert result.exists()

    def test_plan_diff_yaml_has_correct_feature_id(self, tmp_path):
        touches = [
            {
                "path": "src/bar.py",
                "hunks": [{"lines": [1, 1], "op": "insert", "intent": "add import", "surrounding_symbol": "m", "new_lines": ["import os\n"]}],
            }
        ]
        plan_path = plan_diff("feat-pd-002", touches, workspace=tmp_path)
        data = yaml.safe_load(plan_path.read_text())
        assert data["feature_id"] == "feat-pd-002"

    def test_plan_diff_empty_touches_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            plan_diff("feat-pd-003", [], workspace=tmp_path)

    def test_plan_diff_invalid_op_raises_value_error(self, tmp_path):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 2], "op": "frobnicate", "intent": "bad op", "surrounding_symbol": "f"}],
            }
        ]
        with pytest.raises(ValueError):
            plan_diff("feat-pd-004", touches, workspace=tmp_path)


# ---------------------------------------------------------------------------
# emit_diff_plan
# ---------------------------------------------------------------------------


class TestEmitDiffPlan:
    def test_creates_diff_plan_yaml_in_bob_dir(self, tmp_path):
        touches = [
            {
                "path": "src/x.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f", "new_lines": ["# x\n"]}],
            }
        ]
        plan_path = emit_diff_plan("feat-ep-001", touches, workspace=tmp_path)
        assert plan_path.exists()
        assert ".bob" in str(plan_path)

    def test_plan_contains_touches(self, tmp_path):
        touches = [
            {
                "path": "src/auth.py",
                "hunks": [{"lines": [5, 7], "op": "delete", "intent": "remove dead code", "surrounding_symbol": "cleanup"}],
            }
        ]
        plan_path = emit_diff_plan("feat-ep-002", touches, workspace=tmp_path)
        data = yaml.safe_load(plan_path.read_text())
        assert data["touches"][0]["path"] == "src/auth.py"

    def test_all_valid_ops_accepted(self, tmp_path):
        for i, op in enumerate(("replace", "insert", "delete")):
            touches = [{"path": "src/f.py", "hunks": [{"lines": [1, 1], "op": op, "intent": "t", "surrounding_symbol": "s"}]}]
            plan_path = emit_diff_plan(f"feat-ep-op-{i}", touches, workspace=tmp_path)
            data = yaml.safe_load(plan_path.read_text())
            assert data["touches"][0]["hunks"][0]["op"] == op

    def test_empty_touches_raises(self, tmp_path):
        with pytest.raises(ValueError, match="touches"):
            emit_diff_plan("feat-ep-empty", [], workspace=tmp_path)

    def test_invalid_op_raises(self, tmp_path):
        touches = [{"path": "src/f.py", "hunks": [{"lines": [1, 1], "op": "overwrite", "intent": "x", "surrounding_symbol": "f"}]}]
        with pytest.raises(ValueError, match="op"):
            emit_diff_plan("feat-ep-bad-op", touches, workspace=tmp_path)


# ---------------------------------------------------------------------------
# apply_diff_plan
# ---------------------------------------------------------------------------


class TestApplyDiffPlan:
    def _make_file(self, tmp_path: Path, rel_path: str, content: str) -> Path:
        p = tmp_path / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def test_replace_op_modifies_file(self, tmp_path):
        self._make_file(tmp_path, "src/target.py", "line1\nline2\nline3\n")
        touches = [
            {
                "path": "src/target.py",
                "hunks": [
                    {"lines": [2, 3], "op": "replace", "intent": "replace line2", "surrounding_symbol": "f", "new_lines": ["REPLACED\n"]},
                ],
            }
        ]
        plan_path = emit_diff_plan("feat-ap-001", touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        content = (tmp_path / "src/target.py").read_text()
        assert "REPLACED" in content
        assert "line2" not in content

    def test_delete_op_removes_lines(self, tmp_path):
        self._make_file(tmp_path, "src/target.py", "keep_this\ndelete_me\nalso_keep\n")
        touches = [
            {
                "path": "src/target.py",
                "hunks": [{"lines": [2, 3], "op": "delete", "intent": "remove line", "surrounding_symbol": "f"}],
            }
        ]
        plan_path = emit_diff_plan("feat-ap-002", touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        content = (tmp_path / "src/target.py").read_text()
        assert "delete_me" not in content
        assert "keep_this" in content

    def test_backup_created_before_modification(self, tmp_path):
        original = "original content\n"
        self._make_file(tmp_path, "src/target.py", original)
        touches = [
            {
                "path": "src/target.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "modify", "surrounding_symbol": "f", "new_lines": ["changed\n"]}],
            }
        ]
        plan_path = emit_diff_plan("feat-ap-003", touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        backup = tmp_path / ".bob" / "features" / "feat-ap-003" / "orig" / "src" / "target.py"
        assert backup.exists()
        assert backup.read_text() == original

    def test_missing_file_raises_file_not_found(self, tmp_path):
        touches = [
            {
                "path": "src/ghost.py",
                "hunks": [{"lines": [1, 2], "op": "replace", "intent": "x", "surrounding_symbol": "f", "new_lines": ["# x\n"]}],
            }
        ]
        plan_path = emit_diff_plan("feat-ap-004", touches, workspace=tmp_path)
        with pytest.raises(FileNotFoundError):
            apply_diff_plan(plan_path, workspace=tmp_path)

    def test_returns_list_of_modified_paths(self, tmp_path):
        self._make_file(tmp_path, "src/x.py", "x = 1\n")
        touches = [
            {
                "path": "src/x.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f", "new_lines": ["x = 2\n"]}],
            }
        ]
        plan_path = emit_diff_plan("feat-ap-005", touches, workspace=tmp_path)
        result = apply_diff_plan(plan_path, workspace=tmp_path)
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Path)


# ---------------------------------------------------------------------------
# rollback_changes
# ---------------------------------------------------------------------------


class TestRollbackChanges:
    def test_rollback_restores_original(self, tmp_path):
        target = tmp_path / "src" / "r.py"
        target.parent.mkdir(parents=True)
        original = "original\n"
        target.write_text(original)
        touches = [
            {
                "path": "src/r.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f", "new_lines": ["changed\n"]}],
            }
        ]
        plan_path = emit_diff_plan("feat-rb-001", touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        assert target.read_text() != original
        rollback_changes("feat-rb-001", workspace=tmp_path)
        assert target.read_text() == original

    def test_rollback_without_apply_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="orig"):
            rollback_changes("feat-rb-nobackup", workspace=tmp_path)

    def test_rollback_returns_restored_paths(self, tmp_path):
        target = tmp_path / "src" / "r2.py"
        target.parent.mkdir(parents=True)
        target.write_text("data\n")
        touches = [
            {
                "path": "src/r2.py",
                "hunks": [{"lines": [1, 1], "op": "delete", "intent": "x", "surrounding_symbol": "f"}],
            }
        ]
        plan_path = emit_diff_plan("feat-rb-002", touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        restored = rollback_changes("feat-rb-002", workspace=tmp_path)
        assert isinstance(restored, list)
        assert len(restored) >= 1


# ---------------------------------------------------------------------------
# check_scope_guard
# ---------------------------------------------------------------------------


class TestCheckScopeGuard:
    def test_out_of_scope_path_raises(self):
        touches = [{"path": "src/evil.py", "hunks": []}]
        with pytest.raises(ValueError, match="scope"):
            check_scope_guard(touches, ["src/safe.py"])

    def test_in_scope_path_passes(self):
        touches = [{"path": "src/safe.py", "hunks": []}]
        check_scope_guard(touches, ["src/safe.py"])

    def test_empty_allowlist_allows_any_path(self):
        check_scope_guard([{"path": "src/anything.py", "hunks": []}], [])

    def test_empty_touches_always_passes(self):
        check_scope_guard([], ["src/foo.py"])

    def test_error_message_names_bad_path(self):
        bad = "src/bad/module.py"
        with pytest.raises(ValueError, match=bad):
            check_scope_guard([{"path": bad, "hunks": []}], ["src/good.py"])


# ---------------------------------------------------------------------------
# PatchPlanner class
# ---------------------------------------------------------------------------


class TestPatchPlannerClass:
    def test_instantiation_with_workspace(self, tmp_path):
        planner = PatchPlanner("feat-cls-001", workspace=tmp_path)
        assert planner.feature_id == "feat-cls-001"
        assert planner.workspace == tmp_path

    def test_emit_returns_path(self, tmp_path):
        planner = PatchPlanner("feat-cls-002", workspace=tmp_path)
        touches = [{"path": "src/x.py", "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f", "new_lines": ["# x\n"]}]}]
        plan_path = planner.emit(touches)
        assert isinstance(plan_path, Path)
        assert plan_path.exists()

    def test_apply_and_rollback_roundtrip(self, tmp_path):
        target = tmp_path / "src" / "rnd.py"
        target.parent.mkdir(parents=True)
        original = "original_content = True\n"
        target.write_text(original)

        planner = PatchPlanner("feat-cls-003", workspace=tmp_path)
        touches = [{"path": "src/rnd.py", "hunks": [{"lines": [1, 1], "op": "replace", "intent": "change", "surrounding_symbol": "m", "new_lines": ["changed = True\n"]}]}]
        plan_path = planner.emit(touches)
        planner.apply(plan_path)
        assert target.read_text() != original
        planner.rollback()
        assert target.read_text() == original

    def test_check_scope_raises_for_out_of_scope(self, tmp_path):
        planner = PatchPlanner("feat-cls-004", workspace=tmp_path)
        with pytest.raises(ValueError, match="scope"):
            planner.check_scope([{"path": "src/evil.py", "hunks": []}], allowlist=["src/safe.py"])

    def test_check_scope_passes_for_allowed(self, tmp_path):
        planner = PatchPlanner("feat-cls-005", workspace=tmp_path)
        planner.check_scope([{"path": "src/safe.py", "hunks": []}], allowlist=["src/safe.py"])


# ---------------------------------------------------------------------------
# Orchestrator integration
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    def test_plan_diff_importable_from_orchestrator(self):
        import bob.orchestrator as orch
        assert hasattr(orch, "plan_diff") or hasattr(orch, "emit_diff_plan") or hasattr(orch, "apply_diff_plan"), (
            "bob.orchestrator must expose at least one patch_planner symbol"
        )

    def test_patch_planner_module_has_required_symbols(self):
        from bob.brownfield import patch_planner
        for name in ("plan_diff", "emit_diff_plan", "apply_diff_plan", "rollback_changes", "check_scope_guard"):
            assert hasattr(patch_planner, name), f"patch_planner missing symbol: {name}"
