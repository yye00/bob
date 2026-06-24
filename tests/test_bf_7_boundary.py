"""BF-7 boundary case tests — empty, zero, or minimum input returns a well-defined
result rather than raising (boundary case).

AC: pytest: tests/test_bf_7_boundary.py — empty, zero, or minimum input returns
a well-defined result rather than raising (boundary case)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.brownfield.patch_planner import (
    apply_diff_plan,
    check_scope_guard,
    emit_diff_plan,
    generate_diff_plan,
    rollback_changes,
)


# ---------------------------------------------------------------------------
# check_scope_guard boundary cases
# ---------------------------------------------------------------------------


def test_scope_guard_empty_allowlist_does_not_raise():
    """Empty allowlist = no restriction; any path is allowed."""
    touches = [{"path": "src/anything.py", "hunks": []}]
    check_scope_guard(touches, [])  # must not raise


def test_scope_guard_empty_touches_does_not_raise():
    """No touches = nothing to guard against; must not raise."""
    check_scope_guard([], ["src/foo.py"])


def test_scope_guard_single_path_in_allowlist_does_not_raise():
    """Minimum: single path, single-element allowlist, path is allowed."""
    touches = [{"path": "src/foo.py", "hunks": []}]
    check_scope_guard(touches, ["src/foo.py"])


# ---------------------------------------------------------------------------
# emit_diff_plan / generate_diff_plan boundary cases
# ---------------------------------------------------------------------------


def test_generate_diff_plan_single_touch_minimum(tmp_path: Path):
    """Minimum valid input: one touch, one hunk — returns a Path."""
    touches = [
        {
            "path": "src/foo.py",
            "hunks": [
                {
                    "lines": [1, 1],
                    "op": "replace",
                    "intent": "minimal hunk",
                    "surrounding_symbol": "foo",
                    "new_lines": ["# replaced\n"],
                }
            ],
        }
    ]
    result = generate_diff_plan("feat-min-001", touches, workspace=tmp_path)
    assert isinstance(result, Path)
    assert result.exists()


def test_emit_diff_plan_single_hunk_no_new_lines(tmp_path: Path):
    """Delete hunk with no new_lines is valid minimum for delete op."""
    touches = [
        {
            "path": "src/bar.py",
            "hunks": [
                {
                    "lines": [3, 5],
                    "op": "delete",
                    "intent": "remove dead code",
                    "surrounding_symbol": "cleanup",
                }
            ],
        }
    ]
    result = emit_diff_plan("feat-del-001", touches, workspace=tmp_path)
    assert result.exists()


def test_apply_diff_plan_no_hunks_is_noop(tmp_path: Path):
    """A touch with no hunks applies cleanly and file remains unchanged."""
    src_file = tmp_path / "src" / "noop.py"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("x = 1\n")
    original = src_file.read_text()

    touches = [{"path": "src/noop.py", "hunks": []}]
    plan_path = emit_diff_plan("feat-noop-001", touches, workspace=tmp_path)
    modified = apply_diff_plan(plan_path, workspace=tmp_path)

    assert modified == [src_file]
    assert src_file.read_text() == original


def test_rollback_after_apply_restores_single_line_file(tmp_path: Path):
    """Single-line file: apply + rollback restores exactly the original content."""
    src_file = tmp_path / "src" / "one_liner.py"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("pass\n")
    original = src_file.read_text()

    touches = [
        {
            "path": "src/one_liner.py",
            "hunks": [
                {
                    "lines": [1, 1],
                    "op": "replace",
                    "intent": "swap content",
                    "surrounding_symbol": "module",
                    "new_lines": ["x = 42\n"],
                }
            ],
        }
    ]
    plan_path = emit_diff_plan("feat-rb-001", touches, workspace=tmp_path)
    apply_diff_plan(plan_path, workspace=tmp_path)
    rollback_changes("feat-rb-001", workspace=tmp_path)

    assert src_file.read_text() == original


def test_generate_diff_plan_returns_path_not_none(tmp_path: Path):
    """generate_diff_plan always returns a non-None Path on valid input."""
    touches = [
        {
            "path": "src/x.py",
            "hunks": [
                {
                    "lines": [1, 2],
                    "op": "insert",
                    "intent": "add import",
                    "surrounding_symbol": "module",
                    "new_lines": ["import os\n"],
                }
            ],
        }
    ]
    result = generate_diff_plan("feat-nnone-001", touches, workspace=tmp_path)
    assert result is not None
    assert isinstance(result, Path)
