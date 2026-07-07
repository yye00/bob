"""Boundary tests for the clangd/libclang C++ survey backend.

Empty, zero, or minimum input must return a well-defined result rather than
raising.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bob.survey.clangd_backend import (
    ClangdAvailability,
    build_clangd_index,
    detect_clangd_availability,
)


def test_empty_index_returns_zero_counts(tmp_path: Path) -> None:
    """An index with no symbols and no edges yields empty, well-defined counts."""
    result = build_clangd_index(
        tmp_path,
        db_path=tmp_path / "survey.db",
        index_records={"symbols": [], "edges": []},
    )
    assert result["ok"] is True
    assert result["symbol_count"] == 0
    assert result["edge_count"] == 0


def test_missing_keys_default_to_empty(tmp_path: Path) -> None:
    """An index dict missing 'symbols'/'edges' keys is treated as empty, not an error."""
    result = build_clangd_index(
        tmp_path,
        db_path=tmp_path / "survey.db",
        index_records={},
    )
    assert result["ok"] is True
    assert result["symbol_count"] == 0
    assert result["edge_count"] == 0


def test_no_index_no_clangd_is_graceful(tmp_path: Path) -> None:
    """No injected index and no clangd installed: graceful fallback, not a raise."""
    result = build_clangd_index(tmp_path, db_path=tmp_path / "survey.db")
    assert result["ok"] is True
    assert result["symbol_count"] == 0


def test_detect_on_empty_workspace(tmp_path: Path) -> None:
    """Availability detection on an empty workspace returns a clean False result."""
    avail = detect_clangd_availability(tmp_path)
    assert isinstance(avail, ClangdAvailability)
    assert avail.available is False


def test_edge_referencing_unknown_usr_is_skipped(tmp_path: Path) -> None:
    """An edge whose endpoints are not in the symbol set is dropped, not fatal."""
    db_path = tmp_path / "survey.db"
    result = build_clangd_index(
        tmp_path,
        db_path=db_path,
        index_records={
            "symbols": [{"usr": "A", "name": "A", "kind": "function"}],
            "edges": [{"src_usr": "A", "dst_usr": "MISSING", "kind": "calls"}],
        },
    )
    assert result["ok"] is True
    assert result["symbol_count"] == 1
    assert result["edge_count"] == 0

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 0
    finally:
        conn.close()


def test_single_symbol_no_edges(tmp_path: Path) -> None:
    """The minimum non-empty input — one symbol, no edges — round-trips cleanly."""
    result = build_clangd_index(
        tmp_path,
        db_path=tmp_path / "survey.db",
        index_records={"symbols": [{"usr": "S", "name": "S", "kind": "class"}]},
    )
    assert result["symbol_count"] == 1
    assert result["edge_count"] == 0
