"""Tests for bob.clang_format_patch — clang-format minimal-diff patch mode."""

from __future__ import annotations

import pytest

from bob.clang_format_patch import (
    ReformatScopeError,
    clang_format_available,
    guard_reformat_scope,
    normalize_edit_region,
)


# ---------------------------------------------------------------------------
# normalize_edit_region
# ---------------------------------------------------------------------------


def test_normalize_empty_region_returns_empty():
    assert normalize_edit_region("") == ""


def test_normalize_returns_str():
    out = normalize_edit_region("int  x = 1 ;\n")
    assert isinstance(out, str)


def test_normalize_without_clang_format_returns_unchanged(monkeypatch):
    monkeypatch.setattr(
        "bob.clang_format_patch.clang_format_available", lambda: False
    )
    text = "int  x=1;\n"
    assert normalize_edit_region(text) == text


def test_normalize_invokes_clang_format_when_available(monkeypatch):
    calls = {}

    monkeypatch.setattr(
        "bob.clang_format_patch.clang_format_available", lambda: True
    )

    class _Result:
        stdout = "int x = 1;\n"

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["input"] = kwargs.get("input")
        return _Result()

    monkeypatch.setattr("bob.clang_format_patch.subprocess.run", fake_run)
    out = normalize_edit_region("int  x=1;\n")
    assert out == "int x = 1;\n"
    assert calls["cmd"][0] == "clang-format"
    assert calls["input"] == "int  x=1;\n"


def test_normalize_uses_repo_style_file(monkeypatch, tmp_path):
    (tmp_path / ".clang-format").write_text("BasedOnStyle: LLVM\n")
    monkeypatch.setattr(
        "bob.clang_format_patch.clang_format_available", lambda: True
    )
    captured = {}

    class _Result:
        stdout = "formatted\n"

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr("bob.clang_format_patch.subprocess.run", fake_run)
    normalize_edit_region("int x=1;\n", workspace=tmp_path)
    assert "-style=file" in captured["cmd"]


def test_normalize_formatter_failure_falls_back_to_raw(monkeypatch):
    import subprocess as _sp

    monkeypatch.setattr(
        "bob.clang_format_patch.clang_format_available", lambda: True
    )

    def fake_run(cmd, **kwargs):
        raise _sp.CalledProcessError(1, cmd)

    monkeypatch.setattr("bob.clang_format_patch.subprocess.run", fake_run)
    text = "int x=1;\n"
    assert normalize_edit_region(text) == text


# ---------------------------------------------------------------------------
# guard_reformat_scope
# ---------------------------------------------------------------------------


def test_guard_empty_touches_returns_true():
    assert guard_reformat_scope([]) is True


def test_guard_in_scope_passes():
    touches = [{"path": "src/a.cpp", "hunks": [{"lines": [10, 20], "op": "replace"}]}]
    assert guard_reformat_scope(
        touches,
        edit_site={"src/a.cpp": (5, 25)},
        localization_allowlist=["src/a.cpp"],
    ) is True


def test_guard_hunk_escaping_edit_site_rejected():
    touches = [{"path": "src/a.cpp", "hunks": [{"lines": [1, 40], "op": "replace"}]}]
    with pytest.raises(ReformatScopeError):
        guard_reformat_scope(touches, edit_site={"src/a.cpp": (5, 25)})


def test_guard_path_outside_allowlist_rejected():
    touches = [{"path": "src/evil.cpp", "hunks": [{"lines": [1, 2], "op": "replace"}]}]
    with pytest.raises(ReformatScopeError):
        guard_reformat_scope(touches, localization_allowlist=["src/a.cpp"])


def test_guard_no_allowlist_no_edit_site_passes():
    touches = [{"path": "any.cpp", "hunks": [{"lines": [1, 100], "op": "replace"}]}]
    assert guard_reformat_scope(touches) is True


def test_reformat_scope_error_is_value_error():
    assert issubclass(ReformatScopeError, ValueError)


# ---------------------------------------------------------------------------
# integration: bob.patch_planner
# ---------------------------------------------------------------------------


def test_patch_planner_facade_importable():
    import bob.patch_planner as pp

    assert hasattr(pp, "emit_diff_plan")
    assert hasattr(pp, "check_scope_guard")


def test_clang_format_available_returns_bool():
    assert isinstance(clang_format_available(), bool)
