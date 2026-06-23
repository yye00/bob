"""Tests for BF-4 — Hierarchical Localizer.

Acceptance criteria tested:
  - Function defined: bob3.bf_4_hierarchical_localizer_file_class_symbol_edit_site
  - behavior: BF-4 handles empty/zero input by returning well-defined result (no crash)
  - behavior: BF-4 raises ValueError (or returns rejection) for invalid input
  - File exists: src/bob3/brownfield/localizer.py
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from bob3.bf_4_hierarchical_localizer_file_class_symbol_edit_site import (
    bf_4_hierarchical_localizer_file_class_symbol_edit_site,
)


def test_bf_4_hierarchical_localizer_file_class_symbol_edit_site():
    """Primary AC test: function exists and returns correct structure on empty input."""
    result = bf_4_hierarchical_localizer_file_class_symbol_edit_site()
    assert isinstance(result, dict)
    assert "files" in result
    assert "symbols" in result
    assert "edit_sites" in result
    assert result["files"] == []
    assert result["symbols"] == []
    assert result["edit_sites"] == []


def test_empty_intent_returns_empty_result():
    """Empty intent (None) returns well-defined empty result, no crash."""
    result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=None)
    assert isinstance(result, dict)
    assert result["files"] == []
    assert result["symbols"] == []
    assert result["edit_sites"] == []


def test_empty_dict_intent_no_db_returns_empty():
    """Empty dict intent with no survey_db returns empty result."""
    result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent={})
    assert isinstance(result, dict)
    assert "files" in result
    assert "symbols" in result
    assert "edit_sites" in result


def test_invalid_intent_raises_value_error():
    """Non-dict intent raises ValueError (does not silently succeed)."""
    with pytest.raises(ValueError):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent="not a dict")


def test_invalid_intent_list_raises_value_error():
    """List intent raises ValueError."""
    with pytest.raises(ValueError):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=["keyword"])


def test_invalid_intent_int_raises_value_error():
    """Integer intent raises ValueError."""
    with pytest.raises(ValueError):
        bf_4_hierarchical_localizer_file_class_symbol_edit_site(intent=42)


def test_missing_survey_db_returns_empty():
    """Non-existent survey_db path returns empty result, no crash."""
    result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(
        intent={"capability": "fix bug", "keywords": ["auth"]},
        survey_db=Path("/nonexistent/survey.db"),
    )
    assert isinstance(result, dict)
    assert result["files"] == []
    assert result["symbols"] == []
    assert result["edit_sites"] == []


def _make_survey_db(symbols: list[dict]) -> Path:
    """Create a minimal in-memory survey.db temp file for tests."""
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
                s.get("end_lineno", 10),
                s.get("pagerank", 0.5),
                s.get("docstring", ""),
            ),
        )
    conn.commit()
    conn.close()
    return Path(tmp.name)


def test_real_survey_db_returns_files_and_symbols():
    """With a real survey.db, localization returns non-empty shortlists."""
    symbols = [
        {
            "path": "src/auth/login.py",
            "kind": "function",
            "name": "authenticate_user",
            "lineno": 10,
            "end_lineno": 30,
            "pagerank": 0.8,
            "docstring": "Authenticate a user with username and password",
        },
        {
            "path": "src/auth/session.py",
            "kind": "class",
            "name": "Session",
            "lineno": 1,
            "end_lineno": 50,
            "pagerank": 0.5,
            "docstring": "Session management class",
        },
        {
            "path": "src/db/models.py",
            "kind": "class",
            "name": "User",
            "lineno": 5,
            "end_lineno": 40,
            "pagerank": 0.6,
            "docstring": "User database model",
        },
    ]
    db_path = _make_survey_db(symbols)
    try:
        intent = {
            "capability": "add user authentication",
            "target_subsystem": "auth",
            "keywords": ["authenticate", "user", "login"],
        }
        result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(
            intent=intent, survey_db=db_path
        )
        assert len(result["files"]) > 0
        assert len(result["symbols"]) > 0
        assert len(result["edit_sites"]) > 0

        # Each edit site must have required keys
        for site in result["edit_sites"]:
            assert "path" in site
            assert "start_line" in site
            assert "end_line" in site
            assert "scope" in site
            assert site["start_line"] <= site["end_line"]
            assert site["scope"] in ("function", "class", "module")
    finally:
        db_path.unlink(missing_ok=True)


def test_edit_sites_scope_function():
    """Function-kind symbols map to scope='function' in edit sites."""
    symbols = [
        {
            "path": "src/utils.py",
            "kind": "function",
            "name": "helper",
            "lineno": 5,
            "end_lineno": 15,
            "pagerank": 0.9,
            "docstring": "helper function for utils",
        }
    ]
    db_path = _make_survey_db(symbols)
    try:
        result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(
            intent={"capability": "helper utils"}, survey_db=db_path
        )
        assert any(s["scope"] == "function" for s in result["edit_sites"])
    finally:
        db_path.unlink(missing_ok=True)


def test_edit_sites_scope_class():
    """Class-kind symbols map to scope='class' in edit sites."""
    symbols = [
        {
            "path": "src/models.py",
            "kind": "class",
            "name": "MyModel",
            "lineno": 1,
            "end_lineno": 50,
            "pagerank": 0.7,
            "docstring": "My base model class",
        }
    ]
    db_path = _make_survey_db(symbols)
    try:
        result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(
            intent={"capability": "model class"}, survey_db=db_path
        )
        assert any(s["scope"] == "class" for s in result["edit_sites"])
    finally:
        db_path.unlink(missing_ok=True)


def test_top_k_symbols_limit_respected():
    """top_k_symbols parameter limits number of returned symbols."""
    symbols = [
        {
            "path": f"src/module_{i}.py",
            "kind": "function",
            "name": f"func_{i}",
            "lineno": 1,
            "end_lineno": 10,
            "pagerank": float(i) / 10.0,
            "docstring": f"function number {i}",
        }
        for i in range(1, 11)
    ]
    db_path = _make_survey_db(symbols)
    try:
        result = bf_4_hierarchical_localizer_file_class_symbol_edit_site(
            intent={"capability": "function module"},
            survey_db=db_path,
            top_k_symbols=3,
        )
        assert len(result["symbols"]) <= 3
        assert len(result["edit_sites"]) <= 3
    finally:
        db_path.unlink(missing_ok=True)


def test_brownfield_localizer_module_importable():
    """File exists AC: src/bob3/brownfield/localizer.py must be importable."""
    from bob3.brownfield import localizer  # noqa: F401

    assert hasattr(localizer, "localize")
    assert hasattr(localizer, "rank_symbols_by_intent")
    assert hasattr(localizer, "extract_edit_sites")
    assert hasattr(localizer, "check_disjoint")


def test_check_disjoint_overlapping():
    """check_disjoint returns True when edit sites overlap."""
    from bob3.brownfield.localizer import check_disjoint

    loc_a = {
        "edit_sites": [{"path": "src/foo.py", "start_line": 10, "end_line": 30, "scope": "function"}]
    }
    loc_b = {
        "edit_sites": [{"path": "src/foo.py", "start_line": 25, "end_line": 40, "scope": "function"}]
    }
    assert check_disjoint(loc_a, loc_b) is True


def test_check_disjoint_non_overlapping():
    """check_disjoint returns False when edit sites do not overlap."""
    from bob3.brownfield.localizer import check_disjoint

    loc_a = {
        "edit_sites": [{"path": "src/foo.py", "start_line": 10, "end_line": 20, "scope": "function"}]
    }
    loc_b = {
        "edit_sites": [{"path": "src/foo.py", "start_line": 25, "end_line": 40, "scope": "function"}]
    }
    assert check_disjoint(loc_a, loc_b) is False


def test_check_disjoint_different_files():
    """check_disjoint returns False when edit sites are in different files."""
    from bob3.brownfield.localizer import check_disjoint

    loc_a = {
        "edit_sites": [{"path": "src/foo.py", "start_line": 10, "end_line": 30, "scope": "function"}]
    }
    loc_b = {
        "edit_sites": [{"path": "src/bar.py", "start_line": 10, "end_line": 30, "scope": "function"}]
    }
    assert check_disjoint(loc_a, loc_b) is False
