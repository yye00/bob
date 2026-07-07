"""Error-path tests for bob.clang_format_patch.

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.clang_format_patch import (
    ReformatScopeError,
    guard_reformat_scope,
    normalize_edit_region,
)


def test_normalize_non_str_text_raises_value_error():
    with pytest.raises(ValueError):
        normalize_edit_region(123)  # type: ignore[arg-type]


def test_normalize_none_text_raises_value_error():
    with pytest.raises(ValueError):
        normalize_edit_region(None)  # type: ignore[arg-type]


def test_normalize_missing_style_file_raises_value_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "bob.clang_format_patch.clang_format_available", lambda: True
    )
    with pytest.raises(ValueError):
        normalize_edit_region(
            "int x=1;\n", style_file=tmp_path / "nonexistent.clang-format"
        )


def test_guard_non_list_touches_raises_value_error():
    with pytest.raises(ValueError):
        guard_reformat_scope("not-a-list")  # type: ignore[arg-type]


def test_guard_touch_without_path_raises_value_error():
    with pytest.raises(ValueError):
        guard_reformat_scope([{"hunks": []}])


def test_guard_bad_hunk_lines_raises_value_error():
    touches = [{"path": "src/a.cpp", "hunks": [{"lines": [5], "op": "replace"}]}]
    with pytest.raises(ValueError):
        guard_reformat_scope(touches)


def test_guard_inverted_line_range_raises_value_error():
    touches = [{"path": "src/a.cpp", "hunks": [{"lines": [20, 10], "op": "replace"}]}]
    with pytest.raises(ValueError):
        guard_reformat_scope(touches)


def test_guard_scope_escape_raises_reformat_scope_error():
    touches = [{"path": "src/a.cpp", "hunks": [{"lines": [1, 99], "op": "replace"}]}]
    with pytest.raises(ReformatScopeError):
        guard_reformat_scope(touches, edit_site={"src/a.cpp": (5, 10)})


def test_reformat_scope_error_subclasses_value_error():
    # ReformatScopeError must be catchable as ValueError (error-path contract).
    touches = [{"path": "out.cpp", "hunks": [{"lines": [1, 2], "op": "replace"}]}]
    with pytest.raises(ValueError):
        guard_reformat_scope(touches, localization_allowlist=["src/a.cpp"])
