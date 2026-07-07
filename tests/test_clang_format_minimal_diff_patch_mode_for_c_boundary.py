"""Boundary tests for bob.clang_format_patch.

Empty / zero / minimum inputs return a well-defined result rather than raising.
"""

from __future__ import annotations

from bob.clang_format_patch import guard_reformat_scope, normalize_edit_region


def test_normalize_empty_string_returns_empty_string():
    # Boundary: empty region → empty result, no formatter invoked, no raise.
    assert normalize_edit_region("") == ""


def test_normalize_whitespace_only_returns_str(monkeypatch):
    monkeypatch.setattr(
        "bob.clang_format_patch.clang_format_available", lambda: False
    )
    result = normalize_edit_region("   \n")
    assert isinstance(result, str)


def test_guard_empty_touches_returns_true():
    # Boundary: nothing to edit → trivially in scope.
    assert guard_reformat_scope([]) is True


def test_guard_touch_with_no_hunks_returns_true():
    # Boundary: a touch with zero hunks has nothing to guard.
    touches = [{"path": "src/a.cpp", "hunks": []}]
    assert guard_reformat_scope(touches) is True


def test_guard_minimum_single_line_hunk_in_scope():
    touches = [{"path": "src/a.cpp", "hunks": [{"lines": [1, 1], "op": "replace"}]}]
    assert guard_reformat_scope(
        touches, edit_site={"src/a.cpp": (1, 1)}
    ) is True


def test_guard_no_edit_site_no_allowlist_is_permissive():
    touches = [{"path": "src/a.cpp", "hunks": [{"lines": [3, 9], "op": "replace"}]}]
    assert guard_reformat_scope(touches) is True
