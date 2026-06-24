"""Tests for BF-7 patch application workflow — apply_diff_plan end-to-end.

AC: pytest: tests/brownfield/test_patch_application.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bob.brownfield.patch_planner import (
    PatchPlanner,
    apply_diff_plan,
    apply_patch,
    apply_patch_plan,
    emit_diff_plan,
    rollback_changes,
    synthesize_unified_diff,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def feature_id() -> str:
    return "bf7-patch-application-test-001"


@pytest.fixture()
def src_file(tmp_path: Path) -> Path:
    """A realistic Python source file for patch targets."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    f = src_dir / "foo.py"
    f.write_text(
        "def handle_request(request: dict) -> dict:\n"         # line 1
        "    user = request.get('user')\n"                      # line 2
        "    data = request.get('data')\n"                      # line 3
        "    return {'status': 'ok', 'user': user}\n"           # line 4
        "\n"                                                     # line 5
        "def process_data(data: list) -> list:\n"               # line 6
        "    return [item for item in data if item is not None]\n"  # line 7
    )
    return f


# ---------------------------------------------------------------------------
# apply_diff_plan — replace operation
# ---------------------------------------------------------------------------


class TestApplyDiffPlanReplace:
    def test_replace_updates_target_lines(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [2, 3],
                        "op": "replace",
                        "intent": "add OAuth header extraction",
                        "surrounding_symbol": "handle_request",
                        "new_lines": [
                            "    token = request.get('token')\n",
                            "    user = request.get('user')\n",
                        ],
                    }
                ],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        content = src_file.read_text()
        assert "token = request.get('token')" in content
        assert "user = request.get('user')" in content

    def test_replace_removes_original_lines(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [6, 7],
                        "op": "replace",
                        "intent": "replace process_data body",
                        "surrounding_symbol": "process_data",
                        "new_lines": ["def process_data(data: list) -> list:\n", "    return list(data)\n"],
                    }
                ],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        assert "item is not None" not in src_file.read_text()

    def test_replace_returns_modified_paths_list(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f",
                            "new_lines": ["def handle_request(req):\n"]}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        result = apply_diff_plan(plan_path, workspace=tmp_path)
        assert isinstance(result, list)
        assert src_file in result


# ---------------------------------------------------------------------------
# apply_diff_plan — insert operation
# ---------------------------------------------------------------------------


class TestApplyDiffPlanInsert:
    def test_insert_adds_lines_at_position(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [1, 1],
                        "op": "insert",
                        "intent": "add module docstring",
                        "surrounding_symbol": "module",
                        "new_lines": ["\"\"\"Brownfield module.\"\"\"\n", "from __future__ import annotations\n"],
                    }
                ],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        content = src_file.read_text()
        assert "Brownfield module" in content
        assert "from __future__ import annotations" in content

    def test_insert_preserves_existing_lines(self, feature_id, tmp_path, src_file):
        original = src_file.read_text()
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [5, 5],
                        "op": "insert",
                        "intent": "add blank separator",
                        "surrounding_symbol": "module",
                        "new_lines": ["# --- separator ---\n"],
                    }
                ],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        content = src_file.read_text()
        # Original lines must still be present
        assert "handle_request" in content
        assert "process_data" in content
        assert "separator" in content


# ---------------------------------------------------------------------------
# apply_diff_plan — delete operation
# ---------------------------------------------------------------------------


class TestApplyDiffPlanDelete:
    def test_delete_removes_specified_lines(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [6, 7],
                        "op": "delete",
                        "intent": "remove process_data stub",
                        "surrounding_symbol": "process_data",
                    }
                ],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        assert "process_data" not in src_file.read_text()

    def test_delete_leaves_untouched_lines(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [6, 7],
                        "op": "delete",
                        "intent": "remove process_data",
                        "surrounding_symbol": "process_data",
                    }
                ],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        assert "handle_request" in src_file.read_text()


# ---------------------------------------------------------------------------
# Backup and rollback
# ---------------------------------------------------------------------------


class TestPatchBackupAndRollback:
    def test_orig_backup_created_before_modification(self, feature_id, tmp_path, src_file):
        original = src_file.read_text()
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f",
                            "new_lines": ["# changed\n"]}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        backup = tmp_path / ".bob" / "features" / feature_id / "orig" / "src" / "foo.py"
        assert backup.exists()
        assert backup.read_text() == original

    def test_rollback_restores_original(self, feature_id, tmp_path, src_file):
        original = src_file.read_text()
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f",
                            "new_lines": ["# changed\n"]}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        assert src_file.read_text() != original
        rollback_changes(feature_id, workspace=tmp_path)
        assert src_file.read_text() == original

    def test_rollback_clears_backup_files(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f",
                            "new_lines": ["# changed\n"]}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        apply_diff_plan(plan_path, workspace=tmp_path)
        rollback_changes(feature_id, workspace=tmp_path)
        orig_dir = tmp_path / ".bob" / "features" / feature_id / "orig"
        remaining = [p for p in orig_dir.rglob("*") if p.is_file()]
        assert remaining == []


# ---------------------------------------------------------------------------
# apply_patch and apply_patch_plan aliases
# ---------------------------------------------------------------------------


class TestApplyAliases:
    def test_apply_patch_alias(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f",
                            "new_lines": ["# via apply_patch\n"]}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        result = apply_patch(plan_path, workspace=tmp_path)
        assert isinstance(result, list)
        assert "apply_patch" in src_file.read_text()

    def test_apply_patch_plan_alias(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "y", "surrounding_symbol": "f",
                            "new_lines": ["# via apply_patch_plan\n"]}],
            }
        ]
        plan_path = emit_diff_plan(f"{feature_id}-b", touches, workspace=tmp_path)
        result = apply_patch_plan(plan_path, workspace=tmp_path)
        assert isinstance(result, list)
        assert "apply_patch_plan" in src_file.read_text()


# ---------------------------------------------------------------------------
# synthesize_unified_diff
# ---------------------------------------------------------------------------


class TestSynthesizeUnifiedDiff:
    def test_diff_contains_fromfile_tofile_markers(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f",
                            "new_lines": ["# replaced\n"]}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        diff = synthesize_unified_diff(plan_path, workspace=tmp_path)
        assert "--- a/src/foo.py" in diff
        assert "+++ b/src/foo.py" in diff

    def test_diff_shows_added_lines(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f",
                            "new_lines": ["# ADDED_MARKER\n"]}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        diff = synthesize_unified_diff(plan_path, workspace=tmp_path)
        assert "+# ADDED_MARKER" in diff

    def test_diff_shows_removed_lines(self, feature_id, tmp_path, src_file):
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "f",
                            "new_lines": ["# new first line\n"]}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        diff = synthesize_unified_diff(plan_path, workspace=tmp_path)
        assert "-def handle_request" in diff

    def test_diff_missing_plan_raises(self, tmp_path: Path):
        bogus = tmp_path / "no_such_plan.yaml"
        with pytest.raises(ValueError, match="diff_plan not found"):
            synthesize_unified_diff(bogus, workspace=tmp_path)

    def test_diff_no_change_returns_empty(self, feature_id, tmp_path, src_file):
        """When replace uses the same lines, unified_diff may produce no output."""
        first_line = src_file.read_text().splitlines(keepends=True)[0]
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "noop", "surrounding_symbol": "f",
                            "new_lines": [first_line]}],
            }
        ]
        plan_path = emit_diff_plan(feature_id, touches, workspace=tmp_path)
        diff = synthesize_unified_diff(plan_path, workspace=tmp_path)
        # No change means empty diff string
        assert diff == ""


# ---------------------------------------------------------------------------
# PatchPlanner integration — full apply workflow
# ---------------------------------------------------------------------------


class TestPatchPlannerApplyWorkflow:
    def test_full_workflow_via_patchplanner(self, tmp_path: Path):
        src = tmp_path / "src" / "module.py"
        src.parent.mkdir(parents=True)
        src.write_text("x = 1\ny = 2\n")
        original = src.read_text()

        planner = PatchPlanner("bf7-wf-001", workspace=tmp_path)
        touches = [
            {
                "path": "src/module.py",
                "hunks": [{"lines": [1, 1], "op": "replace", "intent": "swap x", "surrounding_symbol": "module",
                            "new_lines": ["x = 99\n"]}],
            }
        ]
        plan_path = planner.emit(touches)
        modified = planner.apply(plan_path)
        assert src in modified
        assert "x = 99" in src.read_text()

        planner.rollback()
        assert src.read_text() == original

    def test_multi_file_patch(self, tmp_path: Path):
        a = tmp_path / "src" / "a.py"
        b = tmp_path / "src" / "b.py"
        a.parent.mkdir(parents=True)
        a.write_text("a = 1\n")
        b.write_text("b = 2\n")

        touches = [
            {"path": "src/a.py",
             "hunks": [{"lines": [1, 1], "op": "replace", "intent": "x", "surrounding_symbol": "m",
                        "new_lines": ["a = 10\n"]}]},
            {"path": "src/b.py",
             "hunks": [{"lines": [1, 1], "op": "replace", "intent": "y", "surrounding_symbol": "m",
                        "new_lines": ["b = 20\n"]}]},
        ]
        plan_path = emit_diff_plan("bf7-multi-001", touches, workspace=tmp_path)
        modified = apply_diff_plan(plan_path, workspace=tmp_path)
        assert len(modified) == 2
        assert "a = 10" in a.read_text()
        assert "b = 20" in b.read_text()
