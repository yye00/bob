"""BF-4 boundary-case tests: empty, zero, or minimum input returns well-defined result.

These tests verify that bob3.brownfield.localizer.localize (and the BF-4
entry-point) never raises when given empty/minimum input — they always
return a dict with the three required keys.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from bob3.brownfield.localizer import (
    check_disjoint,
    extract_edit_sites,
    localize,
    rank_symbols_by_intent,
)
from bob3.bf_4_hierarchical_localizer_file_class_symbol_edit_site import (
    bf_4_hierarchical_localizer_file_class_symbol_edit_site,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_result_shape(result: dict[str, Any]) -> None:
    """Assert result has the required top-level keys and is a dict."""
    assert isinstance(result, dict)
    assert "files" in result
    assert "symbols" in result
    assert "edit_sites" in result


def _make_survey_db(symbols: list[dict[str, Any]]) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.execute(
        "CREATE TABLE symbols "
        "(id INTEGER PRIMARY KEY, path TEXT, kind TEXT, name TEXT, "
        "sha TEXT DEFAULT 'x', lineno INTEGER, end_lineno INTEGER, "
        "pagerank REAL DEFAULT 0.0, docstring TEXT DEFAULT '')"
    )
    for s in symbols:
        conn.execute(
            "INSERT INTO symbols (path, kind, name, lineno, end_lineno, pagerank, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                s["path"], s.get("kind", "function"), s["name"],
                s.get("lineno", 1), s.get("end_lineno", 10),
                s.get("pagerank", 0.5), s.get("docstring", ""),
            ),
        )
    conn.commit()
    conn.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# Boundary: localize() with no survey_db
# ---------------------------------------------------------------------------

def test_localize_no_db_returns_empty_lists() -> None:
    """localize() with no survey_db returns empty lists, not an exception."""
    result = localize({})
    _empty_result_shape(result)
    assert result["files"] == []
    assert result["symbols"] == []
    assert result["edit_sites"] == []


def test_localize_none_db_path_returns_empty() -> None:
    """localize() with survey_db=None returns empty, no crash."""
    result = localize({"capability": "add auth"}, survey_db=None)
    _empty_result_shape(result)
    assert result["files"] == []


def test_localize_nonexistent_db_path_returns_empty(tmp_path: Path) -> None:
    """localize() with a path that doesn't exist returns empty."""
    result = localize({"capability": "test"}, survey_db=tmp_path / "missing.db")
    _empty_result_shape(result)
    assert result["files"] == []


# ---------------------------------------------------------------------------
# Boundary: empty intent
# ---------------------------------------------------------------------------

def test_localize_empty_intent_dict_no_crash(tmp_path: Path) -> None:
    """localize({}) with a real (empty) DB returns empty lists — no crash."""
    db = _make_survey_db([])
    try:
        result = localize({}, survey_db=db)
        _empty_result_shape(result)
    finally:
        db.unlink(missing_ok=True)


def test_localize_intent_all_empty_strings(tmp_path: Path) -> None:
    """Intent with all-empty strings is a valid no-query intent — no crash."""
    db = _make_survey_db([
        {"path": "src/a.py", "name": "do_thing", "kind": "function", "lineno": 1}
    ])
    try:
        result = localize(
            {"capability": "", "target_subsystem": "", "keywords": []},
            survey_db=db,
        )
        _empty_result_shape(result)
    finally:
        db.unlink(missing_ok=True)


def test_localize_only_capability_no_keywords() -> None:
    """Intent with capability but no keywords returns well-defined result."""
    result = localize({"capability": "authenticate user"})
    _empty_result_shape(result)


def test_localize_only_keywords_no_capability() -> None:
    """Intent with only keywords list returns well-defined result."""
    result = localize({"keywords": ["auth", "login"]})
    _empty_result_shape(result)


# ---------------------------------------------------------------------------
# Boundary: top_k = 0
# ---------------------------------------------------------------------------

def test_localize_top_k_files_zero(tmp_path: Path) -> None:
    """top_k_files=0 returns empty files list, no crash."""
    db = _make_survey_db([
        {"path": "src/a.py", "name": "func", "kind": "function", "lineno": 1}
    ])
    try:
        result = localize({"capability": "test"}, survey_db=db, top_k_files=0)
        _empty_result_shape(result)
        assert result["files"] == []
    finally:
        db.unlink(missing_ok=True)


def test_localize_top_k_symbols_zero(tmp_path: Path) -> None:
    """top_k_symbols=0 returns empty symbols and edit_sites, no crash."""
    db = _make_survey_db([
        {"path": "src/a.py", "name": "func", "kind": "function", "lineno": 1}
    ])
    try:
        result = localize({"capability": "test"}, survey_db=db, top_k_symbols=0)
        _empty_result_shape(result)
        assert result["symbols"] == []
        assert result["edit_sites"] == []
    finally:
        db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Boundary: single-symbol DB
# ---------------------------------------------------------------------------

def test_localize_single_symbol_db() -> None:
    """With exactly one symbol, localize returns exactly one edit_site."""
    db = _make_survey_db([
        {
            "path": "src/main.py",
            "name": "main",
            "kind": "function",
            "lineno": 1,
            "end_lineno": 10,
            "pagerank": 1.0,
            "docstring": "entry point",
        }
    ])
    try:
        result = localize({"capability": "main entry point"}, survey_db=db)
        _empty_result_shape(result)
        assert len(result["files"]) == 1
        assert len(result["symbols"]) == 1
        assert len(result["edit_sites"]) == 1
    finally:
        db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Boundary: rank_symbols_by_intent with empty inputs
# ---------------------------------------------------------------------------

def test_rank_symbols_empty_list_returns_empty() -> None:
    """rank_symbols_by_intent([]) returns empty list, no crash."""
    result = rank_symbols_by_intent([], {"capability": "auth"})
    assert result == []


def test_rank_symbols_empty_intent_no_crash() -> None:
    """rank_symbols_by_intent with empty intent returns list without crash."""
    syms = [
        {"id": 1, "path": "a.py", "kind": "function", "name": "foo",
         "lineno": 1, "end_lineno": 10, "pagerank": 0.5, "docstring": "foo"},
    ]
    result = rank_symbols_by_intent(syms, {})
    assert isinstance(result, list)


def test_rank_symbols_top_k_zero_returns_empty() -> None:
    """top_k=0 returns empty list."""
    syms = [
        {"id": 1, "path": "a.py", "kind": "function", "name": "foo",
         "lineno": 1, "end_lineno": 10, "pagerank": 0.5, "docstring": ""},
    ]
    result = rank_symbols_by_intent(syms, {"capability": "foo"}, top_k=0)
    assert result == []


# ---------------------------------------------------------------------------
# Boundary: extract_edit_sites with empty/minimum input
# ---------------------------------------------------------------------------

def test_extract_edit_sites_empty_list_returns_empty() -> None:
    """extract_edit_sites([]) returns empty list."""
    assert extract_edit_sites([]) == []


def test_extract_edit_sites_symbol_without_end_lineno() -> None:
    """Symbols missing end_lineno get a fallback end_line >= start_line."""
    syms = [
        {"path": "a.py", "kind": "function", "name": "foo",
         "lineno": 5, "end_lineno": None, "pagerank": 0.5, "score": 0.5},
    ]
    sites = extract_edit_sites(syms)
    assert len(sites) == 1
    assert sites[0]["start_line"] <= sites[0]["end_line"]


# ---------------------------------------------------------------------------
# Boundary: check_disjoint with empty edit_sites
# ---------------------------------------------------------------------------

def test_check_disjoint_both_empty() -> None:
    """Two empty localizations are not disjoint (return False = no conflict)."""
    assert check_disjoint({"edit_sites": []}, {"edit_sites": []}) is False


def test_check_disjoint_one_empty() -> None:
    """One empty localization is always disjoint with any other."""
    loc_with_site = {
        "edit_sites": [{"path": "src/a.py", "start_line": 1, "end_line": 10, "scope": "function"}]
    }
    assert check_disjoint({"edit_sites": []}, loc_with_site) is False
    assert check_disjoint(loc_with_site, {"edit_sites": []}) is False


# ---------------------------------------------------------------------------
# Boundary: entry-point function with None / empty intent
# ---------------------------------------------------------------------------

def test_entry_point_none_intent_returns_empty() -> None:
    """bf_4_... with intent=None returns empty dict, no crash."""
    result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=None)
    _empty_result_shape(result)
    assert result["files"] == []
    assert result["symbols"] == []
    assert result["edit_sites"] == []


def test_entry_point_empty_dict_intent_no_db_returns_empty() -> None:
    """bf_4_... with intent={} and no db returns empty dict."""
    result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent={})
    _empty_result_shape(result)


def test_entry_point_top_k_zero_no_crash() -> None:
    """bf_4_... with top_k_files=0 and top_k_symbols=0 returns empty, no crash."""
    result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(
        intent={}, top_k_files=0, top_k_symbols=0
    )
    _empty_result_shape(result)
