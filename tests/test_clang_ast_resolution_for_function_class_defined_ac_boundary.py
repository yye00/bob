"""Boundary tests for bob.clang_ast_resolution (feature 43fbc3fb).

Empty / minimal workspaces and the tooling-unavailable path must return a
well-defined result rather than raising.
"""
from __future__ import annotations

import pytest

from bob.clang_ast_resolution import (
    probe_class_definition,
    probe_function_definition,
    search_for_class_clang,
    search_for_function_clang,
)


def test_empty_workspace_no_tooling_is_pass_with_warning(tmp_path):
    """An empty workspace (no compile_commands.json) returns PASS-with-warning."""
    result = probe_function_definition(tmp_path, "foo")
    assert result.passed is True
    assert result.available is False


def test_search_function_empty_workspace_returns_bool(tmp_path):
    assert search_for_function_clang(tmp_path, "foo") is True


def test_search_class_empty_workspace_returns_bool(tmp_path):
    assert search_for_class_clang(tmp_path, "Widget") is True


def test_minimal_single_char_name(tmp_path, monkeypatch):
    """A single-character name is still a well-defined query, not an error."""
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )
    (tmp_path / "compile_commands.json").write_text("[]")
    assert search_for_function_clang(tmp_path, "f", run_query=lambda *a: 0) is False


def test_name_with_surrounding_whitespace_is_stripped(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )
    (tmp_path / "compile_commands.json").write_text("[]")
    seen = {}

    def runner(exe, build_dir, matcher):
        seen["m"] = matcher
        return 1

    assert search_for_function_clang(tmp_path, "  foo  ", run_query=runner) is True
    assert 'hasName("foo")' in seen["m"]


def test_workspace_as_string_path(tmp_path):
    """workspace accepted as a str, not only a Path."""
    result = probe_class_definition(str(tmp_path), "Widget")
    assert result.passed is True


def test_zero_matches_is_defined_false(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )
    (tmp_path / "compile_commands.json").write_text("[]")
    result = probe_class_definition(tmp_path, "Nope", run_query=lambda *a: 0)
    assert result.available is True
    assert result.passed is False
    assert result.matched is False
