"""Tests for the clangd/libclang C++ semantic survey backend.

The environment running these tests has neither clangd nor libclang installed,
so the tests exercise:
  * detect_clangd_availability() reporting unavailability cleanly,
  * build_clangd_index() populating survey.db from an *injected* semantic index
    (the seam that decouples DB population from a live compiler front end),
  * the tree-sitter/BF-1 fallback path when clangd is absent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bob.survey import clangd_backend
from bob.survey.clangd_backend import (
    ClangdAvailability,
    build_clangd_index,
    detect_clangd_availability,
)


# A small semantic index resembling clangd-indexer output for two RCCL-ish TUs.
_SAMPLE_INDEX = {
    "symbols": [
        {
            "usr": "c:@F@ncclAllReduce#",
            "name": "ncclAllReduce",
            "kind": "function",
            "namespace": "",
            "signature": "ncclResult_t ncclAllReduce(const void*, void*, size_t)",
            "decl": {"path": "src/nccl.h", "line": 42},
            "def": {"path": "src/collectives.cc", "line": 100},
        },
        {
            "usr": "c:@F@enqueueKernel#",
            "name": "enqueueKernel",
            "kind": "function",
            "namespace": "rccl",
            "signature": "void rccl::enqueueKernel()",
            "decl": {"path": "src/enqueue.h", "line": 8},
            "def": {"path": "src/enqueue.cc", "line": 30},
        },
    ],
    "edges": [
        # enqueueKernel calls ncclAllReduce — a cross-TU call edge.
        {"src_usr": "c:@F@enqueueKernel#", "dst_usr": "c:@F@ncclAllReduce#", "kind": "calls"},
    ],
}


def _write_compile_commands(workspace: Path) -> Path:
    cc = workspace / "compile_commands.json"
    cc.write_text('[{"directory": "/x", "command": "clang++ a.cc", "file": "a.cc"}]')
    return cc


def test_detect_returns_availability_dataclass(tmp_path: Path) -> None:
    """detect_clangd_availability returns a ClangdAvailability with the expected fields."""
    avail = detect_clangd_availability(tmp_path)
    assert isinstance(avail, ClangdAvailability)
    assert isinstance(avail.clangd_on_path, bool)
    assert isinstance(avail.compile_commands_present, bool)
    assert isinstance(avail.available, bool)


def test_detect_no_compile_commands(tmp_path: Path) -> None:
    """With no compile_commands.json present, availability is False."""
    avail = detect_clangd_availability(tmp_path)
    assert avail.compile_commands_present is False
    assert avail.available is False


def test_detect_finds_compile_commands(tmp_path: Path) -> None:
    """A compile_commands.json in the workspace is detected."""
    _write_compile_commands(tmp_path)
    avail = detect_clangd_availability(tmp_path)
    assert avail.compile_commands_present is True
    # available also requires clangd on PATH, which is absent here.
    assert avail.available == (avail.clangd_on_path and avail.compile_commands_present)


def test_detect_available_requires_both(tmp_path: Path) -> None:
    """available is the conjunction of clangd-on-path and compile_commands-present."""
    _write_compile_commands(tmp_path)
    avail = detect_clangd_availability(tmp_path)
    assert avail.available is (avail.clangd_on_path and avail.compile_commands_present)


def test_build_from_injected_index_populates_db(tmp_path: Path) -> None:
    """An injected semantic index populates the survey.db symbols/edges tables."""
    db_path = tmp_path / "survey.db"
    result = build_clangd_index(tmp_path, db_path=db_path, index_records=_SAMPLE_INDEX)

    assert result["ok"] is True
    assert result["backend"] == "injected"
    assert result["symbol_count"] == 2
    assert result["edge_count"] == 1

    conn = sqlite3.connect(str(db_path))
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM symbols").fetchall()}
        assert names == {"ncclAllReduce", "enqueueKernel"}
        # Semantic columns are populated.
        usrs = {r[0] for r in conn.execute("SELECT usr FROM symbols").fetchall()}
        assert "c:@F@ncclAllReduce#" in usrs
        edge_kinds = [r[0] for r in conn.execute("SELECT kind FROM edges").fetchall()]
        assert edge_kinds == ["calls"]
    finally:
        conn.close()


def test_build_resolves_cross_tu_call_edge(tmp_path: Path) -> None:
    """The call edge resolves by USR to the correct src/dst symbol rows."""
    db_path = tmp_path / "survey.db"
    build_clangd_index(tmp_path, db_path=db_path, index_records=_SAMPLE_INDEX)

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT s.name, d.name, e.kind
            FROM edges e
            JOIN symbols s ON e.src_id = s.id
            JOIN symbols d ON e.dst_id = d.id
            """
        ).fetchone()
    finally:
        conn.close()

    assert row == ("enqueueKernel", "ncclAllReduce", "calls")


def test_build_persists_signature_and_namespace(tmp_path: Path) -> None:
    """decl/def locations, signature and namespace survive the round-trip."""
    db_path = tmp_path / "survey.db"
    build_clangd_index(tmp_path, db_path=db_path, index_records=_SAMPLE_INDEX)

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT namespace, signature, path, lineno, def_path, def_lineno "
            "FROM symbols WHERE name = 'enqueueKernel'"
        ).fetchone()
    finally:
        conn.close()

    namespace, signature, path, lineno, def_path, def_lineno = row
    assert namespace == "rccl"
    assert "enqueueKernel" in signature
    assert path == "src/enqueue.h"
    assert lineno == 8
    assert def_path == "src/enqueue.cc"
    assert def_lineno == 30


def test_build_tracks_file_hashes(tmp_path: Path) -> None:
    """The referenced C++ source files get file_hashes rows for incremental refresh."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "collectives.cc").write_text("int main(){return 0;}\n")

    db_path = tmp_path / "survey.db"
    build_clangd_index(tmp_path, db_path=db_path, index_records=_SAMPLE_INDEX)

    conn = sqlite3.connect(str(db_path))
    try:
        paths = {r[0] for r in conn.execute("SELECT path FROM file_hashes").fetchall()}
    finally:
        conn.close()

    # Only files that actually exist on disk are hashed.
    assert "src/collectives.cc" in paths


def test_build_is_idempotent(tmp_path: Path) -> None:
    """Re-running the build does not duplicate symbols or edges."""
    db_path = tmp_path / "survey.db"
    build_clangd_index(tmp_path, db_path=db_path, index_records=_SAMPLE_INDEX)
    build_clangd_index(tmp_path, db_path=db_path, index_records=_SAMPLE_INDEX)

    conn = sqlite3.connect(str(db_path))
    try:
        n_sym = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        n_edge = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    finally:
        conn.close()

    assert n_sym == 2
    assert n_edge == 1


def test_build_falls_back_when_clangd_absent(tmp_path: Path) -> None:
    """With no clangd and no injected index, build returns a graceful fallback result."""
    result = build_clangd_index(tmp_path, db_path=tmp_path / "survey.db")
    assert result["ok"] is True
    assert result["backend"] in ("tree-sitter", "fallback")
    assert result["symbol_count"] == 0


def test_all_edge_kinds_accepted(tmp_path: Path) -> None:
    """calls, overrides, instantiates and includes are all valid edge kinds."""
    index = {
        "symbols": [
            {"usr": "A", "name": "A", "kind": "class"},
            {"usr": "B", "name": "B", "kind": "class"},
        ],
        "edges": [
            {"src_usr": "A", "dst_usr": "B", "kind": "calls"},
            {"src_usr": "A", "dst_usr": "B", "kind": "overrides"},
            {"src_usr": "A", "dst_usr": "B", "kind": "instantiates"},
            {"src_usr": "A", "dst_usr": "B", "kind": "includes"},
        ],
    }
    db_path = tmp_path / "survey.db"
    result = build_clangd_index(tmp_path, db_path=db_path, index_records=index)
    assert result["edge_count"] == 4

    conn = sqlite3.connect(str(db_path))
    try:
        kinds = {r[0] for r in conn.execute("SELECT kind FROM edges").fetchall()}
    finally:
        conn.close()
    assert kinds == {"calls", "overrides", "instantiates", "includes"}


def test_integration_bob_survey_importable() -> None:
    """integration: bob.survey — the package re-exports the backend symbols."""
    import bob.survey as survey_pkg

    assert hasattr(survey_pkg, "build_clangd_index")
    assert hasattr(survey_pkg, "detect_clangd_availability")
    assert clangd_backend.build_clangd_index is survey_pkg.build_clangd_index
