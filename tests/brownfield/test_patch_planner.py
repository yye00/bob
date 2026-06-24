"""Tests for bob3.brownfield.patch_planner — BF-7 CodeT patch-mode + reviewable diff-plan artifact.

AC: File exists: tests/brownfield/test_patch_planner.py
AC: pytest: tests/brownfield/test_patch_planner.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bob3.brownfield.patch_planner import (
    PatchPlanner,
    apply_diff_plan,
    check_scope_guard,
    emit_diff_plan,
    generate_diff_plan,
    plan_diff,
    rollback_changes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def feature_id() -> str:
    return "bf7-brownfield-test-fixture-001"


@pytest.fixture()
def scratch_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def sample_py_file(scratch_dir: Path) -> Path:
    src_dir = scratch_dir / "src" / "auth"
    src_dir.mkdir(parents=True)
    py_file = src_dir / "login.py"
    py_file.write_text(
        "def authenticate_user(username, password):\n"
        "    # TODO: check DB\n"
        "    return True\n"
        "\n"
        "def logout_user(session_id):\n"
        "    pass\n"
    )
    return py_file


@pytest.fixture()
def minimal_touches() -> list[dict]:
    return [
        {
            "path": "src/auth/login.py",
            "hunks": [
                {
                    "lines": [1, 3],
                    "op": "replace",
                    "intent": "add OAuth token validation",
                    "surrounding_symbol": "authenticate_user",
                    "new_lines": [
                        "def authenticate_user(username, password):\n",
                        "    # OAuth check\n",
                        "    return bool(username and password)\n",
                    ],
                }
            ],
        }
    ]


# ---------------------------------------------------------------------------
# emit_diff_plan
# ---------------------------------------------------------------------------


class TestEmitDiffPlan:
    def test_creates_diff_plan_yaml(self, feature_id, scratch_dir, minimal_touches):
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        assert plan_path.exists()
        assert plan_path.suffix == ".yaml"

    def test_plan_path_under_bob3_features_dir(self, feature_id, scratch_dir, minimal_touches):
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        expected = scratch_dir / ".bob3" / "features" / feature_id
        assert plan_path.parent == expected

    def test_plan_contains_feature_id(self, feature_id, scratch_dir, minimal_touches):
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        data = yaml.safe_load(plan_path.read_text())
        assert data["feature_id"] == feature_id

    def test_plan_contains_touches(self, feature_id, scratch_dir, minimal_touches):
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        data = yaml.safe_load(plan_path.read_text())
        assert "touches" in data
        assert len(data["touches"]) == 1

    def test_empty_touches_raises(self, feature_id, scratch_dir):
        with pytest.raises(ValueError, match="touches"):
            emit_diff_plan(feature_id, [], workspace=scratch_dir)

    def test_invalid_op_raises(self, feature_id, scratch_dir):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 2], "op": "overwrite", "intent": "x", "surrounding_symbol": "f"}],
            }
        ]
        with pytest.raises(ValueError, match="op"):
            emit_diff_plan(feature_id, touches, workspace=scratch_dir)

    def test_returns_path_object(self, feature_id, scratch_dir, minimal_touches):
        result = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        assert isinstance(result, Path)

    def test_valid_ops_accepted(self, feature_id, scratch_dir):
        for op in ("replace", "insert", "delete"):
            touches = [
                {
                    "path": "src/foo.py",
                    "hunks": [{"lines": [1, 2], "op": op, "intent": "test", "surrounding_symbol": "f"}],
                }
            ]
            plan_path = emit_diff_plan(f"{feature_id}-{op}", touches, workspace=scratch_dir)
            data = yaml.safe_load(plan_path.read_text())
            assert data["touches"][0]["hunks"][0]["op"] == op


# ---------------------------------------------------------------------------
# generate_diff_plan (alias)
# ---------------------------------------------------------------------------


class TestGenerateDiffPlan:
    def test_alias_returns_path(self, feature_id, scratch_dir, minimal_touches):
        result = generate_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        assert isinstance(result, Path)
        assert result.exists()

    def test_empty_touches_raises(self, feature_id, scratch_dir):
        with pytest.raises(ValueError):
            generate_diff_plan(feature_id, [], workspace=scratch_dir)


# ---------------------------------------------------------------------------
# plan_diff (alias for AC: Function defined: bob3.brownfield.patch_planner.plan_diff)
# ---------------------------------------------------------------------------


class TestPlanDiff:
    def test_plan_diff_returns_path(self, feature_id, scratch_dir, minimal_touches):
        result = plan_diff(feature_id, minimal_touches, workspace=scratch_dir)
        assert isinstance(result, Path)
        assert result.exists()

    def test_plan_diff_creates_yaml_with_correct_structure(self, feature_id, scratch_dir, minimal_touches):
        plan_path = plan_diff(feature_id, minimal_touches, workspace=scratch_dir)
        data = yaml.safe_load(plan_path.read_text())
        assert data["feature_id"] == feature_id
        assert "touches" in data

    def test_plan_diff_empty_touches_raises(self, feature_id, scratch_dir):
        with pytest.raises(ValueError):
            plan_diff(feature_id, [], workspace=scratch_dir)


# ---------------------------------------------------------------------------
# apply_diff_plan
# ---------------------------------------------------------------------------


class TestApplyDiffPlan:
    def test_replace_hunk_modifies_file(self, feature_id, scratch_dir, sample_py_file, minimal_touches):
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)
        assert "OAuth" in sample_py_file.read_text()

    def test_backup_created(self, feature_id, scratch_dir, sample_py_file, minimal_touches):
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)
        backup = scratch_dir / ".bob3" / "features" / feature_id / "orig" / "src" / "auth" / "login.py"
        assert backup.exists()

    def test_backup_has_original_content(self, feature_id, scratch_dir, sample_py_file, minimal_touches):
        original = sample_py_file.read_text()
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)
        backup = scratch_dir / ".bob3" / "features" / feature_id / "orig" / "src" / "auth" / "login.py"
        assert backup.read_text() == original

    def test_delete_removes_lines(self, feature_id, scratch_dir, sample_py_file):
        touches = [
            {
                "path": "src/auth/login.py",
                "hunks": [{"lines": [5, 6], "op": "delete", "intent": "remove stub", "surrounding_symbol": "logout_user"}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)
        assert "logout_user" not in sample_py_file.read_text()

    def test_insert_adds_lines(self, feature_id, scratch_dir, sample_py_file):
        touches = [
            {
                "path": "src/auth/login.py",
                "hunks": [
                    {
                        "lines": [1, 1],
                        "op": "insert",
                        "intent": "add import",
                        "surrounding_symbol": "module",
                        "new_lines": ["import logging\n"],
                    }
                ],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)
        assert "import logging" in sample_py_file.read_text()

    def test_missing_file_raises(self, feature_id, scratch_dir):
        touches = [
            {
                "path": "src/ghost.py",
                "hunks": [{"lines": [1, 3], "op": "replace", "intent": "x", "surrounding_symbol": "f", "new_lines": ["# x\n"]}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=scratch_dir)
        with pytest.raises(FileNotFoundError):
            apply_diff_plan(plan_path, workspace=scratch_dir)

    def test_returns_list_of_modified_paths(self, feature_id, scratch_dir, sample_py_file, minimal_touches):
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        result = apply_diff_plan(plan_path, workspace=scratch_dir)
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Path)


# ---------------------------------------------------------------------------
# rollback_changes
# ---------------------------------------------------------------------------


class TestRollbackChanges:
    def test_rollback_restores_original_content(self, feature_id, scratch_dir, sample_py_file, minimal_touches):
        original = sample_py_file.read_text()
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)
        assert sample_py_file.read_text() != original
        rollback_changes(feature_id, workspace=scratch_dir)
        assert sample_py_file.read_text() == original

    def test_rollback_without_apply_raises(self, feature_id, scratch_dir):
        with pytest.raises(FileNotFoundError, match="orig"):
            rollback_changes(feature_id, workspace=scratch_dir)

    def test_rollback_returns_restored_list(self, feature_id, scratch_dir, sample_py_file, minimal_touches):
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)
        restored = rollback_changes(feature_id, workspace=scratch_dir)
        assert isinstance(restored, list)
        assert len(restored) >= 1

    def test_rollback_clears_orig_backups(self, feature_id, scratch_dir, sample_py_file, minimal_touches):
        plan_path = emit_diff_plan(feature_id, minimal_touches, workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)
        orig_dir = scratch_dir / ".bob3" / "features" / feature_id / "orig"
        assert orig_dir.exists()
        rollback_changes(feature_id, workspace=scratch_dir)
        files = [p for p in orig_dir.rglob("*") if p.is_file()]
        assert files == []


# ---------------------------------------------------------------------------
# check_scope_guard
# ---------------------------------------------------------------------------


class TestCheckScopeGuard:
    def test_path_outside_allowlist_raises(self):
        touches = [{"path": "src/evil.py", "hunks": []}]
        with pytest.raises(ValueError, match="scope"):
            check_scope_guard(touches, ["src/safe.py"])

    def test_path_inside_allowlist_passes(self):
        touches = [{"path": "src/safe.py", "hunks": []}]
        check_scope_guard(touches, ["src/safe.py"])  # must not raise

    def test_empty_allowlist_allows_any_path(self):
        touches = [{"path": "src/anything.py", "hunks": []}]
        check_scope_guard(touches, [])  # must not raise

    def test_empty_touches_passes(self):
        check_scope_guard([], ["src/foo.py"])  # must not raise

    def test_one_bad_path_among_good_raises(self):
        touches = [
            {"path": "src/ok.py", "hunks": []},
            {"path": "src/bad.py", "hunks": []},
        ]
        with pytest.raises(ValueError, match="scope"):
            check_scope_guard(touches, ["src/ok.py"])

    def test_error_message_identifies_bad_path(self):
        bad = "src/secret/creds.py"
        touches = [{"path": bad, "hunks": []}]
        with pytest.raises(ValueError, match=bad):
            check_scope_guard(touches, ["src/other.py"])


# ---------------------------------------------------------------------------
# PatchPlanner class
# ---------------------------------------------------------------------------


class TestPatchPlannerClass:
    def test_instantiation(self, scratch_dir):
        planner = PatchPlanner("feat-cls-001", workspace=scratch_dir)
        assert planner.feature_id == "feat-cls-001"
        assert planner.workspace == scratch_dir

    def test_emit_creates_yaml(self, scratch_dir):
        planner = PatchPlanner("feat-cls-002", workspace=scratch_dir)
        touches = [
            {
                "path": "src/x.py",
                "hunks": [{"lines": [1, 2], "op": "replace", "intent": "x", "surrounding_symbol": "f", "new_lines": ["# r\n"]}],
            }
        ]
        plan_path = planner.emit(touches)
        assert plan_path.exists()

    def test_apply_and_rollback_roundtrip(self, scratch_dir):
        src_file = scratch_dir / "src" / "x.py"
        src_file.parent.mkdir(parents=True)
        src_file.write_text("original = True\n")
        original = src_file.read_text()

        planner = PatchPlanner("feat-cls-003", workspace=scratch_dir)
        touches = [
            {
                "path": "src/x.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "swap", "surrounding_symbol": "m", "new_lines": ["changed = True\n"]}],
            }
        ]
        plan_path = planner.emit(touches)
        planner.apply(plan_path)
        assert src_file.read_text() != original
        planner.rollback()
        assert src_file.read_text() == original

    def test_check_scope_raises_for_out_of_scope(self, scratch_dir):
        planner = PatchPlanner("feat-cls-004", workspace=scratch_dir)
        touches = [{"path": "src/evil.py", "hunks": []}]
        with pytest.raises(ValueError, match="scope"):
            planner.check_scope(touches, allowlist=["src/safe.py"])

    def test_check_scope_passes_for_allowed(self, scratch_dir):
        planner = PatchPlanner("feat-cls-005", workspace=scratch_dir)
        touches = [{"path": "src/safe.py", "hunks": []}]
        planner.check_scope(touches, allowlist=["src/safe.py"])  # must not raise


# ---------------------------------------------------------------------------
# Integration: bob3.orchestrator references patch_planner
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    def test_patch_planner_importable_from_brownfield(self):
        from bob3.brownfield import patch_planner  # noqa: F401
        assert hasattr(patch_planner, "plan_diff")
        assert hasattr(patch_planner, "emit_diff_plan")
        assert hasattr(patch_planner, "apply_diff_plan")
        assert hasattr(patch_planner, "rollback_changes")
        assert hasattr(patch_planner, "check_scope_guard")

    def test_orchestrator_exposes_patch_planner(self):
        import bob3.orchestrator as orch
        # The orchestrator should have patch_planner symbols injected
        assert hasattr(orch, "plan_diff") or hasattr(orch, "emit_diff_plan") or hasattr(orch, "apply_diff_plan")
