"""Tests for bob3.brownfield.localizer — BF-4 Hierarchical Localizer.

Covers the main public API:
  - hierarchical_localize
  - rank_files_by_intent
  - rank_symbols_by_intent
  - extract_edit_sites
  - check_disjoint
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from bob3.brownfield.localizer import (
    check_disjoint,
    extract_edit_sites,
    hierarchical_localize,
    rank_files_by_intent,
    rank_symbols_by_intent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(symbols: list[dict]) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.execute(
        "CREATE TABLE symbols "
        "(id INTEGER PRIMARY KEY, path TEXT, kind TEXT, name TEXT, "
        "lineno INTEGER, end_lineno INTEGER, pagerank REAL, docstring TEXT)"
    )
    for s in symbols:
        conn.execute(
            "INSERT INTO symbols (path, kind, name, lineno, end_lineno, pagerank, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                s["path"],
                s.get("kind", "function"),
                s["name"],
                s.get("lineno", 1),
                s.get("end_lineno", 20),
                s.get("pagerank", 0.5),
                s.get("docstring", ""),
            ),
        )
    conn.commit()
    conn.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# hierarchical_localize
# ---------------------------------------------------------------------------


def test_hierarchical_localize_no_db_returns_empty() -> None:
    result = hierarchical_localize({"capability": "auth", "keywords": ["login"]})
    assert isinstance(result, dict)
    assert result["files"] == []
    assert result["symbols"] == []
    assert result["edit_sites"] == []


def test_hierarchical_localize_empty_intent_no_db() -> None:
    result = hierarchical_localize({})
    assert "files" in result and "symbols" in result and "edit_sites" in result


def test_hierarchical_localize_with_db() -> None:
    db = _make_db([
        {"path": "src/auth.py", "name": "login", "kind": "function",
         "lineno": 10, "end_lineno": 30, "pagerank": 0.8, "docstring": "user authentication login"},
        {"path": "src/user.py", "name": "UserModel", "kind": "class",
         "lineno": 5, "end_lineno": 50, "pagerank": 0.6, "docstring": "user data model"},
    ])
    result = hierarchical_localize(
        {"capability": "user authentication", "keywords": ["login"]},
        survey_db=db,
    )
    assert isinstance(result["files"], list)
    assert len(result["files"]) > 0
    assert "src/auth.py" in result["files"]
    assert len(result["symbols"]) > 0
    assert len(result["edit_sites"]) > 0


def test_hierarchical_localize_top_k_files_respected() -> None:
    symbols = [
        {"path": f"src/file{i}.py", "name": f"func{i}", "lineno": 1, "end_lineno": 10}
        for i in range(20)
    ]
    db = _make_db(symbols)
    result = hierarchical_localize({"capability": "test"}, survey_db=db, top_k_files=5)
    assert len(result["files"]) <= 5


def test_hierarchical_localize_top_k_symbols_respected() -> None:
    symbols = [
        {"path": "src/a.py", "name": f"func{i}", "lineno": i * 10, "end_lineno": i * 10 + 5}
        for i in range(10)
    ]
    db = _make_db(symbols)
    result = hierarchical_localize({"capability": "test"}, survey_db=db, top_k_symbols=3)
    assert len(result["symbols"]) <= 3


# ---------------------------------------------------------------------------
# rank_files_by_intent
# ---------------------------------------------------------------------------


def test_rank_files_by_intent_empty_symbols() -> None:
    result = rank_files_by_intent([], {"capability": "auth"})
    assert result == []


def test_rank_files_by_intent_returns_list_of_paths() -> None:
    symbols = [
        {"path": "src/auth.py", "name": "login", "kind": "function",
         "pagerank": 0.9, "docstring": "authentication login"},
        {"path": "src/db.py", "name": "connect", "kind": "function",
         "pagerank": 0.3, "docstring": "database connect"},
    ]
    result = rank_files_by_intent(symbols, {"capability": "authentication login"})
    assert isinstance(result, list)
    assert "src/auth.py" in result


def test_rank_files_by_intent_top_k() -> None:
    symbols = [
        {"path": f"src/f{i}.py", "name": f"fn{i}", "kind": "function", "pagerank": 0.5, "docstring": "x"}
        for i in range(10)
    ]
    result = rank_files_by_intent(symbols, {"capability": "test"}, top_k=3)
    assert len(result) <= 3


# ---------------------------------------------------------------------------
# rank_symbols_by_intent
# ---------------------------------------------------------------------------


def test_rank_symbols_by_intent_empty() -> None:
    assert rank_symbols_by_intent([], {"capability": "auth"}) == []


def test_rank_symbols_by_intent_adds_score() -> None:
    symbols = [
        {"path": "src/a.py", "name": "login", "kind": "function",
         "lineno": 1, "end_lineno": 10, "pagerank": 0.8, "docstring": "auth login"},
    ]
    result = rank_symbols_by_intent(symbols, {"capability": "login", "keywords": ["auth"]})
    assert len(result) == 1
    assert "score" in result[0]
    assert isinstance(result[0]["score"], float)


def test_rank_symbols_by_intent_sorted_descending() -> None:
    symbols = [
        {"path": "src/a.py", "name": "login", "kind": "function",
         "lineno": 1, "end_lineno": 10, "pagerank": 0.9, "docstring": "auth login user"},
        {"path": "src/b.py", "name": "random_func", "kind": "function",
         "lineno": 1, "end_lineno": 5, "pagerank": 0.1, "docstring": "unrelated code"},
    ]
    result = rank_symbols_by_intent(symbols, {"capability": "auth login", "keywords": ["user"]})
    assert result[0]["score"] >= result[-1]["score"]


def test_rank_symbols_by_intent_top_k() -> None:
    symbols = [
        {"path": "src/a.py", "name": f"fn{i}", "kind": "function",
         "lineno": i, "end_lineno": i + 5, "pagerank": 0.5, "docstring": "x"}
        for i in range(8)
    ]
    result = rank_symbols_by_intent(symbols, {"capability": "x"}, top_k=3)
    assert len(result) <= 3


# ---------------------------------------------------------------------------
# extract_edit_sites
# ---------------------------------------------------------------------------


def test_extract_edit_sites_empty() -> None:
    assert extract_edit_sites([]) == []


def test_extract_edit_sites_function_scope() -> None:
    sym = {"path": "src/a.py", "name": "my_fn", "kind": "function",
           "lineno": 10, "end_lineno": 25, "pagerank": 0.5, "score": 0.7}
    sites = extract_edit_sites([sym])
    assert len(sites) == 1
    assert sites[0]["path"] == "src/a.py"
    assert sites[0]["start_line"] == 10
    assert sites[0]["end_line"] == 25
    assert sites[0]["scope"] == "function"
    assert sites[0]["name"] == "my_fn"


def test_extract_edit_sites_class_scope() -> None:
    sym = {"path": "src/a.py", "name": "MyClass", "kind": "class",
           "lineno": 5, "end_lineno": 50, "pagerank": 0.5, "score": 0.8}
    sites = extract_edit_sites([sym])
    assert sites[0]["scope"] == "class"


def test_extract_edit_sites_module_scope() -> None:
    sym = {"path": "src/a.py", "name": "CONSTANT", "kind": "variable",
           "lineno": 1, "end_lineno": 1, "pagerank": 0.1, "score": 0.2}
    sites = extract_edit_sites([sym])
    assert sites[0]["scope"] == "module"


def test_extract_edit_sites_missing_end_lineno() -> None:
    sym = {"path": "src/a.py", "name": "fn", "kind": "function",
           "lineno": 10, "pagerank": 0.5, "score": 0.5}
    sites = extract_edit_sites([sym])
    assert sites[0]["start_line"] == 10
    assert sites[0]["end_line"] >= sites[0]["start_line"]


# ---------------------------------------------------------------------------
# check_disjoint
# ---------------------------------------------------------------------------


def test_check_disjoint_both_empty() -> None:
    assert check_disjoint({"edit_sites": []}, {"edit_sites": []}) is False


def test_check_disjoint_different_files() -> None:
    loc_a = {"edit_sites": [{"path": "a.py", "start_line": 1, "end_line": 10}]}
    loc_b = {"edit_sites": [{"path": "b.py", "start_line": 1, "end_line": 10}]}
    assert check_disjoint(loc_a, loc_b) is False


def test_check_disjoint_same_file_non_overlapping() -> None:
    loc_a = {"edit_sites": [{"path": "a.py", "start_line": 1, "end_line": 10}]}
    loc_b = {"edit_sites": [{"path": "a.py", "start_line": 20, "end_line": 30}]}
    assert check_disjoint(loc_a, loc_b) is False


def test_check_disjoint_same_file_overlapping() -> None:
    loc_a = {"edit_sites": [{"path": "a.py", "start_line": 5, "end_line": 15}]}
    loc_b = {"edit_sites": [{"path": "a.py", "start_line": 10, "end_line": 25}]}
    assert check_disjoint(loc_a, loc_b) is True


def test_check_disjoint_same_file_adjacent_non_overlapping() -> None:
    loc_a = {"edit_sites": [{"path": "a.py", "start_line": 1, "end_line": 10}]}
    loc_b = {"edit_sites": [{"path": "a.py", "start_line": 11, "end_line": 20}]}
    assert check_disjoint(loc_a, loc_b) is False
