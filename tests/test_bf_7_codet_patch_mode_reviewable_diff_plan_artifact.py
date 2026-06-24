"""Tests for bf_7_codet_patch_mode_reviewable_diff_plan_artifact.

AC verification:
  - File exists: src/bob/bf_7_codet_patch_mode_reviewable_diff_plan_artifact.py
  - Function defined: bob.bf_7_codet_patch_mode_reviewable_diff_plan_artifact
                        .bf_7_codet_patch_mode_reviewable_diff_plan_artifact
  - behavior: BF-7 handles boundary case of empty / zero input without crashing
  - behavior: BF-7 raises ValueError or returns rejection for invalid input
  - File exists: src/bob/brownfield/patch_planner.py
  - File exists: src/foo.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_MODULE = "bob.bf_7_codet_patch_mode_reviewable_diff_plan_artifact"
_FUNC = "bf_7_codet_patch_mode_reviewable_diff_plan_artifact"

SAMPLE_TOUCHES = [
    {
        "path": "src/foo.py",
        "hunks": [
            {
                "lines": [10, 12],
                "op": "replace",
                "intent": "add OAuth check at request entry",
                "surrounding_symbol": "handle_request",
                "new_lines": ["    # OAuth check added\n", "    pass\n"],
            }
        ],
    }
]


# ---------------------------------------------------------------------------
# Primary AC test — must be named exactly as the acceptance criteria requires
# ---------------------------------------------------------------------------


def test_bf_7_codet_patch_mode_reviewable_diff_plan_artifact():
    """AC: function is importable, callable, and returns a structured dict."""
    from bob.bf_7_codet_patch_mode_reviewable_diff_plan_artifact import (
        bf_7_codet_patch_mode_reviewable_diff_plan_artifact,
    )

    result = bf_7_codet_patch_mode_reviewable_diff_plan_artifact()

    assert isinstance(result, dict)
    assert result["supports_rollback"] is True
    assert result["requires_diff_plan"] is True
    assert isinstance(result["protocol_steps"], list)
    assert len(result["protocol_steps"]) >= 3
    assert isinstance(result["module_path"], str)
    assert "patch_planner" in result["module_path"]


# ---------------------------------------------------------------------------
# Structural file-existence tests
# ---------------------------------------------------------------------------


class TestFileExistence:
    def test_source_file_exists(self):
        src = (
            Path(__file__).parent.parent
            / "src"
            / "bob"
            / "bf_7_codet_patch_mode_reviewable_diff_plan_artifact.py"
        )
        assert src.exists(), f"Source file missing: {src}"

    def test_patch_planner_exists(self):
        src = (
            Path(__file__).parent.parent
            / "src"
            / "bob"
            / "brownfield"
            / "patch_planner.py"
        )
        assert src.exists(), f"patch_planner.py missing: {src}"

    def test_foo_py_exists(self):
        src = Path(__file__).parent.parent / "src" / "foo.py"
        assert src.exists(), f"src/foo.py missing: {src}"

    def test_function_importable(self):
        from bob.bf_7_codet_patch_mode_reviewable_diff_plan_artifact import (
            bf_7_codet_patch_mode_reviewable_diff_plan_artifact,
        )

        assert callable(bf_7_codet_patch_mode_reviewable_diff_plan_artifact)


# ---------------------------------------------------------------------------
# Boundary and validation behavior tests
# ---------------------------------------------------------------------------


class TestBoundaryBehavior:
    """BF-7 boundary cases — empty/zero input and invalid input."""

    def test_empty_touches_raises_value_error(self):
        """behavior: empty touches must raise ValueError, not crash silently."""
        from bob.brownfield.patch_planner import emit_diff_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="empty"):
                emit_diff_plan(
                    "feat-empty-001",
                    touches=[],
                    workspace=Path(tmpdir),
                )

    def test_invalid_op_raises_value_error(self):
        """behavior: invalid hunk op must raise ValueError."""
        from bob.brownfield.patch_planner import emit_diff_plan

        bad_touches = [
            {
                "path": "src/foo.py",
                "hunks": [{"lines": [1, 2], "op": "frobnicate", "intent": "bad op"}],
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="frobnicate"):
                emit_diff_plan("feat-badop-001", touches=bad_touches, workspace=Path(tmpdir))

    def test_no_args_returns_dict_without_crash(self):
        """behavior: calling with no args returns well-defined dict."""
        from bob.bf_7_codet_patch_mode_reviewable_diff_plan_artifact import (
            bf_7_codet_patch_mode_reviewable_diff_plan_artifact,
        )

        result = bf_7_codet_patch_mode_reviewable_diff_plan_artifact()
        assert isinstance(result, dict)
        assert result["plan_path"] == ""
        assert result["scope_guard_active"] is False

    def test_scope_guard_rejects_out_of_scope_paths(self):
        """behavior: scope guard raises ValueError for paths outside allowlist."""
        from bob.bf_7_codet_patch_mode_reviewable_diff_plan_artifact import (
            bf_7_codet_patch_mode_reviewable_diff_plan_artifact,
        )

        with pytest.raises(ValueError, match="scope guard"):
            bf_7_codet_patch_mode_reviewable_diff_plan_artifact(
                touches=[{"path": "src/evil.py", "hunks": []}],
                localization_allowlist=["src/foo.py"],
            )

    def test_scope_guard_passes_for_allowed_path(self):
        """behavior: scope guard allows touches within the allowlist."""
        from bob.bf_7_codet_patch_mode_reviewable_diff_plan_artifact import (
            bf_7_codet_patch_mode_reviewable_diff_plan_artifact,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = bf_7_codet_patch_mode_reviewable_diff_plan_artifact(
                feature_id="feat-scope-ok",
                touches=SAMPLE_TOUCHES,
                localization_allowlist=["src/foo.py"],
                workspace=Path(tmpdir),
            )
        assert result["scope_guard_active"] is True
        assert result["plan_path"] != ""


# ---------------------------------------------------------------------------
# Patch planner integration tests
# ---------------------------------------------------------------------------


class TestPatchPlannerIntegration:
    """Integration tests for emit_diff_plan / apply_diff_plan / rollback_changes."""

    def _make_workspace(self, tmp_path: Path) -> Path:
        target = tmp_path / "src" / "foo.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("line1\nline2\nline3\nline4\nline5\n")
        return tmp_path

    def test_emit_diff_plan_creates_yaml(self, tmp_path):
        from bob.brownfield.patch_planner import emit_diff_plan

        ws = self._make_workspace(tmp_path)
        plan_path = emit_diff_plan(
            "feat-emit-001",
            touches=SAMPLE_TOUCHES,
            workspace=ws,
        )
        assert plan_path.exists()
        import yaml

        data = yaml.safe_load(plan_path.read_text())
        assert data["feature_id"] == "feat-emit-001"
        assert len(data["touches"]) == 1
        assert data["touches"][0]["path"] == "src/foo.py"

    def test_apply_diff_plan_replace(self, tmp_path):
        from bob.brownfield.patch_planner import apply_diff_plan, emit_diff_plan

        ws = self._make_workspace(tmp_path)

        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [2, 3],
                        "op": "replace",
                        "intent": "replace line2 with REPLACED",
                        "surrounding_symbol": "foo",
                        "new_lines": ["REPLACED\n"],
                    }
                ],
            }
        ]

        plan_path = emit_diff_plan("feat-apply-001", touches=touches, workspace=ws)
        modified = apply_diff_plan(plan_path, workspace=ws)
        assert len(modified) == 1
        content = (ws / "src" / "foo.py").read_text()
        assert "REPLACED" in content
        assert "line2" not in content

    def test_apply_diff_plan_creates_backup(self, tmp_path):
        from bob.brownfield.patch_planner import apply_diff_plan, emit_diff_plan

        ws = self._make_workspace(tmp_path)
        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [1, 2],
                        "op": "delete",
                        "intent": "remove line1",
                        "surrounding_symbol": "foo",
                    }
                ],
            }
        ]

        plan_path = emit_diff_plan("feat-backup-001", touches=touches, workspace=ws)
        apply_diff_plan(plan_path, workspace=ws)

        orig = ws / ".bob" / "features" / "feat-backup-001" / "orig" / "src" / "foo.py"
        assert orig.exists()
        assert "line1" in orig.read_text()

    def test_rollback_restores_original(self, tmp_path):
        from bob.brownfield.patch_planner import (
            apply_diff_plan,
            emit_diff_plan,
            rollback_changes,
        )

        ws = self._make_workspace(tmp_path)
        original_content = (ws / "src" / "foo.py").read_text()

        touches = [
            {
                "path": "src/foo.py",
                "hunks": [
                    {
                        "lines": [1, 2],
                        "op": "replace",
                        "intent": "test rollback",
                        "surrounding_symbol": "foo",
                        "new_lines": ["MODIFIED\n"],
                    }
                ],
            }
        ]

        plan_path = emit_diff_plan("feat-rollback-001", touches=touches, workspace=ws)
        apply_diff_plan(plan_path, workspace=ws)

        modified_content = (ws / "src" / "foo.py").read_text()
        assert modified_content != original_content

        rollback_changes("feat-rollback-001", workspace=ws)
        restored_content = (ws / "src" / "foo.py").read_text()
        assert restored_content == original_content

    def test_apply_diff_plan_missing_target_raises(self, tmp_path):
        from bob.brownfield.patch_planner import apply_diff_plan, emit_diff_plan

        ws = tmp_path
        touches = [
            {
                "path": "src/nonexistent.py",
                "hunks": [{"lines": [1, 2], "op": "replace", "new_lines": ["x\n"]}],
            }
        ]
        plan_path = emit_diff_plan("feat-missing-001", touches=touches, workspace=ws)

        with pytest.raises(FileNotFoundError):
            apply_diff_plan(plan_path, workspace=ws)

    def test_rollback_no_backup_raises(self, tmp_path):
        from bob.brownfield.patch_planner import rollback_changes

        with pytest.raises(FileNotFoundError):
            rollback_changes("feat-no-backup", workspace=tmp_path)

    def test_check_scope_guard_empty_allowlist_allows_all(self):
        from bob.brownfield.patch_planner import check_scope_guard

        touches = [{"path": "src/anything.py", "hunks": []}]
        check_scope_guard(touches, localization_allowlist=[])

    def test_check_scope_guard_disallows_out_of_scope(self):
        from bob.brownfield.patch_planner import check_scope_guard

        touches = [{"path": "src/secret.py", "hunks": []}]
        with pytest.raises(ValueError, match="scope guard"):
            check_scope_guard(touches, localization_allowlist=["src/foo.py"])
