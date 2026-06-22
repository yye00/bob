"""Tests for bob3.brownfield.localizer — BF-4 Hierarchical Localizer.

Covers the full three-stage pipeline:
  Stage A — file shortlist via BM25
  Stage B — symbol shortlist via pagerank * cosine
  Stage C — edit-site extraction

Also tests check_disjoint and the localize_and_persist coordinator helper.
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
    find_edit_sites,
    localize,
    rank_symbols,
    rank_symbols_by_intent,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_survey_db(symbols: list[dict[str, Any]]) -> Path:
    """Create a temporary survey.db with the given symbols."""
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
                s["path"],
                s.get("kind", "function"),
                s["name"],
                s.get("lineno", 1),
                s.get("end_lineno", 10),
                s.get("pagerank", 0.5),
                s.get("docstring", ""),
            ),
        )
    conn.commit()
    conn.close()
    return Path(tmp.name)


SAMPLE_SYMBOLS = [
    {
        "path": "src/auth/login.py",
        "kind": "function",
        "name": "authenticate_user",
        "lineno": 10,
        "end_lineno": 40,
        "pagerank": 0.9,
        "docstring": "Authenticate a user with username and password",
    },
    {
        "path": "src/auth/login.py",
        "kind": "class",
        "name": "LoginHandler",
        "lineno": 1,
        "end_lineno": 8,
        "pagerank": 0.7,
        "docstring": "HTTP handler for login endpoint",
    },
    {
        "path": "src/db/models.py",
        "kind": "class",
        "name": "User",
        "lineno": 5,
        "end_lineno": 50,
        "pagerank": 0.8,
        "docstring": "Database model for user accounts",
    },
    {
        "path": "src/utils/helpers.py",
        "kind": "function",
        "name": "hash_password",
        "lineno": 3,
        "end_lineno": 15,
        "pagerank": 0.4,
        "docstring": "Hash a plaintext password using bcrypt",
    },
    {
        "path": "src/api/endpoints.py",
        "kind": "function",
        "name": "get_current_user",
        "lineno": 20,
        "end_lineno": 35,
        "pagerank": 0.6,
        "docstring": "Return the currently authenticated user from JWT token",
    },
]


# ---------------------------------------------------------------------------
# Test: localize() API
# ---------------------------------------------------------------------------

class TestLocalize:
    def test_returns_dict_with_required_keys(self) -> None:
        result = localize({"capability": "authenticate user"})
        assert isinstance(result, dict)
        assert "files" in result
        assert "symbols" in result
        assert "edit_sites" in result

    def test_no_survey_db_returns_empty(self) -> None:
        result = localize({"capability": "auth"})
        assert result["files"] == []
        assert result["symbols"] == []
        assert result["edit_sites"] == []

    def test_with_survey_db_returns_nonempty(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            result = localize({"capability": "authenticate user", "keywords": ["auth"]}, survey_db=db)
            assert len(result["files"]) > 0
            assert len(result["symbols"]) > 0
            assert len(result["edit_sites"]) > 0
        finally:
            db.unlink(missing_ok=True)

    def test_auth_intent_ranks_auth_files_higher(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            result = localize(
                {"capability": "authenticate user login", "keywords": ["auth", "login"]},
                survey_db=db,
            )
            # Auth-related files should appear in the file shortlist
            auth_file_present = any("auth" in f or "login" in f for f in result["files"])
            assert auth_file_present, f"Expected auth file in shortlist, got: {result['files']}"
        finally:
            db.unlink(missing_ok=True)

    def test_respects_top_k_files_limit(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            result = localize({"capability": "auth"}, survey_db=db, top_k_files=2)
            assert len(result["files"]) <= 2
        finally:
            db.unlink(missing_ok=True)

    def test_respects_top_k_symbols_limit(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            result = localize({"capability": "auth"}, survey_db=db, top_k_symbols=3)
            assert len(result["symbols"]) <= 3
        finally:
            db.unlink(missing_ok=True)

    def test_edit_sites_count_matches_symbols(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            result = localize({"capability": "auth"}, survey_db=db)
            assert len(result["edit_sites"]) == len(result["symbols"])
        finally:
            db.unlink(missing_ok=True)

    def test_missing_db_path_returns_empty(self, tmp_path: Path) -> None:
        result = localize({"capability": "auth"}, survey_db=tmp_path / "nonexistent.db")
        assert result == {"files": [], "symbols": [], "edit_sites": []}

    def test_intent_with_all_keys(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            result = localize(
                {
                    "capability": "hash password",
                    "target_subsystem": "utils",
                    "keywords": ["bcrypt", "hash"],
                },
                survey_db=db,
            )
            assert isinstance(result, dict)
        finally:
            db.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test: rank_symbols_by_intent (and its alias rank_symbols)
# ---------------------------------------------------------------------------

class TestRankSymbols:
    def test_returns_list(self) -> None:
        result = rank_symbols_by_intent(SAMPLE_SYMBOLS, {"capability": "auth"})
        assert isinstance(result, list)

    def test_result_length_capped_at_top_k(self) -> None:
        result = rank_symbols_by_intent(SAMPLE_SYMBOLS, {"capability": "auth"}, top_k=3)
        assert len(result) <= 3

    def test_each_symbol_has_score_key(self) -> None:
        result = rank_symbols_by_intent(SAMPLE_SYMBOLS, {"capability": "auth"}, top_k=5)
        for sym in result:
            assert "score" in sym
            assert isinstance(sym["score"], float)

    def test_symbols_sorted_descending_by_score(self) -> None:
        result = rank_symbols_by_intent(SAMPLE_SYMBOLS, {"capability": "auth"}, top_k=5)
        scores = [s["score"] for s in result]
        assert scores == sorted(scores, reverse=True)

    def test_high_pagerank_symbol_scores_well(self) -> None:
        syms = [
            {"id": 1, "path": "a.py", "kind": "function", "name": "foo",
             "lineno": 1, "end_lineno": 10, "pagerank": 0.0, "docstring": "foo"},
            {"id": 2, "path": "a.py", "kind": "function", "name": "bar",
             "lineno": 11, "end_lineno": 20, "pagerank": 1.0, "docstring": "bar"},
        ]
        result = rank_symbols_by_intent(syms, {})
        # With empty intent, cosine = 0 for both; pagerank alone decides ranking
        assert result[0]["name"] == "bar"

    def test_empty_symbols_returns_empty(self) -> None:
        assert rank_symbols_by_intent([], {"capability": "auth"}) == []

    def test_alias_rank_symbols_same_as_rank_symbols_by_intent(self) -> None:
        r1 = rank_symbols_by_intent(SAMPLE_SYMBOLS, {"capability": "user auth"}, top_k=3)
        r2 = rank_symbols(SAMPLE_SYMBOLS, {"capability": "user auth"}, top_k=3)
        assert r1 == r2

    def test_relevant_symbols_score_higher_than_irrelevant(self) -> None:
        syms = [
            {"id": 1, "path": "src/auth.py", "kind": "function", "name": "authenticate_user",
             "lineno": 1, "end_lineno": 20, "pagerank": 0.5,
             "docstring": "Authenticate a user with username and password credentials"},
            {"id": 2, "path": "src/db.py", "kind": "function", "name": "create_table",
             "lineno": 1, "end_lineno": 5, "pagerank": 0.5,
             "docstring": "Create a database table schema"},
        ]
        result = rank_symbols_by_intent(
            syms, {"capability": "authenticate user", "keywords": ["auth", "password"]}, top_k=2
        )
        assert result[0]["name"] == "authenticate_user"

    def test_original_symbol_keys_preserved(self) -> None:
        syms = [
            {"id": 99, "path": "foo.py", "kind": "class", "name": "Foo",
             "lineno": 1, "end_lineno": 30, "pagerank": 0.5, "docstring": "Foo class"},
        ]
        result = rank_symbols_by_intent(syms, {"capability": "foo"})
        assert result[0]["id"] == 99
        assert result[0]["path"] == "foo.py"
        assert result[0]["name"] == "Foo"


# ---------------------------------------------------------------------------
# Test: extract_edit_sites (and its alias find_edit_sites)
# ---------------------------------------------------------------------------

class TestExtractEditSites:
    def test_returns_list(self) -> None:
        ranked = rank_symbols_by_intent(SAMPLE_SYMBOLS, {"capability": "auth"}, top_k=3)
        sites = extract_edit_sites(ranked)
        assert isinstance(sites, list)

    def test_length_matches_input(self) -> None:
        ranked = rank_symbols_by_intent(SAMPLE_SYMBOLS, {"capability": "auth"}, top_k=3)
        sites = extract_edit_sites(ranked)
        assert len(sites) == len(ranked)

    def test_each_site_has_required_keys(self) -> None:
        ranked = rank_symbols_by_intent(SAMPLE_SYMBOLS, {"capability": "auth"}, top_k=3)
        sites = extract_edit_sites(ranked)
        for site in sites:
            assert "path" in site
            assert "start_line" in site
            assert "end_line" in site
            assert "scope" in site
            assert "name" in site

    def test_function_kind_maps_to_function_scope(self) -> None:
        syms = [
            {"path": "a.py", "kind": "function", "name": "do_thing",
             "lineno": 5, "end_lineno": 20, "pagerank": 0.5, "score": 0.5},
        ]
        sites = extract_edit_sites(syms)
        assert sites[0]["scope"] == "function"

    def test_class_kind_maps_to_class_scope(self) -> None:
        syms = [
            {"path": "a.py", "kind": "class", "name": "MyClass",
             "lineno": 1, "end_lineno": 50, "pagerank": 0.7, "score": 0.7},
        ]
        sites = extract_edit_sites(syms)
        assert sites[0]["scope"] == "class"

    def test_method_kind_maps_to_function_scope(self) -> None:
        syms = [
            {"path": "a.py", "kind": "method", "name": "my_method",
             "lineno": 10, "end_lineno": 30, "pagerank": 0.5, "score": 0.5},
        ]
        sites = extract_edit_sites(syms)
        assert sites[0]["scope"] == "function"

    def test_unknown_kind_maps_to_module_scope(self) -> None:
        syms = [
            {"path": "a.py", "kind": "constant", "name": "MY_CONST",
             "lineno": 1, "end_lineno": 1, "pagerank": 0.1, "score": 0.1},
        ]
        sites = extract_edit_sites(syms)
        assert sites[0]["scope"] == "module"

    def test_start_line_lte_end_line(self) -> None:
        syms = [
            {"path": "a.py", "kind": "function", "name": "foo",
             "lineno": 10, "end_lineno": 5, "pagerank": 0.5, "score": 0.5},
        ]
        sites = extract_edit_sites(syms)
        assert sites[0]["start_line"] <= sites[0]["end_line"]

    def test_fallback_end_line_when_none(self) -> None:
        syms = [
            {"path": "a.py", "kind": "function", "name": "foo",
             "lineno": 10, "end_lineno": None, "pagerank": 0.5, "score": 0.5},
        ]
        sites = extract_edit_sites(syms)
        assert sites[0]["end_line"] >= sites[0]["start_line"]
        assert sites[0]["end_line"] >= 10

    def test_alias_find_edit_sites_same_result(self) -> None:
        ranked = rank_symbols_by_intent(SAMPLE_SYMBOLS, {"capability": "auth"}, top_k=3)
        r1 = extract_edit_sites(ranked)
        r2 = find_edit_sites(ranked)
        assert r1 == r2

    def test_empty_input_returns_empty(self) -> None:
        assert extract_edit_sites([]) == []

    def test_path_preserved_in_edit_site(self) -> None:
        syms = [
            {"path": "src/special/path.py", "kind": "function", "name": "special_func",
             "lineno": 42, "end_lineno": 80, "pagerank": 0.9, "score": 0.9},
        ]
        sites = extract_edit_sites(syms)
        assert sites[0]["path"] == "src/special/path.py"


# ---------------------------------------------------------------------------
# Test: check_disjoint
# ---------------------------------------------------------------------------

class TestCheckDisjoint:
    def _make_loc(self, sites: list[dict]) -> dict:
        return {"edit_sites": sites}

    def test_overlapping_same_file_returns_true(self) -> None:
        loc_a = self._make_loc([{"path": "a.py", "start_line": 1, "end_line": 20, "scope": "function"}])
        loc_b = self._make_loc([{"path": "a.py", "start_line": 10, "end_line": 30, "scope": "function"}])
        assert check_disjoint(loc_a, loc_b) is True

    def test_non_overlapping_same_file_returns_false(self) -> None:
        loc_a = self._make_loc([{"path": "a.py", "start_line": 1, "end_line": 10, "scope": "function"}])
        loc_b = self._make_loc([{"path": "a.py", "start_line": 20, "end_line": 30, "scope": "function"}])
        assert check_disjoint(loc_a, loc_b) is False

    def test_different_files_never_overlap(self) -> None:
        loc_a = self._make_loc([{"path": "a.py", "start_line": 1, "end_line": 100, "scope": "function"}])
        loc_b = self._make_loc([{"path": "b.py", "start_line": 1, "end_line": 100, "scope": "function"}])
        assert check_disjoint(loc_a, loc_b) is False

    def test_empty_edit_sites_returns_false(self) -> None:
        assert check_disjoint({"edit_sites": []}, {"edit_sites": []}) is False

    def test_touching_lines_overlap(self) -> None:
        # Lines [1,10] and [10,20] share line 10 — should be considered overlapping
        loc_a = self._make_loc([{"path": "a.py", "start_line": 1, "end_line": 10, "scope": "class"}])
        loc_b = self._make_loc([{"path": "a.py", "start_line": 10, "end_line": 20, "scope": "function"}])
        assert check_disjoint(loc_a, loc_b) is True

    def test_single_line_overlap(self) -> None:
        loc_a = self._make_loc([{"path": "x.py", "start_line": 5, "end_line": 5, "scope": "module"}])
        loc_b = self._make_loc([{"path": "x.py", "start_line": 5, "end_line": 5, "scope": "module"}])
        assert check_disjoint(loc_a, loc_b) is True

    def test_contained_range_overlaps(self) -> None:
        loc_a = self._make_loc([{"path": "a.py", "start_line": 1, "end_line": 100, "scope": "class"}])
        loc_b = self._make_loc([{"path": "a.py", "start_line": 40, "end_line": 60, "scope": "function"}])
        assert check_disjoint(loc_a, loc_b) is True

    def test_multiple_sites_one_overlap_returns_true(self) -> None:
        loc_a = self._make_loc([
            {"path": "a.py", "start_line": 1, "end_line": 10, "scope": "function"},
            {"path": "b.py", "start_line": 1, "end_line": 50, "scope": "class"},
        ])
        loc_b = self._make_loc([
            {"path": "c.py", "start_line": 1, "end_line": 10, "scope": "function"},
            {"path": "a.py", "start_line": 5, "end_line": 15, "scope": "function"},  # overlaps
        ])
        assert check_disjoint(loc_a, loc_b) is True

    def test_multiple_sites_no_overlap_returns_false(self) -> None:
        loc_a = self._make_loc([
            {"path": "a.py", "start_line": 1, "end_line": 10, "scope": "function"},
        ])
        loc_b = self._make_loc([
            {"path": "b.py", "start_line": 1, "end_line": 10, "scope": "function"},
            {"path": "c.py", "start_line": 1, "end_line": 10, "scope": "function"},
        ])
        assert check_disjoint(loc_a, loc_b) is False


# ---------------------------------------------------------------------------
# Test: full pipeline integration
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_pipeline_produces_consistent_output(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            result1 = localize({"capability": "user authentication"}, survey_db=db)
            result2 = localize({"capability": "user authentication"}, survey_db=db)
            assert result1 == result2
        finally:
            db.unlink(missing_ok=True)

    def test_pipeline_edit_sites_have_valid_line_ranges(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            result = localize({"capability": "auth"}, survey_db=db)
            for site in result["edit_sites"]:
                assert site["start_line"] >= 1
                assert site["end_line"] >= site["start_line"]
        finally:
            db.unlink(missing_ok=True)

    def test_pipeline_files_are_subset_of_db_paths(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            result = localize({"capability": "auth"}, survey_db=db)
            all_paths = {s["path"] for s in SAMPLE_SYMBOLS}
            for f in result["files"]:
                assert f in all_paths, f"Unexpected file path: {f}"
        finally:
            db.unlink(missing_ok=True)

    def test_pipeline_symbols_have_all_required_fields(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            result = localize({"capability": "auth"}, survey_db=db)
            for sym in result["symbols"]:
                assert "path" in sym
                assert "name" in sym
                assert "kind" in sym
                assert "score" in sym
        finally:
            db.unlink(missing_ok=True)

    def test_disjoint_check_on_pipeline_outputs(self) -> None:
        db = _make_survey_db(SAMPLE_SYMBOLS)
        try:
            loc_auth = localize({"capability": "authenticate user login"}, survey_db=db, top_k_files=2)
            loc_db = localize({"capability": "database model schema"}, survey_db=db, top_k_files=2)
            # Both are valid localization results — disjoint check must not raise
            overlap = check_disjoint(loc_auth, loc_db)
            assert isinstance(overlap, bool)
        finally:
            db.unlink(missing_ok=True)

    def test_large_db_respects_top_k(self) -> None:
        many_symbols = [
            {
                "path": f"src/module_{i}.py",
                "kind": "function",
                "name": f"function_{i}",
                "lineno": 1,
                "end_lineno": 10,
                "pagerank": 0.1,
                "docstring": f"function number {i}",
            }
            for i in range(50)
        ]
        db = _make_survey_db(many_symbols)
        try:
            result = localize({"capability": "function"}, survey_db=db, top_k_files=10, top_k_symbols=5)
            assert len(result["files"]) <= 10
            assert len(result["symbols"]) <= 5
            assert len(result["edit_sites"]) <= 5
        finally:
            db.unlink(missing_ok=True)
