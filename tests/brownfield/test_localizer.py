"""Tests for bob3.brownfield.localizer — BF-4 Hierarchical Localizer."""

from __future__ import annotations

import json
import sqlite3
import textwrap
from pathlib import Path
from typing import Any

import pytest

from bob3.brownfield.localizer import (
    extract_edit_sites,
    localize,
    rank_symbols_by_intent,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def survey_db(tmp_path: Path) -> Path:
    """Create a minimal survey.db with symbols and edges for testing."""
    db_path = tmp_path / "survey.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS symbols (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            path      TEXT    NOT NULL,
            kind      TEXT    NOT NULL,
            name      TEXT    NOT NULL,
            sha       TEXT    NOT NULL,
            lineno    INTEGER NOT NULL,
            end_lineno INTEGER,
            parent_id INTEGER REFERENCES symbols(id),
            pagerank  REAL    DEFAULT 0.0,
            docstring TEXT    DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS edges (
            src_id INTEGER NOT NULL REFERENCES symbols(id),
            dst_id INTEGER NOT NULL REFERENCES symbols(id),
            kind   TEXT    NOT NULL
        );
    """)
    # Insert test symbols
    symbols = [
        # (path, kind, name, sha, lineno, end_lineno, parent_id, pagerank, docstring)
        ("src/auth/login.py",   "function", "authenticate_user",  "abc", 10, 30, None, 0.8, "Authenticate a user by credentials"),
        ("src/auth/login.py",   "function", "logout_user",        "abc", 35, 50, None, 0.3, "Log out the current user session"),
        ("src/auth/models.py",  "class",    "UserCredential",     "def", 5,  40, None, 0.9, "Model for user login credentials"),
        ("src/auth/models.py",  "function", "validate_token",     "def", 45, 60, None, 0.6, "Validate an authentication token"),
        ("src/payment/charge.py", "function", "process_payment",  "ghi", 8,  45, None, 0.5, "Process a payment transaction"),
        ("src/payment/charge.py", "class",    "PaymentGateway",   "ghi", 50, 90, None, 0.4, "Payment gateway integration"),
        ("src/utils/helpers.py",  "function", "format_response",  "jkl", 3,  12, None, 0.2, "Format API response objects"),
        ("src/utils/helpers.py",  "function", "hash_password",    "jkl", 15, 25, None, 0.7, "Hash a password using bcrypt"),
    ]
    for s in symbols:
        conn.execute(
            "INSERT INTO symbols (path, kind, name, sha, lineno, end_lineno, parent_id, pagerank, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            s,
        )
    conn.commit()

    # Add some edges to test pagerank influence
    conn.execute("INSERT INTO edges (src_id, dst_id, kind) VALUES (1, 3, 'ref')")
    conn.execute("INSERT INTO edges (src_id, dst_id, kind) VALUES (4, 3, 'ref')")
    conn.execute("INSERT INTO edges (src_id, dst_id, kind) VALUES (1, 8, 'ref')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def auth_intent() -> dict[str, Any]:
    return {
        "capability": "authenticate users with token validation",
        "target_subsystem": "auth",
        "keywords": ["authenticate", "token", "credentials"],
    }


@pytest.fixture()
def payment_intent() -> dict[str, Any]:
    return {
        "capability": "process payment transactions",
        "target_subsystem": "payment",
        "keywords": ["payment", "charge", "gateway"],
    }


# ---------------------------------------------------------------------------
# Tests: rank_symbols_by_intent
# ---------------------------------------------------------------------------


def test_rank_symbols_by_intent_returns_list(survey_db: Path, auth_intent: dict) -> None:
    """rank_symbols_by_intent must return a non-empty list."""
    rows = _all_symbols_from_db(survey_db)
    result = rank_symbols_by_intent(rows, auth_intent, top_k=5)
    assert isinstance(result, list)
    assert len(result) > 0


def test_rank_symbols_by_intent_top_k_limit(survey_db: Path, auth_intent: dict) -> None:
    """rank_symbols_by_intent must not return more than top_k symbols."""
    rows = _all_symbols_from_db(survey_db)
    result = rank_symbols_by_intent(rows, auth_intent, top_k=3)
    assert len(result) <= 3


def test_rank_symbols_by_intent_auth_prefers_auth_symbols(survey_db: Path, auth_intent: dict) -> None:
    """Auth intent should surface auth-related symbols first."""
    rows = _all_symbols_from_db(survey_db)
    result = rank_symbols_by_intent(rows, auth_intent, top_k=5)
    top_names = [r["name"] for r in result]
    # At least one of the top results should be auth-related
    auth_names = {"authenticate_user", "UserCredential", "validate_token", "hash_password"}
    assert any(name in auth_names for name in top_names), (
        f"Expected auth symbols in top results, got {top_names}"
    )


def test_rank_symbols_by_intent_payment_prefers_payment_symbols(
    survey_db: Path, payment_intent: dict
) -> None:
    """Payment intent should surface payment-related symbols first."""
    rows = _all_symbols_from_db(survey_db)
    result = rank_symbols_by_intent(rows, payment_intent, top_k=5)
    top_names = [r["name"] for r in result]
    payment_names = {"process_payment", "PaymentGateway"}
    assert any(name in payment_names for name in top_names), (
        f"Expected payment symbols in top results, got {top_names}"
    )


def test_rank_symbols_by_intent_each_result_has_required_keys(
    survey_db: Path, auth_intent: dict
) -> None:
    """Each ranked symbol must have path, name, lineno, kind, and score."""
    rows = _all_symbols_from_db(survey_db)
    result = rank_symbols_by_intent(rows, auth_intent, top_k=5)
    for item in result:
        assert "path" in item, f"Missing 'path' in {item}"
        assert "name" in item, f"Missing 'name' in {item}"
        assert "lineno" in item, f"Missing 'lineno' in {item}"
        assert "kind" in item, f"Missing 'kind' in {item}"
        assert "score" in item, f"Missing 'score' in {item}"


def test_rank_symbols_by_intent_scores_are_nonnegative(
    survey_db: Path, auth_intent: dict
) -> None:
    rows = _all_symbols_from_db(survey_db)
    result = rank_symbols_by_intent(rows, auth_intent, top_k=8)
    for item in result:
        assert item["score"] >= 0.0, f"Negative score in {item}"


def test_rank_symbols_by_intent_sorted_descending(survey_db: Path, auth_intent: dict) -> None:
    """Results must be sorted by score descending."""
    rows = _all_symbols_from_db(survey_db)
    result = rank_symbols_by_intent(rows, auth_intent, top_k=8)
    scores = [r["score"] for r in result]
    assert scores == sorted(scores, reverse=True), "Results not sorted by score descending"


# ---------------------------------------------------------------------------
# Tests: extract_edit_sites
# ---------------------------------------------------------------------------


def test_extract_edit_sites_returns_list(survey_db: Path, auth_intent: dict) -> None:
    """extract_edit_sites must return a list of edit-site dicts."""
    rows = _all_symbols_from_db(survey_db)
    ranked = rank_symbols_by_intent(rows, auth_intent, top_k=3)
    sites = extract_edit_sites(ranked)
    assert isinstance(sites, list)


def test_extract_edit_sites_required_keys(survey_db: Path, auth_intent: dict) -> None:
    """Each edit site must have path, start_line, end_line, scope."""
    rows = _all_symbols_from_db(survey_db)
    ranked = rank_symbols_by_intent(rows, auth_intent, top_k=3)
    sites = extract_edit_sites(ranked)
    for site in sites:
        assert "path" in site, f"Missing 'path' in edit site {site}"
        assert "start_line" in site, f"Missing 'start_line' in edit site {site}"
        assert "end_line" in site, f"Missing 'end_line' in edit site {site}"
        assert "scope" in site, f"Missing 'scope' in edit site {site}"


def test_extract_edit_sites_scope_values(survey_db: Path, auth_intent: dict) -> None:
    """scope must be one of 'function', 'class', or 'module'."""
    rows = _all_symbols_from_db(survey_db)
    ranked = rank_symbols_by_intent(rows, auth_intent, top_k=5)
    sites = extract_edit_sites(ranked)
    valid_scopes = {"function", "class", "module"}
    for site in sites:
        assert site["scope"] in valid_scopes, (
            f"Invalid scope '{site['scope']}' in {site}"
        )


def test_extract_edit_sites_lineno_ordering(survey_db: Path, auth_intent: dict) -> None:
    """start_line must be <= end_line for every edit site."""
    rows = _all_symbols_from_db(survey_db)
    ranked = rank_symbols_by_intent(rows, auth_intent, top_k=5)
    sites = extract_edit_sites(ranked)
    for site in sites:
        assert site["start_line"] <= site["end_line"], (
            f"start_line > end_line in {site}"
        )


# ---------------------------------------------------------------------------
# Tests: localize (end-to-end pipeline)
# ---------------------------------------------------------------------------


def test_localize_returns_dict(survey_db: Path, auth_intent: dict) -> None:
    """localize() must return a dict."""
    result = localize(auth_intent, survey_db=survey_db)
    assert isinstance(result, dict)


def test_localize_has_required_top_level_keys(survey_db: Path, auth_intent: dict) -> None:
    """localize() result must have files, symbols, edit_sites."""
    result = localize(auth_intent, survey_db=survey_db)
    assert "files" in result, f"Missing 'files' key: {list(result.keys())}"
    assert "symbols" in result, f"Missing 'symbols' key: {list(result.keys())}"
    assert "edit_sites" in result, f"Missing 'edit_sites' key: {list(result.keys())}"


def test_localize_files_is_list(survey_db: Path, auth_intent: dict) -> None:
    result = localize(auth_intent, survey_db=survey_db)
    assert isinstance(result["files"], list)


def test_localize_symbols_is_list(survey_db: Path, auth_intent: dict) -> None:
    result = localize(auth_intent, survey_db=survey_db)
    assert isinstance(result["symbols"], list)


def test_localize_edit_sites_is_list(survey_db: Path, auth_intent: dict) -> None:
    result = localize(auth_intent, survey_db=survey_db)
    assert isinstance(result["edit_sites"], list)


def test_localize_files_bounded_by_top_k(survey_db: Path, auth_intent: dict) -> None:
    """File shortlist must be at most top_k_files entries."""
    result = localize(auth_intent, survey_db=survey_db, top_k_files=5)
    assert len(result["files"]) <= 5


def test_localize_symbols_bounded_by_top_k(survey_db: Path, auth_intent: dict) -> None:
    """Symbol shortlist must be at most top_k_symbols entries."""
    result = localize(auth_intent, survey_db=survey_db, top_k_symbols=3)
    assert len(result["symbols"]) <= 3


def test_localize_auth_intent_finds_auth_files(survey_db: Path, auth_intent: dict) -> None:
    """Auth intent should find auth-related files in the shortlist."""
    result = localize(auth_intent, survey_db=survey_db, top_k_files=5)
    files = result["files"]
    assert any("auth" in f for f in files), (
        f"Expected auth files in shortlist, got {files}"
    )


def test_localize_payment_intent_finds_payment_files(
    survey_db: Path, payment_intent: dict
) -> None:
    """Payment intent should find payment-related files."""
    result = localize(payment_intent, survey_db=survey_db, top_k_files=5)
    files = result["files"]
    assert any("payment" in f for f in files), (
        f"Expected payment files in shortlist, got {files}"
    )


def test_localize_edit_sites_match_symbols(survey_db: Path, auth_intent: dict) -> None:
    """Edit sites should be derived from the shortlisted symbols."""
    result = localize(auth_intent, survey_db=survey_db)
    symbol_paths = {s["path"] for s in result["symbols"]}
    for site in result["edit_sites"]:
        assert site["path"] in symbol_paths, (
            f"Edit site path {site['path']!r} not in symbol paths {symbol_paths}"
        )


def test_localize_no_survey_db_returns_empty(tmp_path: Path, auth_intent: dict) -> None:
    """localize() with nonexistent survey.db should return empty shortlists."""
    result = localize(auth_intent, survey_db=tmp_path / "nonexistent.db")
    assert result["files"] == []
    assert result["symbols"] == []
    assert result["edit_sites"] == []


def test_localize_empty_intent_returns_empty_or_partial(
    survey_db: Path,
) -> None:
    """An empty intent should return results (no crash), possibly empty."""
    empty_intent: dict[str, Any] = {
        "capability": "",
        "target_subsystem": "",
        "keywords": [],
    }
    result = localize(empty_intent, survey_db=survey_db)
    assert isinstance(result, dict)
    assert "files" in result
    assert "symbols" in result
    assert "edit_sites" in result


# ---------------------------------------------------------------------------
# Tests: disjointness check
# ---------------------------------------------------------------------------


def test_localize_disjointness_overlap_detected(survey_db: Path) -> None:
    """Two localizations with overlapping edit sites should be detected."""
    from bob3.brownfield.localizer import check_disjoint

    loc_a = {
        "edit_sites": [
            {"path": "src/auth/login.py", "start_line": 10, "end_line": 30, "scope": "function"},
        ]
    }
    loc_b = {
        "edit_sites": [
            {"path": "src/auth/login.py", "start_line": 20, "end_line": 40, "scope": "function"},
        ]
    }
    overlapping = check_disjoint(loc_a, loc_b)
    assert overlapping is True, "Expected overlap to be detected"


def test_localize_disjointness_no_overlap(survey_db: Path) -> None:
    """Two localizations with different paths should be disjoint."""
    from bob3.brownfield.localizer import check_disjoint

    loc_a = {
        "edit_sites": [
            {"path": "src/auth/login.py", "start_line": 10, "end_line": 30, "scope": "function"},
        ]
    }
    loc_b = {
        "edit_sites": [
            {"path": "src/payment/charge.py", "start_line": 10, "end_line": 30, "scope": "function"},
        ]
    }
    overlapping = check_disjoint(loc_a, loc_b)
    assert overlapping is False, "Expected no overlap for different paths"


def test_localize_disjointness_same_path_nonoverlapping_lines(survey_db: Path) -> None:
    """Same file but non-overlapping line ranges should be disjoint."""
    from bob3.brownfield.localizer import check_disjoint

    loc_a = {
        "edit_sites": [
            {"path": "src/auth/login.py", "start_line": 10, "end_line": 30, "scope": "function"},
        ]
    }
    loc_b = {
        "edit_sites": [
            {"path": "src/auth/login.py", "start_line": 35, "end_line": 50, "scope": "function"},
        ]
    }
    overlapping = check_disjoint(loc_a, loc_b)
    assert overlapping is False, "Expected no overlap for non-overlapping line ranges"


def test_localize_disjointness_empty_edit_sites() -> None:
    """Empty edit sites should not overlap."""
    from bob3.brownfield.localizer import check_disjoint

    assert check_disjoint({"edit_sites": []}, {"edit_sites": []}) is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_symbols_from_db(db_path: Path) -> list[dict[str, Any]]:
    """Load all symbols from survey.db for unit testing rank_symbols_by_intent."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT id, path, kind, name, lineno, end_lineno, pagerank, docstring "
            "FROM symbols"
        ).fetchall()
        return [
            {
                "id": r[0],
                "path": r[1],
                "kind": r[2],
                "name": r[3],
                "lineno": r[4],
                "end_lineno": r[5],
                "pagerank": r[6] or 0.0,
                "docstring": r[7] or "",
            }
            for r in rows
        ]
    finally:
        conn.close()
