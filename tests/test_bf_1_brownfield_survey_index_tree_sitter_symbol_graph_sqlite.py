"""Tests for bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite."""

from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

import pytest

from bob.bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite import (
    bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_repo(tmp_path: Path) -> Path:
    """Create a minimal fake Python repo with defs + implicit features."""
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "models.py").write_text(
        textwrap.dedent("""\
        class User:
            '''A user model.'''
            def get_name(self):
                return self.name

        class Admin(User):
            pass
        """)
    )
    (pkg / "utils.py").write_text(
        textwrap.dedent("""\
        from mypkg.models import User

        def make_user(name: str) -> User:
            return User()
        """)
    )
    (pkg / "stub_mod.py").write_text(
        textwrap.dedent("""\
        class NotImplFeature:
            '''stub: not yet implemented'''
            def run(self):
                pass
        """)
    )
    return tmp_path


# ---------------------------------------------------------------------------
# AC: test_bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite
# ---------------------------------------------------------------------------


def test_bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
    tmp_path: Path,
) -> None:
    """Main AC: function runs, creates DB, returns expected structure."""
    repo = make_repo(tmp_path)
    db_path = tmp_path / "survey.db"

    result = bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=repo,
        db_path=db_path,
    )

    # Result structure
    assert result["ok"] is True
    assert result["mode"] == "full"
    assert "workspace" in result
    assert "db_path" in result
    assert "implicit_features" in result
    assert isinstance(result["implicit_features"], list)
    assert isinstance(result["feature_count"], int)
    assert result["feature_count"] == len(result["implicit_features"])

    # DB was created
    assert db_path.exists(), "survey.db was not created"

    # DB has expected tables
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "symbols" in tables, f"Missing 'symbols' table; got {tables}"
    assert "edges" in tables, f"Missing 'edges' table; got {tables}"
    assert "file_hashes" in tables, f"Missing 'file_hashes' table; got {tables}"


def test_bf_1_symbols_populated(tmp_path: Path) -> None:
    """Symbols table must contain class and function names from the repo."""
    repo = make_repo(tmp_path)
    db_path = tmp_path / "survey.db"

    bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=repo,
        db_path=db_path,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        names = {
            row[0]
            for row in conn.execute("SELECT name FROM symbols").fetchall()
        }
    finally:
        conn.close()

    assert "User" in names, f"Expected 'User' in symbols; got {names}"
    assert "Admin" in names, f"Expected 'Admin' in symbols; got {names}"
    assert "make_user" in names, f"Expected 'make_user' in symbols; got {names}"


def test_bf_1_pagerank_stored(tmp_path: Path) -> None:
    """symbols.pagerank must be populated (non-negative floats)."""
    repo = make_repo(tmp_path)
    db_path = tmp_path / "survey.db"

    bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=repo,
        db_path=db_path,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT pagerank FROM symbols").fetchall()
    finally:
        conn.close()

    assert rows, "No rows in symbols table"
    for (pr,) in rows:
        assert isinstance(pr, float), f"pagerank is not a float: {pr!r}"
        assert pr >= 0.0, f"pagerank is negative: {pr}"


def test_bf_1_implicit_feature_detection(tmp_path: Path) -> None:
    """Implicit feature scan must find the stub class."""
    repo = make_repo(tmp_path)
    db_path = tmp_path / "survey.db"

    result = bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=repo,
        db_path=db_path,
    )

    candidates = result["implicit_features"]
    names = [c["name"] for c in candidates]
    assert "NotImplFeature" in names, (
        f"Expected NotImplFeature in implicit candidates; got {names}"
    )


def test_bf_1_incremental_refresh(tmp_path: Path) -> None:
    """Incremental refresh (refresh=True) returns mode='incremental'."""
    repo = make_repo(tmp_path)
    db_path = tmp_path / "survey.db"

    bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=repo,
        db_path=db_path,
    )

    result = bf_1_brownfield_survey_index_tree_sitter_symbol_graph_sqlite(
        workspace=repo,
        db_path=db_path,
        refresh=True,
    )

    assert result["mode"] == "incremental"
    assert result["ok"] is True
