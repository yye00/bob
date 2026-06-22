"""BF-7 error path tests — invalid input raises ValueError and the function
does not silently succeed (error path).

AC: pytest: tests/test_bf_7_error.py — invalid input raises ValueError and the
function does not silently succeed (error path)
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
# emit_diff_plan / generate_diff_plan error paths
# ---------------------------------------------------------------------------


def test_emit_diff_plan_empty_touches_raises(tmp_path: Path):
    """Empty touches list must raise ValueError, not silently succeed."""
    with pytest.raises(ValueError, match="touches"):
        emit_diff_plan("feat-err-001", [], workspace=tmp_path)


def test_generate_diff_plan_empty_touches_raises(tmp_path: Path):
    """generate_diff_plan with empty touches must raise ValueError."""
    with pytest.raises(ValueError):
        generate_diff_plan("feat-err-002", [], workspace=tmp_path)


def test_emit_diff_plan_invalid_op_raises(tmp_path: Path):
    """An unrecognized hunk op must raise ValueError, not silently succeed."""
    touches = [
        {
            "path": "src/foo.py",
            "hunks": [
                {
                    "lines": [1, 5],
                    "op": "rewrite",  # invalid
                    "intent": "bad op",
                    "surrounding_symbol": "func",
                }
            ],
        }
    ]
    with pytest.raises(ValueError, match="op"):
        emit_diff_plan("feat-err-003", touches, workspace=tmp_path)


def test_generate_diff_plan_invalid_op_raises(tmp_path: Path):
    """generate_diff_plan propagates invalid-op ValueError."""
    touches = [
        {
            "path": "src/foo.py",
            "hunks": [
                {
                    "lines": [1, 5],
                    "op": "mutate",  # invalid
                    "intent": "bad op",
                    "surrounding_symbol": "func",
                }
            ],
        }
    ]
    with pytest.raises(ValueError):
        generate_diff_plan("feat-err-004", touches, workspace=tmp_path)


def test_emit_diff_plan_null_op_raises(tmp_path: Path):
    """A None op in a hunk must raise ValueError."""
    touches = [
        {
            "path": "src/foo.py",
            "hunks": [
                {
                    "lines": [1, 5],
                    "op": None,
                    "intent": "null op",
                    "surrounding_symbol": "func",
                }
            ],
        }
    ]
    with pytest.raises(ValueError):
        emit_diff_plan("feat-err-005", touches, workspace=tmp_path)


# ---------------------------------------------------------------------------
# apply_diff_plan error paths
# ---------------------------------------------------------------------------


def test_apply_diff_plan_missing_target_raises(tmp_path: Path):
    """apply_diff_plan must raise FileNotFoundError when touched file does not exist."""
    touches = [
        {
            "path": "src/ghost.py",  # does not exist in tmp_path
            "hunks": [
                {
                    "lines": [1, 3],
                    "op": "replace",
                    "intent": "x",
                    "surrounding_symbol": "foo",
                    "new_lines": ["# replaced\n"],
                }
            ],
        }
    ]
    plan_path = emit_diff_plan("feat-err-006", touches, workspace=tmp_path)
    with pytest.raises(FileNotFoundError):
        apply_diff_plan(plan_path, workspace=tmp_path)


# ---------------------------------------------------------------------------
# rollback_changes error paths
# ---------------------------------------------------------------------------


def test_rollback_without_prior_apply_raises(tmp_path: Path):
    """rollback_changes must raise FileNotFoundError if no orig backup exists."""
    with pytest.raises(FileNotFoundError, match="orig"):
        rollback_changes("feat-err-007", workspace=tmp_path)


# ---------------------------------------------------------------------------
# check_scope_guard error paths
# ---------------------------------------------------------------------------


def test_scope_guard_raises_for_path_outside_allowlist():
    """Touching a file outside the allowlist must raise ValueError."""
    touches = [{"path": "src/sensitive/secrets.py", "hunks": []}]
    with pytest.raises(ValueError, match="scope"):
        check_scope_guard(touches, ["src/auth/login.py"])


def test_scope_guard_raises_for_any_out_of_scope_path():
    """Even if some touches are in scope, one out-of-scope path still raises."""
    touches = [
        {"path": "src/auth/login.py", "hunks": []},   # allowed
        {"path": "src/payments/charge.py", "hunks": []},  # not allowed
    ]
    with pytest.raises(ValueError, match="scope"):
        check_scope_guard(touches, ["src/auth/login.py"])


def test_scope_guard_error_message_names_the_bad_path():
    """The ValueError message should identify the offending path."""
    bad_path = "src/evil/module.py"
    touches = [{"path": bad_path, "hunks": []}]
    with pytest.raises(ValueError, match=bad_path):
        check_scope_guard(touches, ["src/good/module.py"])
