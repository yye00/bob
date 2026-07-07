"""Tests for bob.clang_ast_resolution (feature 43fbc3fb).

clang-AST resolution for ``Function defined:`` / ``Class defined:`` ACs on C++
projects, replacing the gameable ``re.search(f"{name}\\(", ...)`` heuristic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bob.clang_ast_resolution import (
    CLANG_TOOLING_UNAVAILABLE,
    ClangProbeResult,
    probe_class_definition,
    probe_function_definition,
    search_for_class_clang,
    search_for_function_clang,
)


def _cmake_ws(tmp_path: Path) -> Path:
    """A workspace with a compile_commands.json so tooling looks 'present'."""
    (tmp_path / "compile_commands.json").write_text(
        json.dumps([{"directory": str(tmp_path), "file": "a.cpp",
                     "command": "clang++ -c a.cpp"}])
    )
    (tmp_path / "a.cpp").write_text("int foo() { return 1; }\n")
    return tmp_path


def test_function_defined_returns_true_via_clang(tmp_path, monkeypatch):
    ws = _cmake_ws(tmp_path)
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )
    calls = {}

    def fake_runner(exe, build_dir, matcher):
        calls["matcher"] = matcher
        return 1  # one definition match

    assert search_for_function_clang(ws, "foo", run_query=fake_runner) is True
    # The matcher must require a DEFINITION with a non-empty body, not a substring.
    assert "isDefinition()" in calls["matcher"]
    assert "unless(statementCountIs(0))" in calls["matcher"]
    assert 'hasName("foo")' in calls["matcher"]


def test_function_zero_matches_returns_false(tmp_path, monkeypatch):
    ws = _cmake_ws(tmp_path)
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )
    # A call site / forward decl produces 0 definition matches -> False.
    assert search_for_function_clang(ws, "foo", run_query=lambda *a: 0) is False


def test_namespaced_function_name_passed_to_matcher(tmp_path, monkeypatch):
    ws = _cmake_ws(tmp_path)
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )
    seen = {}

    def runner(exe, build_dir, matcher):
        seen["m"] = matcher
        return 1

    assert search_for_function_clang(ws, "ns::foo", run_query=runner) is True
    assert 'hasName("ns::foo")' in seen["m"]


def test_class_defined_returns_true(tmp_path, monkeypatch):
    ws = _cmake_ws(tmp_path)
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )
    seen = {}

    def runner(exe, build_dir, matcher):
        seen["m"] = matcher
        return 1

    assert search_for_class_clang(ws, "Widget", run_query=runner) is True
    assert "cxxRecordDecl" in seen["m"]
    assert "isDefinition()" in seen["m"]


def test_class_forward_decl_only_returns_false(tmp_path, monkeypatch):
    ws = _cmake_ws(tmp_path)
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )
    assert search_for_class_clang(ws, "Widget", run_query=lambda *a: 0) is False


def test_clang_query_missing_is_pass_with_warning(tmp_path, monkeypatch):
    ws = _cmake_ws(tmp_path)
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: None
    )
    # Must NOT degrade to regex; PASS-with-warning instead.
    result = probe_function_definition(ws, "foo")
    assert result.available is False
    assert result.passed is True
    assert result.matched is False
    assert CLANG_TOOLING_UNAVAILABLE in result.reason
    assert search_for_function_clang(ws, "foo") is True


def test_no_compile_commands_is_pass_with_warning(tmp_path, monkeypatch):
    # clang-query present but no compile DB -> unavailable -> PASS-with-warning.
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )
    result = probe_class_definition(tmp_path, "Widget")
    assert result.available is False
    assert result.passed is True
    assert CLANG_TOOLING_UNAVAILABLE in result.reason


def test_clang_query_crash_is_pass_with_warning(tmp_path, monkeypatch):
    ws = _cmake_ws(tmp_path)
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )

    def boom(*a):
        raise RuntimeError("clang-query segfault")

    result = probe_function_definition(ws, "foo", run_query=boom)
    assert result.available is False
    assert result.passed is True
    assert CLANG_TOOLING_UNAVAILABLE in result.reason


def test_probe_result_shape():
    r = ClangProbeResult(available=True, passed=True, matched=True, reason="")
    assert r.available and r.passed and r.matched
    assert r.reason == ""


def test_parse_match_count():
    from bob.clang_ast_resolution import _parse_match_count

    assert _parse_match_count("Match #1:\n1 match.\n") == 1
    assert _parse_match_count("Match #1:\nMatch #2:\n2 matches.\n") == 2
    assert _parse_match_count("0 matches.\n") == 0
    assert _parse_match_count("garbage output") == 0


def test_compile_commands_in_build_dir_is_found(tmp_path, monkeypatch):
    build = tmp_path / "build"
    build.mkdir()
    (build / "compile_commands.json").write_text("[]")
    monkeypatch.setattr(
        "bob.clang_ast_resolution._find_clang_query", lambda: "/usr/bin/clang-query"
    )
    seen = {}

    def runner(exe, build_dir, matcher):
        seen["dir"] = Path(build_dir)
        return 1

    assert search_for_function_clang(tmp_path, "foo", run_query=runner) is True
    assert seen["dir"] == build
