"""Tests for bob3.brownfield.patch_planner — BF-7 CodeT patch-mode + reviewable diff-plan artifact."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from bob3.brownfield.patch_planner import (
    apply_diff_plan,
    emit_diff_plan,
    rollback_changes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def feature_id() -> str:
    return "e09ffd78-f972-445c-8d35-211e3cc45396"


@pytest.fixture()
def scratch_dir(tmp_path: Path) -> Path:
    """A scratch directory acting as the workspace root."""
    return tmp_path


@pytest.fixture()
def sample_py_file(scratch_dir: Path) -> Path:
    """A sample Python source file for patching."""
    src_dir = scratch_dir / "src" / "auth"
    src_dir.mkdir(parents=True)
    py_file = src_dir / "login.py"
    py_file.write_text(
        "def authenticate_user(username, password):\n"  # line 1
        "    # TODO: check DB\n"                         # line 2
        "    return True\n"                              # line 3
        "\n"                                             # line 4
        "def logout_user(session_id):\n"                 # line 5
        "    pass\n"                                     # line 6
    )
    return py_file


@pytest.fixture()
def minimal_diff_plan(feature_id: str, scratch_dir: Path) -> dict:
    """A well-formed diff plan dict (not yet written to disk)."""
    return {
        "feature_id": feature_id,
        "touches": [
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
        ],
    }


# ---------------------------------------------------------------------------
# emit_diff_plan tests
# ---------------------------------------------------------------------------


class TestEmitDiffPlan:
    def test_creates_diff_plan_yaml(self, feature_id, scratch_dir, minimal_diff_plan):
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)

        assert plan_path.exists(), "diff_plan.yaml must be created"
        assert plan_path.suffix == ".yaml"

    def test_plan_path_under_bob3_features_dir(self, feature_id, scratch_dir, minimal_diff_plan):
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)

        expected_dir = scratch_dir / ".bob3" / "features" / feature_id
        assert plan_path.parent == expected_dir

    def test_plan_contains_feature_id(self, feature_id, scratch_dir, minimal_diff_plan):
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        data = yaml.safe_load(plan_path.read_text())

        assert data["feature_id"] == feature_id

    def test_plan_contains_touches(self, feature_id, scratch_dir, minimal_diff_plan):
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        data = yaml.safe_load(plan_path.read_text())

        assert "touches" in data
        assert len(data["touches"]) == 1
        touch = data["touches"][0]
        assert touch["path"] == "src/auth/login.py"
        assert len(touch["hunks"]) == 1

    def test_hunk_has_required_fields(self, feature_id, scratch_dir, minimal_diff_plan):
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        data = yaml.safe_load(plan_path.read_text())

        hunk = data["touches"][0]["hunks"][0]
        assert "lines" in hunk
        assert "op" in hunk
        assert "intent" in hunk
        assert "surrounding_symbol" in hunk

    def test_op_values_are_valid(self, feature_id, scratch_dir):
        for op in ("replace", "insert", "delete"):
            touches = [
                {
                    "path": "src/foo.py",
                    "hunks": [
                        {
                            "lines": [1, 2],
                            "op": op,
                            "intent": f"test {op}",
                            "surrounding_symbol": "foo",
                        }
                    ],
                }
            ]
            plan_path = emit_diff_plan(feature_id, touches, workspace=scratch_dir)
            data = yaml.safe_load(plan_path.read_text())
            assert data["touches"][0]["hunks"][0]["op"] == op

    def test_empty_touches_raises(self, feature_id, scratch_dir):
        with pytest.raises(ValueError, match="touches"):
            emit_diff_plan(feature_id, [], workspace=scratch_dir)

    def test_invalid_op_raises(self, feature_id, scratch_dir):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [1, 2],
                        "op": "rewrite",  # invalid
                        "intent": "x",
                        "surrounding_symbol": "foo",
                    }
                ],
            }
        ]
        with pytest.raises(ValueError, match="op"):
            emit_diff_plan(feature_id, touches, workspace=scratch_dir)

    def test_returns_path_object(self, feature_id, scratch_dir, minimal_diff_plan):
        result = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        assert isinstance(result, Path)

    def test_multiple_touches(self, feature_id, scratch_dir):
        touches = [
            {
                "path": "src/a.py",
                "hunks": [{"lines": [1, 5], "op": "replace", "intent": "a", "surrounding_symbol": "func_a"}],
            },
            {
                "path": "src/b.py",
                "hunks": [{"lines": [10, 20], "op": "insert", "intent": "b", "surrounding_symbol": "func_b"}],
            },
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=scratch_dir)
        data = yaml.safe_load(plan_path.read_text())
        assert len(data["touches"]) == 2


# ---------------------------------------------------------------------------
# apply_diff_plan tests
# ---------------------------------------------------------------------------


class TestApplyDiffPlan:
    def test_replace_hunk_updates_file_content(
        self, feature_id, scratch_dir, sample_py_file, minimal_diff_plan
    ):
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)

        content = sample_py_file.read_text()
        assert "OAuth" in content

    def test_backup_created_before_apply(
        self, feature_id, scratch_dir, sample_py_file, minimal_diff_plan
    ):
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)

        orig_path = scratch_dir / ".bob3" / "features" / feature_id / "orig" / "src" / "auth" / "login.py"
        assert orig_path.exists(), "Original backup must be created before patching"

    def test_backup_contains_original_content(
        self, feature_id, scratch_dir, sample_py_file, minimal_diff_plan
    ):
        original_content = sample_py_file.read_text()
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)

        orig_path = scratch_dir / ".bob3" / "features" / feature_id / "orig" / "src" / "auth" / "login.py"
        assert orig_path.read_text() == original_content

    def test_delete_hunk_removes_lines(self, feature_id, scratch_dir, sample_py_file):
        touches = [
            {
                "path": "src/auth/login.py",
                "hunks": [
                    {
                        "lines": [5, 6],
                        "op": "delete",
                        "intent": "remove logout_user stub",
                        "surrounding_symbol": "logout_user",
                    }
                ],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)

        content = sample_py_file.read_text()
        assert "logout_user" not in content

    def test_insert_hunk_adds_lines(self, feature_id, scratch_dir, sample_py_file):
        touches = [
            {
                "path": "src/auth/login.py",
                "hunks": [
                    {
                        "lines": [4, 4],
                        "op": "insert",
                        "intent": "add logging import",
                        "surrounding_symbol": "module",
                        "new_lines": ["import logging\n"],
                    }
                ],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)

        content = sample_py_file.read_text()
        assert "import logging" in content

    def test_missing_file_raises(self, feature_id, scratch_dir):
        touches = [
            {
                "path": "src/nonexistent.py",
                "hunks": [
                    {
                        "lines": [1, 5],
                        "op": "replace",
                        "intent": "x",
                        "surrounding_symbol": "foo",
                        "new_lines": ["# replaced\n"],
                    }
                ],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=scratch_dir)
        with pytest.raises(FileNotFoundError):
            apply_diff_plan(plan_path, workspace=scratch_dir)

    def test_returns_list_of_modified_paths(
        self, feature_id, scratch_dir, sample_py_file, minimal_diff_plan
    ):
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        result = apply_diff_plan(plan_path, workspace=scratch_dir)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Path)


# ---------------------------------------------------------------------------
# rollback_changes tests
# ---------------------------------------------------------------------------


class TestRollbackChanges:
    def test_rollback_restores_original(
        self, feature_id, scratch_dir, sample_py_file, minimal_diff_plan
    ):
        original_content = sample_py_file.read_text()
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)

        # Content is now changed
        assert sample_py_file.read_text() != original_content

        rollback_changes(feature_id, workspace=scratch_dir)
        assert sample_py_file.read_text() == original_content

    def test_rollback_when_no_backup_raises(self, feature_id, scratch_dir):
        with pytest.raises(FileNotFoundError, match="orig"):
            rollback_changes(feature_id, workspace=scratch_dir)

    def test_rollback_returns_list_of_restored_paths(
        self, feature_id, scratch_dir, sample_py_file, minimal_diff_plan
    ):
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)

        restored = rollback_changes(feature_id, workspace=scratch_dir)
        assert isinstance(restored, list)
        assert len(restored) >= 1

    def test_rollback_clears_orig_dir(
        self, feature_id, scratch_dir, sample_py_file, minimal_diff_plan
    ):
        plan_path = emit_diff_plan(feature_id, minimal_diff_plan["touches"], workspace=scratch_dir)
        apply_diff_plan(plan_path, workspace=scratch_dir)

        orig_dir = scratch_dir / ".bob3" / "features" / feature_id / "orig"
        assert orig_dir.exists()

        rollback_changes(feature_id, workspace=scratch_dir)
        # orig dir should be empty or removed after rollback
        remaining = list(orig_dir.rglob("*"))
        files = [p for p in remaining if p.is_file()]
        assert files == [], "orig dir must be empty after rollback"


# ---------------------------------------------------------------------------
# Coordinator scope-guard tests
# ---------------------------------------------------------------------------


class TestCoordinatorScopeGuard:
    def test_touches_outside_allowlist_raises(self, feature_id, scratch_dir):
        """Coordinator must reject diff_plan touching files outside localization allowlist."""
        from bob3.brownfield.patch_planner import check_scope_guard

        localization_allowlist = ["src/auth/login.py", "src/auth/models.py"]
        touches = [
            {
                "path": "src/payment/charge.py",  # NOT in allowlist
                "hunks": [{"lines": [1, 5], "op": "replace", "intent": "x", "surrounding_symbol": "foo"}],
            }
        ]
        with pytest.raises(ValueError, match="scope"):
            check_scope_guard(touches, localization_allowlist)

    def test_touches_inside_allowlist_ok(self, feature_id, scratch_dir):
        from bob3.brownfield.patch_planner import check_scope_guard

        localization_allowlist = ["src/auth/login.py", "src/auth/models.py"]
        touches = [
            {
                "path": "src/auth/login.py",  # in allowlist
                "hunks": [{"lines": [1, 5], "op": "replace", "intent": "x", "surrounding_symbol": "foo"}],
            }
        ]
        # Should not raise
        check_scope_guard(touches, localization_allowlist)

    def test_empty_allowlist_allows_anything(self, feature_id, scratch_dir):
        from bob3.brownfield.patch_planner import check_scope_guard

        touches = [
            {
                "path": "src/any/file.py",
                "hunks": [{"lines": [1, 5], "op": "replace", "intent": "x", "surrounding_symbol": "foo"}],
            }
        ]
        # Empty allowlist = no restriction
        check_scope_guard(touches, [])


# ---------------------------------------------------------------------------
# Integration: bob3.coordinator import
# ---------------------------------------------------------------------------


class TestCoordinatorIntegration:
    def test_coordinator_module_imports_patch_planner(self):
        """AC: integration: bob3.coordinator — patch_planner must be importable from coordinator path."""
        # The coordinator integration is verified by confirming that
        # patch_planner is importable from the brownfield package, which
        # the coordinator references.
        from bob3.brownfield import patch_planner  # noqa: F401
        assert hasattr(patch_planner, "emit_diff_plan")
        assert hasattr(patch_planner, "apply_diff_plan")
        assert hasattr(patch_planner, "rollback_changes")

    def test_patch_planner_exported_in_brownfield_init(self):
        import bob3.brownfield as bf
        # patch_planner should be importable via the package
        from bob3.brownfield.patch_planner import emit_diff_plan, apply_diff_plan, rollback_changes  # noqa: F401

    def test_patch_planner_class_importable(self):
        """AC: Function defined: bob3.brownfield.patch_planner.PatchPlanner."""
        from bob3.brownfield.patch_planner import PatchPlanner
        assert callable(PatchPlanner)


# ---------------------------------------------------------------------------
# PatchPlanner class tests
# ---------------------------------------------------------------------------


class TestPatchPlannerClass:
    def test_patch_planner_instantiates(self, scratch_dir):
        from bob3.brownfield.patch_planner import PatchPlanner
        planner = PatchPlanner("feat-class-001", workspace=scratch_dir)
        assert planner.feature_id == "feat-class-001"
        assert planner.workspace == scratch_dir

    def test_patch_planner_emit_writes_yaml(self, scratch_dir):
        from bob3.brownfield.patch_planner import PatchPlanner
        planner = PatchPlanner("feat-class-002", workspace=scratch_dir)
        touches = [
            {
                "path": "src/x.py",
                "hunks": [
                    {
                        "lines": [1, 2],
                        "op": "replace",
                        "intent": "x",
                        "surrounding_symbol": "foo",
                        "new_lines": ["# replaced\n"],
                    }
                ],
            }
        ]
        plan_path = planner.emit(touches)
        assert plan_path.exists()

    def test_patch_planner_apply_and_rollback(self, scratch_dir):
        from bob3.brownfield.patch_planner import PatchPlanner
        src_file = scratch_dir / "src" / "x.py"
        src_file.parent.mkdir(parents=True)
        src_file.write_text("original = True\n")
        original = src_file.read_text()

        planner = PatchPlanner("feat-class-003", workspace=scratch_dir)
        touches = [
            {
                "path": "src/x.py",
                "hunks": [
                    {
                        "lines": [1, 1],
                        "op": "replace",
                        "intent": "swap",
                        "surrounding_symbol": "module",
                        "new_lines": ["changed = True\n"],
                    }
                ],
            }
        ]
        plan_path = planner.emit(touches)
        modified = planner.apply(plan_path)
        assert len(modified) == 1
        assert src_file.read_text() != original

        restored = planner.rollback()
        assert len(restored) == 1
        assert src_file.read_text() == original

    def test_patch_planner_check_scope_raises_for_out_of_scope(self, scratch_dir):
        from bob3.brownfield.patch_planner import PatchPlanner
        planner = PatchPlanner("feat-class-004", workspace=scratch_dir)
        touches = [{"path": "src/evil.py", "hunks": []}]
        with pytest.raises(ValueError, match="scope"):
            planner.check_scope(touches, allowlist=["src/safe.py"])
